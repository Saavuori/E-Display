"""
E-Paper Display for HSL Bus Schedule

Displays real-time bus arrival information on a Waveshare 7.5" e-paper display.
"""

import os
import sys
import time
import textwrap
import importlib
import traceback
from datetime import date, datetime
from dataclasses import dataclass
from typing import Optional

import requests
from PIL import Image, ImageDraw

# Import configuration from config module (loads from config.json)
from config import (
    BASE_DIR, PIC_DIR, FONT_DIR,
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    COLOR_BLACK,
    ERROR_RETRY_SECONDS, SCREEN_CLEAR_HOUR,
    REFRESH_TRIGGER_FILE,
    Fonts, load_config, Config, LayoutConfig
)

from weather import WeatherData, current_weather, draw_weather_icon

# Add lib folder for display driver modules. Anchored to this file rather than
# the working directory, so running display.py from another directory still
# finds the real driver instead of failing over to (or crashing in) the mock.
LIB_DIR = os.path.join(BASE_DIR, 'lib')
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

DEFAULT_EPD_DRIVER = "epd7in5b_V2"


def load_epd_driver(driver_name: str = DEFAULT_EPD_DRIVER):
    """Import a Waveshare EPD driver module by name, falling back to the mock.

    Returns a tuple of (driver_module, preview_mode) where preview_mode is True
    when the real hardware driver could not be loaded (e.g. running off-Pi).
    """
    try:
        module = importlib.import_module(f"waveshare_epd.{driver_name}")
        return module, False
    except (ImportError, OSError, RuntimeError) as e:
        print(f"Hardware driver '{driver_name}' not available ({e}), using mock display for preview")
        from waveshare_epd import epd_mock
        return epd_mock, True


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class BusArrival:
    """Represents a single bus arrival."""
    route: str
    headsign: str
    arrival_time: int  # Unix timestamp (serviceDay + realtimeArrival)
    delay: int = 0  # Delay in seconds

    @property
    def is_late(self) -> bool:
        """Check if bus is late (delay > 60 seconds)."""
        return self.delay > 60

    def minutes_until_arrival(self, now: float) -> float:
        """Calculate minutes until this bus arrives, *now* being a Unix timestamp."""
        return (self.arrival_time - now) / 60

    def formatted_time(self) -> str:
        """Get arrival time as H:MM local time."""
        local = datetime.fromtimestamp(self.arrival_time)
        return f"{local.hour}:{local.minute:02d}"

    def display_time(self, now: float, minutes_threshold: int) -> str:
        """Minutes to go when closer than *minutes_threshold*, else the clock time."""
        minutes = self.minutes_until_arrival(now)
        if minutes < minutes_threshold:
            return str(int(minutes))
        return self.formatted_time()


@dataclass
class Alert:
    """Represents a transit alert."""
    header_text: str
    severity_level: str


# =============================================================================
# HSL API CLIENT
# =============================================================================

class HSLClient:
    """Client for fetching data from the HSL API."""

    # Network timeout (seconds) so a hung request never freezes the display loop.
    REQUEST_TIMEOUT = 15

    # The stop id is passed as a GraphQL variable rather than pasted into the
    # query text. realtimeArrival counts seconds from the start of serviceDay
    # (a Unix timestamp), and a service day runs past midnight, so the two are
    # added together to get a wall-clock time.
    QUERY = """
        query ($id: String!) {
            stop(id: $id) {
                stoptimesWithoutPatterns {
                    trip {
                        route {
                            shortName
                            alerts {
                                alertHeaderText
                                alertSeverityLevel
                            }
                        }
                    }
                    serviceDay
                    realtimeArrival
                    scheduledArrival
                    arrivalDelay
                    realtimeState
                    headsign
                }
            }
        }
    """

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.headers = {"digitransit-subscription-key": api_key}

    def fetch_stop_data(self, stop_ids: list[str]) -> list[dict]:
        """Fetch arrival data for multiple stops."""
        responses = []
        for stop_id in stop_ids:
            response = requests.post(
                url=self.api_url,
                headers=self.headers,
                json={"query": self.QUERY, "variables": {"id": stop_id}},
                timeout=self.REQUEST_TIMEOUT,
            )
            responses.append(response.json())
        return responses

    def fetch_arrivals(self, stop_ids: list[str], min_seconds_away: int) -> tuple[list[BusArrival], list[Alert]]:
        """Fetch and parse arrivals for *stop_ids*. Network errors propagate."""
        return self.parse_arrivals(self.fetch_stop_data(stop_ids), min_seconds_away)

    def parse_arrivals(self, responses: list[dict], min_seconds_away: int,
                       now: Optional[float] = None) -> tuple[list[BusArrival], list[Alert]]:
        """Parse API responses into BusArrival and Alert objects.

        Every departure of a route carries that route's alerts, so alerts are
        de-duplicated by their text.
        """
        arrivals = []
        alerts = []
        seen_alerts = set()
        if now is None:
            now = time.time()

        for stop_response in responses:
            stop_data = self._get_stop_times(stop_response)
            if not stop_data:
                continue

            for bus in stop_data:
                for alert in self._extract_alerts(bus):
                    if alert.header_text not in seen_alerts:
                        seen_alerts.add(alert.header_text)
                        alerts.append(alert)

                arrival = self._extract_arrival(bus, now, min_seconds_away)
                if arrival:
                    arrivals.append(arrival)

        arrivals.sort(key=lambda x: x.arrival_time)
        return arrivals, alerts

    def _get_stop_times(self, stop_response: dict) -> Optional[list]:
        """Safely extract stop times from response."""
        try:
            return stop_response["data"]["stop"]["stoptimesWithoutPatterns"]
        except (KeyError, TypeError) as e:
            print(f"Error extracting stop times: {e}")
            return None

    def _extract_alerts(self, bus_data: dict) -> list[Alert]:
        """Extract alerts from bus data."""
        alerts = []
        try:
            alerts_list = bus_data["trip"]["route"]["alerts"]
            for alert in alerts_list:
                if alert.get("alertSeverityLevel") == 'WARNING':
                    alerts.append(Alert(
                        header_text=alert["alertHeaderText"],
                        severity_level=alert["alertSeverityLevel"]
                    ))
        except (KeyError, TypeError):
            pass
        return alerts

    def _extract_arrival(self, bus_data: dict, now: float, min_seconds_away: int) -> Optional[BusArrival]:
        """Extract arrival info from bus data if it meets criteria."""
        try:
            arrival_time = bus_data["serviceDay"] + bus_data["realtimeArrival"]

            # Skip buses arriving too soon
            if arrival_time - now <= min_seconds_away:
                return None

            return BusArrival(
                route=bus_data["trip"]["route"]["shortName"],
                headsign=bus_data["headsign"],
                arrival_time=arrival_time,
                delay=bus_data.get("arrivalDelay", 0)
            )
        except (KeyError, TypeError) as e:
            print(f"Error extracting arrival: {e}")
            return None


# =============================================================================
# DISPLAY RENDERER
# =============================================================================

class DisplayRenderer:
    """Handles rendering content to the e-paper display."""

    def __init__(self, epd, fonts: Fonts, pic_dir: str, layout: LayoutConfig, max_items: int = 5, show_minutes_threshold: int = 10):
        self.epd = epd
        self.fonts = fonts
        self.pic_dir = pic_dir
        self.layout = layout
        self.max_items = max_items
        self.show_minutes_threshold = show_minutes_threshold

    @classmethod
    def from_config(cls, epd, config: Config, pic_dir: str = PIC_DIR) -> 'DisplayRenderer':
        """Build a renderer for *config*."""
        renderer = cls(epd, None, pic_dir, config.layout)
        renderer.apply_config(config)
        return renderer

    def apply_config(self, config: Config):
        """Pick up layout and display settings from a (re)loaded config."""
        self.fonts = Fonts(FONT_DIR, layout=config.layout)
        self.layout = config.layout
        self.max_items = config.display.max_items
        self.show_minutes_threshold = config.display.show_arrival_minutes_threshold

    def initialize(self):
        """Initialize and clear the display."""
        print('Initializing and clearing screen.')
        self.epd.init()
        self.epd.Clear()

    def render_schedule(self, arrivals: list[BusArrival], alerts: list[Alert],
                        weather: Optional[WeatherData] = None) -> tuple[Image.Image, Image.Image]:
        """Render the bus schedule into black and red layers.

        Copies are saved to pic/ for inspection, but the images themselves are
        returned: pic/ is shared with the API container, which renders previews
        into the same files, so reading them back could pick up its render.
        """
        # Create blank white images instead of loading template file
        template_bw = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 255)
        template_red = Image.new('1', (DISPLAY_WIDTH, DISPLAY_HEIGHT), 255)

        draw_bw = ImageDraw.Draw(template_bw)
        draw_red = ImageDraw.Draw(template_red)

        self._draw_grid_lines(draw_red)
        self._draw_clock(draw_bw)
        self._draw_temperature(draw_bw, weather)
        self._draw_weather_icon(draw_bw, weather)
        self._draw_headers(draw_bw)
        self._draw_arrivals(draw_bw, draw_red, arrivals)
        self._draw_alerts(draw_bw, alerts)

        template_bw.save(os.path.join(self.pic_dir, 'screen_output_bw.png'))
        template_red.save(os.path.join(self.pic_dir, 'screen_output_red.png'))

        return template_bw, template_red

    def render_error(self, error_source: str) -> Image.Image:
        """Render an error message image."""
        print(f'Error in the {error_source} request.')

        error_image = Image.new('1', (self.epd.width, self.epd.height), 255)
        draw = ImageDraw.Draw(error_image)

        draw.text((100, 150), f'{error_source} ERROR', font=self.fonts.error, fill=COLOR_BLACK)
        draw.text((100, 300), f'Retrying in {ERROR_RETRY_SECONDS} seconds', font=self.fonts.small, fill=COLOR_BLACK)

        current_time = datetime.now().strftime('%H:%M')
        draw.text((300, 365), f'Last Refresh: {current_time}', font=self.fonts.error, fill=COLOR_BLACK)

        error_image.save(os.path.join(self.pic_dir, 'error.png'))

        return error_image

    def write_to_screen(self, screen_bw: Image.Image, screen_red: Image.Image):
        """Write black and red layers to the e-paper display."""
        print('Writing to screen.')

        image_bw = Image.new('1', (self.epd.width, self.epd.height), 255)
        image_red = Image.new('1', (self.epd.width, self.epd.height), 255)

        image_bw.paste(screen_bw, (0, 0))
        image_red.paste(screen_red, (0, 0))

        self.epd.init()
        self.epd.display(self.epd.getbuffer(image_bw), self.epd.getbuffer(image_red))
        time.sleep(2)
        self.epd.sleep()

    def clear_screen(self):
        """Clear the display to avoid burn-in."""
        print('Clearing screen to avoid burn-in.')
        self.epd.init()
        self.epd.Clear()

    @staticmethod
    def _temperature_text(weather: WeatherData) -> str:
        return f"{weather.temperature:+.1f}°C"

    def _draw_temperature(self, draw: ImageDraw, weather: Optional[WeatherData]):
        """Draw current temperature right-aligned in the top-right area beside the clock."""
        if weather is None:
            return
        draw.text(
            (self.layout.weather_x, self.layout.weather_y),
            self._temperature_text(weather),
            font=self.fonts.header,
            fill=COLOR_BLACK,
            anchor="ra",  # right edge, top of ascender
        )

    def _draw_weather_icon(self, draw: ImageDraw, weather: Optional[WeatherData]):
        """Draw weather condition icon to the left of the temperature text."""
        if weather is None:
            return
        icon_size = 46  # pixels — fits inside the 90px top zone
        # Measure temperature text width for precise icon placement
        bbox = draw.textbbox((0, 0), self._temperature_text(weather), font=self.fonts.header, anchor="la")
        text_width = bbox[2] - bbox[0]
        icon_x = self.layout.weather_x - text_width - 10 - icon_size
        icon_y = self.layout.weather_y
        draw_weather_icon(draw, icon_x, icon_y, icon_size, weather.symbol_code)

    def _draw_grid_lines(self, draw: ImageDraw):
        """Draw the grid lines for the schedule."""
        # Dotted separator lines between items
        for i in range(self.max_items - 1):
            y = self.layout.top_line_y + (i + 1) * self.layout.line_gap
            for x in range(0, DISPLAY_WIDTH, 6):
                draw.line([(x, y), (x + 2, y)], fill=COLOR_BLACK, width=4)

        # Top and bottom solid lines
        draw.line([(0, self.layout.top_line_y), (DISPLAY_WIDTH, self.layout.top_line_y)], fill=COLOR_BLACK, width=4)
        draw.line(
            [(0, self.layout.top_line_y + self.max_items * self.layout.line_gap), (DISPLAY_WIDTH, self.layout.top_line_y + self.max_items * self.layout.line_gap)],
            fill=COLOR_BLACK,
            width=4
        )

    def _draw_clock(self, draw: ImageDraw):
        """Draw the current time."""
        current_time = datetime.now().strftime('%H:%M')
        draw.text((self.layout.clock_x, self.layout.clock_y), current_time, font=self.fonts.clock, fill=COLOR_BLACK, anchor="mt")

    def _draw_headers(self, draw: ImageDraw):
        """Draw the column headers."""
        # Use route_col_x for the Route header
        draw.text((self.layout.route_col_x, self.layout.header_y), "Linja", font=self.fonts.header, fill=COLOR_BLACK, anchor="la")
        draw.text((self.layout.destination_col_x, self.layout.header_y), "Määränpää", font=self.fonts.header, fill=COLOR_BLACK, anchor="la")
        draw.text((self.layout.time_col_x, self.layout.header_y), "Aika/min", font=self.fonts.header, fill=COLOR_BLACK, anchor="ra")

    def _draw_arrivals(self, draw_bw: ImageDraw, draw_red: ImageDraw, arrivals: list[BusArrival]):
        """Draw the list of bus arrivals."""
        now = time.time()

        for i, bus in enumerate(arrivals[:self.max_items]):
            # Row i sits between the grid line at top_line_y + i * line_gap
            # and the next one down.
            y_pos = self.layout.top_line_y + (i * self.layout.line_gap)

            draw_bw.text((self.layout.route_col_x, y_pos), bus.route, font=self.fonts.numbers, fill=COLOR_BLACK, anchor="la")

            # Destination uses the smaller text font, nudged down to sit mid-row
            draw_bw.text((self.layout.destination_col_x, y_pos + 15), bus.headsign, font=self.fonts.text, fill=COLOR_BLACK, anchor="la")

            # Draw time in red if late, otherwise black
            draw = draw_red if bus.is_late else draw_bw
            draw.text((self.layout.time_col_x, y_pos), bus.display_time(now, self.show_minutes_threshold),
                      font=self.fonts.numbers, fill=COLOR_BLACK, anchor="ra")

    def _draw_alerts(self, draw: ImageDraw, alerts: list[Alert]):
        """Draw transit alerts if any."""
        if not alerts:
            return

        # Centre the alert area horizontally
        alert_width = self.layout.alert_width
        x_start = (DISPLAY_WIDTH - alert_width) // 2

        # Estimate characters per line based on width and font size (approx 0.6 aspect ratio)
        char_width = self.layout.font_text * 0.5  # Conservative estimate
        chars_per_line = int(alert_width / char_width)

        lines = textwrap.wrap(alerts[0].header_text, width=chars_per_line)
        for idx, line in enumerate(lines):
            draw.text((x_start + 10, self.layout.alert_y + idx * 30), line, font=self.fonts.text, fill=COLOR_BLACK, anchor="la")


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class BusScheduleDisplay:
    """Main application class for the bus schedule display."""

    def __init__(self):
        self.config = load_config()

        # Resolve the display driver from config (falls back to mock off-Pi)
        driver_module, self.preview_mode = load_epd_driver(self.config.epd_driver)
        self.epd = driver_module.EPD()

        self.renderer = DisplayRenderer.from_config(self.epd, self.config)
        self.hsl_client = HSLClient(self.config.hsl_api_url, self.config.hsl_api_key)
        self._last_clear: Optional[date] = None

    def _apply_config(self):
        """Push a freshly loaded config into the renderer and HSL client."""
        self.renderer.apply_config(self.config)
        self.hsl_client.api_url = self.config.hsl_api_url
        self.hsl_client.headers = {"digitransit-subscription-key": self.config.hsl_api_key}

    def _clear_due(self, now: datetime) -> bool:
        """True once per day, on the first cycle inside SCREEN_CLEAR_HOUR."""
        return now.hour == SCREEN_CLEAR_HOUR and self._last_clear != now.date()

    def run(self):
        """Main application loop."""
        self.renderer.initialize()

        while True:
            # Reload configuration to pick up changes
            try:
                self.config = load_config()
                self._apply_config()
            except Exception as e:
                print(f"Error reloading config: {e}")

            # Clear once a day to avoid burn-in, right before a redraw so the
            # panel is only blank for the length of one refresh.
            now = datetime.now()
            if not self.preview_mode and self._clear_due(now):
                self.renderer.clear_screen()
                self._last_clear = now.date()

            try:
                self._update_display()
            except Exception as e:
                print(f"Unexpected error: {e}")
                traceback.print_exc()
                self._handle_error("UNEXPECTED")

            # In preview mode, just render once and exit
            if self.preview_mode:
                print("\n[PREVIEW MODE] Rendered once. Exiting.")
                break

            # Wait for next refresh, but check for manual trigger every second
            refresh_interval = self.config.refresh_interval_seconds
            print(f"Sleeping for {refresh_interval} seconds...", flush=True)

            for i in range(refresh_interval):
                # Check for manual refresh trigger from web UI
                if os.path.exists(REFRESH_TRIGGER_FILE):
                    print("Manual refresh triggered from web UI", flush=True)
                    try:
                        os.remove(REFRESH_TRIGGER_FILE)
                    except OSError as e:
                        # Refresh anyway; the next cycle retries the removal.
                        print(f"ERROR: Could not remove trigger file: {e}", flush=True)
                    break

                time.sleep(1)

                # Print a countdown every minute
                if (refresh_interval - i) % 60 == 0:
                    print(f"Time to next refresh: {refresh_interval - i}s", flush=True)

    def _update_display(self):
        """Fetch data and update the display."""
        # Weather is cached, so this won't call FMI on every cycle
        weather = current_weather(self.config.weather)

        try:
            print('Attempting to connect to HSL API.', flush=True)
            stop_ids = [s.id for s in self.config.stops]
            min_seconds = self.config.display.hide_arrival_before_minutes * 60
            arrivals, alerts = self.hsl_client.fetch_arrivals(stop_ids, min_seconds)
            print('Connection to API successful.', flush=True)
        except requests.RequestException as e:
            print(f'Connection error: {e}', flush=True)
            self._handle_error("CONNECTION")
            return

        image_bw, image_red = self.renderer.render_schedule(arrivals, alerts, weather=weather)
        self.renderer.write_to_screen(image_bw, image_red)

    def _handle_error(self, error_type: str):
        """Handle and display an error."""
        error_image = self.renderer.render_error(error_type)
        self.renderer.write_to_screen(error_image, error_image)
        time.sleep(ERROR_RETRY_SECONDS)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    app = BusScheduleDisplay()
    app.run()
