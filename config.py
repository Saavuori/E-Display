"""
Configuration module for E-Display.

Loads configuration from config.json as the single source of truth.
"""

import os
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Optional
from PIL import ImageFont

# =============================================================================
# PATHS (these are always static)
# =============================================================================

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
PIC_DIR = os.path.join(BASE_DIR, 'pic')
FONT_DIR = os.path.join(BASE_DIR, 'font')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
# Use a directory for triggers so the directory itself can be mounted safely
TRIGGER_DIR = os.path.join(BASE_DIR, 'triggers')
REFRESH_TRIGGER_FILE = os.path.join(TRIGGER_DIR, 'refresh')

# Layout constants (fixed based on display hardware)
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# Colors
COLOR_BLACK = 'rgb(0,0,0)'

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

    @classmethod
    def from_dict(cls, data: dict) -> 'DisplaySettings':
        """Create DisplaySettings from a possibly partial dictionary."""
        return _from_partial_dict(cls, data)


@dataclass
class WeatherConfig:
    """Configuration for the FMI weather overlay."""
    enabled: bool = True
    location: str = "Helsinki"   # FMI place name (Finnish cities)
    cache_minutes: int = 30


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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'LayoutConfig':
        """Create LayoutConfig from dictionary; missing keys keep their defaults."""
        return _from_partial_dict(cls, data)


@dataclass
class Config:
    hsl_api_url: str
    hsl_api_key: str
    stops: list[StopConfig]
    refresh_interval_seconds: int
    display: DisplaySettings
    layout: LayoutConfig
    epd_driver: str = "epd7in5b_V2"  # Waveshare driver module name in lib/waveshare_epd
    weather: WeatherConfig = field(default_factory=WeatherConfig)

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
        weather = _from_partial_dict(WeatherConfig, data.get('weather', {}))
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
        """Convert to dictionary for saving."""
        return {
            'hsl_api_url': self.hsl_api_url,
            'hsl_api_key': self.hsl_api_key,
            'stops': [{'id': s.id, 'name': s.name, 'routes': s.routes} for s in self.stops],
            'refresh_interval_seconds': self.refresh_interval_seconds,
            'epd_driver': self.epd_driver,
            'display': asdict(self.display),
            'layout': self.layout.to_dict(),
            'weather': asdict(self.weather),
        }


def _from_partial_dict(cls, data: dict):
    """Build dataclass *cls* from *data*, keeping field defaults for missing
    keys and ignoring unknown ones, so a hand-edited or older config.json with
    a partial block loads instead of raising TypeError."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def load_config() -> Config:
    """Load configuration from config.json (defaults if it does not exist)."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            return Config.from_dict(json.load(f))
    # from_dict({}) also applies the HSL_API_KEY environment override.
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
        layout = layout or LayoutConfig()
        self.small = ImageFont.truetype(font_path, layout.font_small)
        self.text = ImageFont.truetype(font_path, layout.font_text)
        self.header = ImageFont.truetype(font_path, layout.font_header)
        self.numbers = ImageFont.truetype(font_path, layout.font_numbers)
        self.clock = ImageFont.truetype(font_path, layout.font_clock)
        self.error = self.numbers
