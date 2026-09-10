"""
Configuration module for E-Display.

Loads configuration from config.json as the single source of truth.
"""

import os
import json
from dataclasses import dataclass
from typing import Optional
from PIL import ImageFont

# =============================================================================
# PATHS (these are always static)
# =============================================================================

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PIC_DIR = os.path.join(BASE_DIR, 'pic')
ICON_DIR = os.path.join(PIC_DIR, 'icon')
FONT_DIR = os.path.join(BASE_DIR, 'font')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
# Use a directory for triggers so the directory itself can be mounted safely
TRIGGER_DIR = os.path.join(BASE_DIR, 'triggers')
REFRESH_TRIGGER_FILE = os.path.join(TRIGGER_DIR, 'refresh')

# Layout constants (fixed based on display hardware)
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
TOP_LINE_Y = 90
LINE_GAP = 60

# Colors
COLOR_BLACK = 'rgb(0,0,0)'
COLOR_WHITE = 'rgb(255,255,255)'
COLOR_GREY = 'rgb(235,235,235)'

# Timing
ERROR_RETRY_SECONDS = 30
SCREEN_CLEAR_HOUR = 3


# =============================================================================
# CONFIG DATA CLASSES
# =============================================================================

@dataclass
class StopConfig:
    id: str
    name: str
    routes: Optional[list] = None  # List of {name, mode} dicts for display


@dataclass
class DisplaySettings:
    max_items: int = 5
    show_arrival_minutes_threshold: int = 10
    hide_arrival_before_minutes: int = 10

    def to_dict(self) -> dict:
        """Convert to dictionary for saving."""
        return {
            'max_items': self.max_items,
            'show_arrival_minutes_threshold': self.show_arrival_minutes_threshold,
            'hide_arrival_before_minutes': self.hide_arrival_before_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DisplaySettings':
        """Create DisplaySettings from a dictionary.

        Reads field by field so a hand-edited config.json that omits a key —
        or carries an extra one from a newer version — still loads instead of
        raising TypeError out of the dataclass constructor.
        """
        return cls(
            max_items=data.get('max_items', 5),
            show_arrival_minutes_threshold=data.get('show_arrival_minutes_threshold', 10),
            hide_arrival_before_minutes=data.get('hide_arrival_before_minutes', 10),
        )


@dataclass
class WeatherConfig:
    """Configuration for the FMI weather overlay."""
    enabled: bool = True
    location: str = "Helsinki"   # FMI place name (Finnish cities)
    cache_minutes: int = 30

    def to_dict(self) -> dict:
        """Convert to dictionary for saving."""
        return {
            'enabled': self.enabled,
            'location': self.location,
            'cache_minutes': self.cache_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WeatherConfig':
        """Create WeatherConfig from a dictionary."""
        return cls(
            enabled=data.get('enabled', True),
            location=data.get('location', 'Helsinki'),
            cache_minutes=data.get('cache_minutes', 30),
        )


@dataclass
class LayoutConfig:
    """Configurable layout parameters for the e-paper display."""
    
    # Grid layout
    top_line_y: int = 90
    line_gap: int = 60
    
    # Clock position
    clock_x: int = 400
    clock_y: int = 10
    
    # Column positions
    route_col_x: int = 40
    route_col_width: int = 100
    destination_col_x: int = 100
    time_col_x: int = 770
    time_col_width: int = 180
    
    # Header row Y position
    header_y: int = 50
    
    # Alert position
    alert_y: int = 390
    alert_width: int = 780
    
    # Font sizes
    font_clock: int = 100
    font_numbers: int = 60
    font_text: int = 30
    font_header: int = 30
    font_small: int = 22

    # Weather overlay position (top-right of clock area)
    weather_x: int = 790
    weather_y: int = 15
    
    def to_dict(self) -> dict:
        """Convert to dictionary for saving."""
        return {
            'top_line_y': self.top_line_y,
            'line_gap': self.line_gap,
            'clock_x': self.clock_x,
            'clock_y': self.clock_y,
            'route_col_x': self.route_col_x,
            'route_col_width': self.route_col_width,
            'destination_col_x': self.destination_col_x,
            'time_col_x': self.time_col_x,
            'time_col_width': self.time_col_width,
            'header_y': self.header_y,
            'alert_y': self.alert_y,
            'alert_width': self.alert_width,
            'font_clock': self.font_clock,
            'font_numbers': self.font_numbers,
            'font_text': self.font_text,
            'font_header': self.font_header,
            'font_small': self.font_small,
            'weather_x': self.weather_x,
            'weather_y': self.weather_y,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LayoutConfig':
        """Create LayoutConfig from dictionary."""
        return cls(
            top_line_y=data.get('top_line_y', 90),
            line_gap=data.get('line_gap', 60),
            clock_x=data.get('clock_x', 400),
            clock_y=data.get('clock_y', 10),
            route_col_x=data.get('route_col_x', 40),
            route_col_width=data.get('route_col_width', 100),
            destination_col_x=data.get('destination_col_x', 100),
            time_col_x=data.get('time_col_x', 770),
            time_col_width=data.get('time_col_width', 180),
            header_y=data.get('header_y', 50),
            alert_y=data.get('alert_y', 390),
            alert_width=data.get('alert_width', 780),
            font_clock=data.get('font_clock', 100),
            font_numbers=data.get('font_numbers', 60),
            font_text=data.get('font_text', 30),
            font_header=data.get('font_header', 30),
            font_small=data.get('font_small', 22),
            weather_x=data.get('weather_x', 790),
            weather_y=data.get('weather_y', 15),
        )


@dataclass
class Config:
    hsl_api_url: str
    hsl_api_key: str
    stops: list[StopConfig]
    refresh_interval_seconds: int
    display: DisplaySettings
    layout: LayoutConfig
    epd_driver: str = "epd7in5b_V2"  # Waveshare driver module name in lib/waveshare_epd
    weather: Optional[WeatherConfig] = None

    def __post_init__(self):
        if self.weather is None:
            self.weather = WeatherConfig()
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        """Create Config from dictionary."""
        stops = [StopConfig(
            id=s.get('id', ''),
            name=s.get('name', ''),
            routes=s.get('routes')
        ) for s in data.get('stops', [])]
        display = DisplaySettings.from_dict(data.get('display', {}))
        layout = LayoutConfig.from_dict(data.get('layout', {}))
        weather = WeatherConfig.from_dict(data.get('weather', {}))
        return cls(
            hsl_api_url=data.get('hsl_api_url', 'https://api.digitransit.fi/routing/v2/hsl/gtfs/v1'),
            hsl_api_key=os.environ.get('HSL_API_KEY') or data.get('hsl_api_key', ''),
            stops=stops,
            refresh_interval_seconds=data.get('refresh_interval_seconds', 300),
            display=display,
            layout=layout,
            epd_driver=data.get('epd_driver', 'epd7in5b_V2'),
            weather=weather,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for saving.

        A key that came from the HSL_API_KEY environment variable is written
        out as an empty string: it lives in .env on purpose, and persisting it
        here would copy the secret into the bind-mounted config.json. The env
        value keeps winning on the next load either way.
        """
        env_key = os.environ.get('HSL_API_KEY')
        stored_key = '' if env_key and self.hsl_api_key == env_key else self.hsl_api_key
        return {
            'hsl_api_url': self.hsl_api_url,
            'hsl_api_key': stored_key,
            'stops': [{'id': s.id, 'name': s.name, 'routes': s.routes} for s in self.stops],
            'refresh_interval_seconds': self.refresh_interval_seconds,
            'epd_driver': self.epd_driver,
            'display': self.display.to_dict(),
            'layout': self.layout.to_dict(),
            'weather': self.weather.to_dict(),
        }


def load_config() -> Config:
    """Load configuration from config.json, falling back to defaults."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            return Config.from_dict(data)
        except (OSError, ValueError) as e:
            # A truncated or hand-mangled config.json must not take the display
            # loop and the whole API down — fall through to the defaults.
            print(f"Could not read {CONFIG_FILE} ({e}), using defaults")

    return Config.from_dict({})


def save_config(config: Config):
    """Save configuration to config.json."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config.to_dict(), f, indent=2)


# =============================================================================
# FONTS
# =============================================================================

class Fonts:
    """Font configuration for the display."""
    
    def __init__(self, font_dir: str = FONT_DIR, layout: Optional[LayoutConfig] = None):
        font_path = os.path.join(font_dir, 'Font.ttc')
        
        # Use layout config if provided, otherwise use defaults
        if layout:
            self.small = ImageFont.truetype(font_path, layout.font_small)
            self.text = ImageFont.truetype(font_path, layout.font_text)
            self.header = ImageFont.truetype(font_path, layout.font_header)
            self.numbers = ImageFont.truetype(font_path, layout.font_numbers)
            self.clock = ImageFont.truetype(font_path, layout.font_clock)
            self.error = ImageFont.truetype(font_path, layout.font_numbers)  # Same as numbers
        else:
            self.small = ImageFont.truetype(font_path, 22)
            self.text = ImageFont.truetype(font_path, 30)
            self.header = ImageFont.truetype(font_path, 30)
            self.numbers = ImageFont.truetype(font_path, 60)
            self.clock = ImageFont.truetype(font_path, 100)
            self.error = ImageFont.truetype(font_path, 60)
