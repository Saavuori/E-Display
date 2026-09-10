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
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

import requests
from PIL import Image, ImageDraw

# Import configuration from config module (loads from config.json)
from config import (
    PIC_DIR, FONT_DIR,
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    COLOR_BLACK,
    ERROR_RETRY_SECONDS, SCREEN_CLEAR_HOUR,
    REFRESH_TRIGGER_FILE,
    Fonts, load_config, LayoutConfig
)

# Weather client
from weather import WeatherData, weather_client, draw_weather_icon

# Add lib folder for display driver modules
sys.path.append('lib')

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


# Resolve the default driver at import time so modules importing PREVIEW_MODE
# (e.g. api.py) still work. The main app re-resolves it from config.
epd7in5b_V2, PREVIEW_MODE = load_epd_driver()


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class BusArrival:
    """Represents a single bus arrival."""
    route: str
    headsign: str
    arrival_seconds: int  # Seconds since midnight
    delay: int = 0  # Delay in seconds
    
    @property
    def is_late(self) -> bool:
        """Check if bus is late (delay > 60 seconds)."""
        return self.delay > 60
    
    def minutes_until_arrival(self, current_seconds: int) -> float:
        """Calculate minutes until this bus arrives."""
        return (self.arrival_seconds - current_seconds) / 60
    
    def formatted_time(self) -> str:
        """Get arrival time as HH:MM format."""
        minutes, _ = divmod(self.arrival_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        # GTFS counts a post-midnight departure as hour 24+ of the service day
        # that started the trip, so 24:25 has to be shown as 00:25.
        return f"{hours % 24}:{minutes:02d}"


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

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.headers = {"digitransit-subscription-key": api_key}
    
    # The stop id travels as a query variable so an id from config.json is
    # never spliced into the query document.
    STOP_QUERY = '''
        query StopArrivals($stopId: String!) {
            stop(id: $stopId) {
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
                    realtimeArrival
                    scheduledArrival
                    arrivalDelay
                    realtimeState
                    headsign
                }
            }
        }
        '''

    def fetch_stop_data(self, stop_ids: list[str]) -> list[dict]:
        """Fetch arrival data for multiple stops.

        One unreachable stop must not cost the whole screen, so a failed stop
        contributes an empty response and the rest still render. If *every*
        stop fails the error is re-raised, so the caller still shows the
        connection error screen instead of a blank timetable.
        """
        responses = []
        last_error: Optional[Exception] = None

        for stop_id in stop_ids:
            try:
                response = requests.post(
                    url=self.api_url,
                    headers=self.headers,
                    json={"query": self.STOP_QUERY, "variables": {"stopId": stop_id}},
                    timeout=self.REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                responses.append(response.json())
            except (requests.RequestException, ValueError) as e:
                print(f"Error fetching stop {stop_id}: {e}", flush=True)
                last_error = e

        if last_error is not None and not responses:
            raise last_error

        return responses
    
    def parse_arrivals(self, responses: list[dict], min_seconds_away: int) -> tuple[list[BusArrival], list[Alert]]:
        """Parse API responses into BusArrival and Alert objects."""
        arrivals = []
        alerts = []
        # The same route alert repeats on every stoptime of that route, so
        # track what has already been collected.
        seen_alerts: set[tuple[str, str]] = set()
        current_seconds = self._seconds_since_midnight()

        for stop_response in responses:
            stop_data = self._get_stop_times(stop_response)
            if not stop_data:
                continue

            for bus in stop_data:
                # Extract alerts
                for alert in self._extract_alerts(bus):
                    key = (alert.header_text, alert.severity_level)
                    if key not in seen_alerts:
                        seen_alerts.add(key)
                        alerts.append(alert)

                # Extract arrival info
                arrival = self._extract_arrival(bus, current_seconds, min_seconds_away)
                if arrival:
                    arrivals.append(arrival)
        
        # Sort by arrival time
        arrivals.sort(key=lambda x: x.arrival_seconds)
        return arrivals, alerts
    
    def _get_stop_times(self, stop_response: dict) -> Optional[list]:
        """Safely extract stop times from response."""
        if not stop_response:
            return None
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
    
    def _extract_arrival(self, bus_data: dict, current_seconds: int, min_seconds_away: int) -> Optional[BusArrival]:
        """Extract arrival info from bus data if it meets criteria."""
        try:
            # realtimeArrival is null for a trip with no realtime feed; falling
            # back to the timetable keeps those departures on the screen
            # instead of silently dropping them.
            arrival = bus_data.get("realtimeArrival")
            if arrival is None:
                arrival = bus_data.get("scheduledArrival")
            if arrival is None:
                return None

            # Skip buses arriving too soon
            if arrival - current_seconds <= min_seconds_away:
                return None

            return BusArrival(
                route=bus_data["trip"]["route"]["shortName"],
                headsign=bus_data["headsign"],
                arrival_seconds=arrival,
                delay=bus_data.get("arrivalDelay") or 0
            )
        except (KeyError, TypeError) as e:
            print(f"Error extracting arrival: {e}")
            return None
    
    @staticmethod
    def _seconds_since_midnight() -> int:
        """Calculate seconds elapsed since midnight."""
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int((now - midnight).total_seconds())


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
        
    def initialize(self):
        """Initialize and clear the display."""
        print('Initializing and clearing screen.')
        self.epd.init()
        self.epd.Clear()
    
    def render_schedule(self, arrivals: list[BusArrival], alerts: list[Alert], weather: Optional[WeatherData] = None) -> tuple[str, str]:
        """Render the bus schedule and return paths to output images."""
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
        
        # Save output images
        output_bw = os.path.join(self.pic_dir, 'screen_output_bw.png')
        output_red = os.path.join(self.pic_dir, 'screen_output_red.png')
        
        template_bw.save(output_bw)
        template_red.save(output_red)
        
        template_bw.close()
        template_red.close()
        
        return output_bw, output_red
    
    def render_error(self, error_source: str) -> tuple[str, str]:
        """Render an error message.

        Returns (black_layer_path, blank_red_layer_path). The red layer is
        blank on purpose: writing the same bitmap to both planes sets every
        error pixel twice on the three-colour panel.
        """
        print(f'Error in the {error_source} request.')

        error_image = Image.new('1', (self.epd.width, self.epd.height), 255)
        draw = ImageDraw.Draw(error_image)

        draw.text((100, 150), f'{error_source} ERROR', font=self.fonts.error, fill=COLOR_BLACK)
        draw.text((100, 300), f'Retrying in {ERROR_RETRY_SECONDS} seconds', font=self.fonts.small, fill=COLOR_BLACK)

        current_time = datetime.now().strftime('%H:%M')
        draw.text((300, 365), f'Last Refresh: {current_time}', font=self.fonts.error, fill=COLOR_BLACK)

        output_path = os.path.join(self.pic_dir, 'error.png')
        error_image.save(output_path)
        error_image.close()

        blank_image = Image.new('1', (self.epd.width, self.epd.height), 255)
        blank_path = os.path.join(self.pic_dir, 'error_blank.png')
        blank_image.save(blank_path)
        blank_image.close()

        return output_path, blank_path
    
    def write_to_screen(self, image_bw_path: str, image_red_path: str):
        """Write images to the e-paper display."""
        print('Writing to screen.')
        
        image_bw = Image.new('1', (self.epd.width, self.epd.height), 255)
        image_red = Image.new('1', (self.epd.width, self.epd.height), 255)
        
        screen_bw = Image.open(image_bw_path)
        screen_red = Image.open(image_red_path)
        
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
    
    def _draw_temperature(self, draw: ImageDraw, weather: Optional[WeatherData]):
        """Draw current temperature right-aligned in the top-right area beside the clock."""
        if weather is None:
            return
        temp_text = f"{weather.temperature:+.1f}\u00b0C"
        draw.text(
            (self.layout.weather_x, self.layout.weather_y),
            temp_text,
            font=self.fonts.header,
            fill=COLOR_BLACK,
            anchor="ra",  # right-aligned baseline
        )

    def _draw_weather_icon(self, draw: ImageDraw, weather: Optional[WeatherData]):
        """Draw weather condition icon to the left of the temperature text."""
        if weather is None:
            return
        icon_size = 46  # pixels — fits inside the 90px top zone
        temp_text = f"{weather.temperature:+.1f}\u00b0C"
        # Measure temperature text width for precise icon placement
        try:
            bbox = draw.textbbox((0, 0), temp_text, font=self.fonts.header, anchor="la")
            text_width = bbox[2] - bbox[0]
        except Exception:
            # Fallback estimate: average ~0.65× font size per character
            text_width = len(temp_text) * int(self.layout.font_header * 0.65)
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
        current_seconds = HSLClient._seconds_since_midnight()
        
        for i, bus in enumerate(arrivals[:self.max_items]):
            # Start below the top line
            # Items are spaced by line_gap
            # We add a small padding (e.g. 5px) from the line? 
            # layout.top_line_y is the Y of the line ABOVE the first item.
            # So item 0 is at top_line_y + padding?
            # Looking at `_draw_grid_lines`:
            # top line is at top_line_y
            # next line is top_line_y + line_gap
            # So the space is between top_line_y and top_line_y + line_gap
            # Text should be vertically centered or aligned nicely.
            
            # Let's align text baseline.
            # If line_gap is 60.
            # Font numbers is 60. That fills the gap tightly.
            
            y_pos = self.layout.top_line_y + (i * self.layout.line_gap)
            
            
            # Route number
            draw_bw.text((self.layout.route_col_x, y_pos), bus.route, font=self.fonts.numbers, fill=COLOR_BLACK, anchor="la")
            
            # Destination (smaller font, maybe offset Y slightly to center?)
            # Font text is 30.
            # 60 (gap) - 30 (font) = 30. / 2 = 15 offset?
            draw_bw.text((self.layout.destination_col_x, y_pos + 15), bus.headsign, font=self.fonts.text, fill=COLOR_BLACK, anchor="la")
            
            # Time
            minutes = bus.minutes_until_arrival(current_seconds)
            if minutes < self.show_minutes_threshold:
                time_text = str(int(minutes))
            else:
                time_text = bus.formatted_time()
                
            # Draw time in red if late, otherwise black
            if bus.is_late:
                draw_red.text((self.layout.time_col_x, y_pos), time_text, font=self.fonts.numbers, fill=COLOR_BLACK, anchor="ra")
            else:
                draw_bw.text((self.layout.time_col_x, y_pos), time_text, font=self.fonts.numbers, fill=COLOR_BLACK, anchor="ra")
    
    def _draw_alerts(self, draw: ImageDraw, alerts: list[Alert]):
        """Draw transit alerts if any."""
        if not alerts:
            return
        
        # Calculate centered X start position
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
        # Load full config
        self.config = load_config()

        # Resolve the display driver from config (falls back to mock off-Pi)
        self.renderer = None
        self._epd_driver_name = None
        self.preview_mode = False
        self.epd = None
        self._apply_epd_driver()

        # Initialize fonts with layout config
        self.fonts = Fonts(FONT_DIR, layout=self.config.layout)

        # Initialize renderer with layout config
        self.renderer = DisplayRenderer(
            self.epd,
            self.fonts,
            PIC_DIR,
            layout=self.config.layout,
            max_items=self.config.display.max_items,
            show_minutes_threshold=self.config.display.show_arrival_minutes_threshold
        )

        self.hsl_client = HSLClient(self.config.hsl_api_url, self.config.hsl_api_key)

        # Configure the shared weather client from loaded config
        weather_client.set_cache_minutes(self.config.weather.cache_minutes)

    def _apply_epd_driver(self):
        """(Re)resolve the panel driver when the configured name changes.

        Re-imported rather than cached from startup so switching epd_driver in
        the web UI takes effect on the next cycle, like every other setting.
        """
        if self.config.epd_driver == self._epd_driver_name:
            return

        driver_module, self.preview_mode = load_epd_driver(self.config.epd_driver)
        self.epd = driver_module.EPD()
        self._epd_driver_name = self.config.epd_driver
        if self.renderer is not None:
            self.renderer.epd = self.epd
    
    def run(self):
        """Main application loop."""
        self.renderer.initialize()
        
        while True:
            # Reload configuration to pick up changes
            try:
                new_config = load_config()
                layout_changed = new_config.layout != self.config.layout
                self.config = new_config

                # Rebuilding Fonts re-reads the TTF from disk, so only do it
                # when a font size (or anything else in the layout) moved.
                if layout_changed:
                    self.fonts = Fonts(FONT_DIR, layout=self.config.layout)
                    self.renderer.fonts = self.fonts

                # Update dependent components
                self.renderer.layout = self.config.layout
                self.renderer.max_items = self.config.display.max_items
                self.renderer.show_minutes_threshold = self.config.display.show_arrival_minutes_threshold

                # Update HSL client keys if changed
                self.hsl_client.api_url = self.config.hsl_api_url
                self.hsl_client.headers = {"digitransit-subscription-key": self.config.hsl_api_key}

                # Panel driver and weather cache TTL are config too
                self._apply_epd_driver()
                weather_client.set_cache_minutes(self.config.weather.cache_minutes)

            except Exception as e:
                print(f"Error reloading config: {e}")


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
            
            # Clear screen at designated hour to avoid burn-in
            if datetime.now().hour == SCREEN_CLEAR_HOUR:
                self.renderer.clear_screen()
            
            # Wait for next refresh, but check for manual trigger every second
            refresh_interval = self.config.refresh_interval_seconds
            print(f"Sleeping for {refresh_interval} seconds...", flush=True)
            
            trigger_unreadable = False
            for i in range(refresh_interval):
                # Check for manual refresh trigger from web UI
                if os.path.exists(REFRESH_TRIGGER_FILE):
                    try:
                        os.remove(REFRESH_TRIGGER_FILE)
                        print("Manual refresh triggered from web UI", flush=True)
                        break
                    except OSError as e:
                        # Breaking here would re-trigger on the next pass and
                        # spin the panel through a full refresh every second,
                        # which wears the e-ink out. Serve the rest of the
                        # interval instead and warn once.
                        if not trigger_unreadable:
                            print(
                                f"ERROR: Could not remove trigger file, ignoring "
                                f"manual refresh: {e}",
                                flush=True,
                            )
                            trigger_unreadable = True

                time.sleep(1)

                # Optional: print countdown every minute
                if (refresh_interval - i) % 60 == 0:
                    print(f"Time to next refresh: {refresh_interval - i}s", flush=True)
    
    def _update_display(self):
        """Fetch data and update the display."""
        # Fetch weather (cached — won't call FMI on every 5-min cycle)
        current_weather = None
        if self.config.weather.enabled:
            try:
                current_weather = weather_client.fetch_current(self.config.weather.location)
            except Exception as exc:
                print(f"Weather fetch failed, continuing without: {exc}")

        # Attempt to connect to HSL API
        try:
            print('Attempting to connect to HSL API.', flush=True)
            stop_ids = [s.id for s in self.config.stops]
            responses = self.hsl_client.fetch_stop_data(stop_ids)
            print('Connection to API successful.', flush=True)
        except requests.RequestException as e:
            print(f'Connection error: {e}', flush=True)
            self._handle_error("CONNECTION")
            return
        
        # Parse the data
        min_seconds = self.config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = self.hsl_client.parse_arrivals(responses, min_seconds)
        
        # Render and display
        output_bw, output_red = self.renderer.render_schedule(arrivals, alerts, weather=current_weather)
        self.renderer.write_to_screen(output_bw, output_red)
    
    def _handle_error(self, error_type: str):
        """Handle and display an error."""
        error_image, blank_image = self.renderer.render_error(error_type)
        self.renderer.write_to_screen(error_image, blank_image)
        time.sleep(ERROR_RETRY_SECONDS)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    app = BusScheduleDisplay()
    app.run()
