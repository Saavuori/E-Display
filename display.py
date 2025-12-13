"""
E-Paper Display for HSL Bus Schedule

Displays real-time bus arrival information on a Waveshare 7.5" e-paper display.
"""

import os
import sys
import time
import textwrap
import traceback
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# Import configuration from config module (loads from config.json)
from config import (
    BASE_DIR, PIC_DIR, ICON_DIR, FONT_DIR,
    DISPLAY_WIDTH, DISPLAY_HEIGHT, TOP_LINE_Y, LINE_GAP,
    COLOR_BLACK, COLOR_WHITE, COLOR_GREY,
    ERROR_RETRY_SECONDS, SCREEN_CLEAR_HOUR,
    Fonts, load_config, Config, LayoutConfig
)

# Add lib folder for display driver modules
sys.path.append('lib')

# Try to import real hardware driver, fall back to mock for preview
PREVIEW_MODE = False
try:
    from waveshare_epd import epd7in5b_V2
except (ImportError, OSError):
    print("Hardware driver not available, using mock display for preview")
    from waveshare_epd import epd_mock as epd7in5b_V2
    PREVIEW_MODE = True


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class BusArrival:
    """Represents a single bus arrival."""
    route: str
    headsign: str
    arrival_seconds: int  # Seconds since midnight
    
    def minutes_until_arrival(self, current_seconds: int) -> float:
        """Calculate minutes until this bus arrives."""
        return (self.arrival_seconds - current_seconds) / 60
    
    def formatted_time(self) -> str:
        """Get arrival time as HH:MM format."""
        minutes, _ = divmod(self.arrival_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}"


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
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.headers = {"digitransit-subscription-key": api_key}
    
    def _build_query(self, stop_id: str) -> str:
        """Build GraphQL query for a stop."""
        return f'''
        {{
            stop(id:"{stop_id}") {{ 
                stoptimesWithoutPatterns {{
                    trip {{
                        route {{
                            shortName 
                            alerts {{ 
                                alertHeaderText
                                alertSeverityLevel
                            }}                   
                        }}           
                    }}            
                    realtimeArrival
                    scheduledArrival
                    arrivalDelay
                    realtimeState
                    headsign
                }}
            }}
        }}
        '''
    
    def fetch_stop_data(self, stop_ids: list[str]) -> list[dict]:
        """Fetch arrival data for multiple stops."""
        responses = []
        for stop_id in stop_ids:
            query = self._build_query(stop_id)
            response = requests.post(
                url=self.api_url,
                headers=self.headers,
                json={"query": query}
            )
            responses.append(response.json())
        return responses
    
    def parse_arrivals(self, responses: list[dict], min_seconds_away: int) -> tuple[list[BusArrival], list[Alert]]:
        """Parse API responses into BusArrival and Alert objects."""
        arrivals = []
        alerts = []
        current_seconds = self._seconds_since_midnight()
        
        for stop_response in responses:
            stop_data = self._get_stop_times(stop_response)
            if not stop_data:
                continue
                
            for bus in stop_data:
                # Extract alerts
                alerts.extend(self._extract_alerts(bus))
                
                # Extract arrival info
                arrival = self._extract_arrival(bus, current_seconds, min_seconds_away)
                if arrival:
                    arrivals.append(arrival)
        
        # Sort by arrival time
        arrivals.sort(key=lambda x: x.arrival_seconds)
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
    
    def _extract_arrival(self, bus_data: dict, current_seconds: int, min_seconds_away: int) -> Optional[BusArrival]:
        """Extract arrival info from bus data if it meets criteria."""
        try:
            realtime_arrival = bus_data["realtimeArrival"]
            
            # Skip buses arriving too soon
            if realtime_arrival - current_seconds <= min_seconds_away:
                return None
            
            return BusArrival(
                route=bus_data["trip"]["route"]["shortName"],
                headsign=bus_data["headsign"],
                arrival_seconds=realtime_arrival
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
    
    def render_schedule(self, arrivals: list[BusArrival], alerts: list[Alert]) -> tuple[str, str]:
        """Render the bus schedule and return paths to output images."""
        template_path = os.path.join(self.pic_dir, 'template.png')
        template_bw = Image.open(template_path)
        template_red = Image.open(template_path)
        
        draw_bw = ImageDraw.Draw(template_bw)
        draw_red = ImageDraw.Draw(template_red)
        
        self._draw_grid_lines(draw_red)
        self._draw_clock(draw_bw)
        self._draw_headers(draw_bw)
        self._draw_arrivals(draw_bw, arrivals)
        self._draw_alerts(draw_bw, alerts)
        
        # Save output images
        output_bw = os.path.join(self.pic_dir, 'screen_output_bw.png')
        output_red = os.path.join(self.pic_dir, 'screen_output_red.png')
        
        template_bw.save(output_bw)
        template_red.save(output_red)
        
        template_bw.close()
        template_red.close()
        
        return output_bw, output_red
    
    def render_error(self, error_source: str) -> str:
        """Render an error message and return path to output image."""
        print(f'Error in the {error_source} request.')
        
        error_image = Image.new('1', (self.epd.width, self.epd.height), 255)
        draw = ImageDraw.Draw(error_image)
        
        draw.text((100, 150), f'{error_source} ERROR', font=self.fonts.error, fill=COLOR_BLACK)
        draw.text((100, 300), 'Retrying in 30 seconds', font=self.fonts.small, fill=COLOR_BLACK)
        
        current_time = datetime.now().strftime('%H:%M')
        draw.text((300, 365), f'Last Refresh: {current_time}', font=self.fonts.error, fill=COLOR_BLACK)
        
        output_path = os.path.join(self.pic_dir, 'error.png')
        error_image.save(output_path)
        error_image.close()
        
        return output_path
    
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
    
    def _draw_alerts(self, draw: ImageDraw, alerts: list[Alert]):
        """Draw transit alerts if any."""
        if not alerts:
            return
        
        # Calculate centered X start position
        # Default width is 780 if not set (fallback)
        alert_width = getattr(self.layout, 'alert_width', 780)
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
        self.epd = epd7in5b_V2.EPD()
        
        # Load full config
        self.config = load_config()
        
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
    
    def run(self):
        """Main application loop."""
        self.renderer.initialize()
        
        while True:
            try:
                self._update_display()
            except Exception as e:
                print(f"Unexpected error: {e}")
                traceback.print_exc()
                self._handle_error("UNEXPECTED")
            
            # In preview mode, just render once and exit
            if PREVIEW_MODE:
                print("\n[PREVIEW MODE] Rendered once. Exiting.")
                break
            
            # Clear screen at designated hour to avoid burn-in
            if datetime.now().hour == SCREEN_CLEAR_HOUR:
                self.renderer.clear_screen()
            
            time.sleep(REFRESH_INTERVAL_SECONDS)
    
    def _update_display(self):
        """Fetch data and update the display."""
        # Retry loop for connection errors
        while True:
            try:
                print('Attempting to connect to HSL API.')
                stop_ids = [s.id for s in self.config.stops]
                responses = self.hsl_client.fetch_stop_data(stop_ids)
                print('Connection to API successful.')
                break
            except requests.RequestException as e:
                print(f'Connection error: {e}')
                self._handle_error("CONNECTION")
        
        # Parse the data
        min_seconds = self.config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = self.hsl_client.parse_arrivals(responses, min_seconds)
        
        # Render and display
        output_bw, output_red = self.renderer.render_schedule(arrivals, alerts)
        self.renderer.write_to_screen(output_bw, output_red)
    
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
