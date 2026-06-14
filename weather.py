"""
FMI (Finnish Meteorological Institute) weather client for E-Display.

Fetches current temperature and weather condition via FMI Open Data WFS.
No API key required.

Data is cached for `cache_minutes` to avoid hammering the FMI API on
every 5-minute bus refresh cycle.
"""

import json
import os
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests


# =============================================================================
# DATA MODEL
# =============================================================================

@dataclass
class WeatherData:
    """Current weather snapshot."""
    temperature: float          # °C
    description: str            # Human-readable condition (e.g. "Light Snow")
    symbol_code: int            # Raw FMI WeatherSymbol3 integer (used for icon selection)
    location: str               # FMI place name used for the query
    fetched_at: float           # time.time() timestamp


# =============================================================================
# SYMBOL MAPPING  (FMI WeatherSymbol3 → description)
# =============================================================================

WEATHER_SYMBOLS: dict[int, str] = {
    1:  "Clear",
    2:  "Mostly Clear",
    4:  "Partly Cloudy",
    6:  "Mostly Cloudy",
    7:  "Overcast",
    21: "Light Showers",
    24: "Showers",
    31: "Light Rain",
    32: "Rain",
    33: "Heavy Rain",
    41: "Light Snow Showers",
    42: "Snow Showers",
    43: "Heavy Snow Showers",
    51: "Light Snow",
    52: "Snow",
    53: "Heavy Snow",
    61: "Thunderstorm",
    62: "Heavy Thunderstorm",
    71: "Fog",
    81: "Light Sleet",
    82: "Sleet",
    83: "Heavy Sleet",
    91: "Mist",
    92: "Fog",
}

# Maps FMI symbol code → icon category for PIL drawing
SYMBOL_CATEGORY: dict[int, str] = {
    1:  "clear",
    2:  "clear",
    4:  "partly_cloudy",
    6:  "cloudy",
    7:  "cloudy",
    21: "light_rain",
    24: "rain",
    31: "light_rain",
    32: "rain",
    33: "rain",
    41: "snow",
    42: "snow",
    43: "snow",
    51: "snow",
    52: "snow",
    53: "snow",
    61: "thunder",
    62: "thunder",
    71: "fog",
    72: "fog",
    73: "fog",
    81: "sleet",
    82: "sleet",
    83: "sleet",
    91: "fog",
    92: "fog",
}


# =============================================================================
# PIL WEATHER ICON DRAWING
# =============================================================================
# All icon functions take (draw, x, y, size) where (x,y) is the top-left corner
# of the size×size bounding box.  They draw using fill=0 (black) onto a PIL
# 1-bit ImageDraw context (mode '1'), matching the e-paper BW layer.

def _cloud_body(draw, x: int, y: int, size: int) -> None:
    """Reusable cloud silhouette occupying the upper ~65% of the bounding box."""
    s = size
    # Wide bottom body
    draw.ellipse([x + 1,          y + int(s * .40),
                  x + s - 1,      y + int(s * .65)], fill=0)
    # Left bump
    draw.ellipse([x + 3,          y + int(s * .20),
                  x + int(s*.50), y + int(s * .52)], fill=0)
    # Right (taller) bump
    draw.ellipse([x + int(s*.32), y + int(s * .10),
                  x + int(s*.88), y + int(s * .48)], fill=0)


def _icon_clear(draw, x: int, y: int, size: int) -> None:
    """Sun: filled circle + 8 radiating lines."""
    cx, cy = x + size // 2, y + size // 2
    r = max(4, size // 5)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    ri, ro = int(r * 1.55), size // 2 - 2
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        draw.line([
            cx + int(ri * math.cos(rad)), cy + int(ri * math.sin(rad)),
            cx + int(ro * math.cos(rad)), cy + int(ro * math.sin(rad)),
        ], fill=0, width=2)


def _icon_partly_cloudy(draw, x: int, y: int, size: int) -> None:
    """Small sun top-left + cloud covering lower-right."""
    sx, sy = x + size // 4, y + size // 4
    sr = max(3, size // 8)
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=0)
    ri, ro = int(sr * 1.5), int(sr * 2.2)
    for deg in range(0, 360, 60):
        rad = math.radians(deg)
        draw.line([
            sx + int(ri * math.cos(rad)), sy + int(ri * math.sin(rad)),
            sx + int(ro * math.cos(rad)), sy + int(ro * math.sin(rad)),
        ], fill=0, width=1)
    # Cloud shifted down-right so sun stays visible
    off = size // 5
    _cloud_body(draw, x + off, y + off, int(size * 0.82))


def _icon_cloudy(draw, x: int, y: int, size: int) -> None:
    """Plain cloud silhouette."""
    _cloud_body(draw, x, y, size)


def _icon_light_rain(draw, x: int, y: int, size: int) -> None:
    """Cloud + 2 angled rain drops."""
    _cloud_body(draw, x, y, size)
    top = y + int(size * .68)
    bot = top + int(size * .22)
    for drop_x in [x + int(size * .30), x + int(size * .65)]:
        draw.line([drop_x, top, drop_x - 2, bot], fill=0, width=2)


def _icon_rain(draw, x: int, y: int, size: int) -> None:
    """Cloud + 4 staggered rain drops."""
    _cloud_body(draw, x, y, size)
    top = y + int(size * .67)
    h = int(size * .20)
    for i, frac in enumerate([.18, .38, .58, .78]):
        dy = (i % 2) * int(size * .07)
        drop_x = x + int(size * frac)
        draw.line([drop_x, top + dy, drop_x - 2, top + dy + h], fill=0, width=2)


def _icon_snow(draw, x: int, y: int, size: int) -> None:
    """Cloud + 3 snow dots."""
    _cloud_body(draw, x, y, size)
    dot_y = y + int(size * .80)
    dot_r = max(2, size // 14)
    for frac in [.25, .50, .75]:
        dot_x = x + int(size * frac)
        draw.ellipse([dot_x - dot_r, dot_y - dot_r,
                      dot_x + dot_r, dot_y + dot_r], fill=0)


def _icon_sleet(draw, x: int, y: int, size: int) -> None:
    """Cloud + 1 rain drop + 1 snow dot (mixed precipitation)."""
    _cloud_body(draw, x, y, size)
    top = y + int(size * .68)
    bot = top + int(size * .22)
    draw.line([x + int(size * .32), top, x + int(size * .30), bot], fill=0, width=2)
    dot_r = max(2, size // 14)
    dot_x, dot_y = x + int(size * .65), y + int(size * .80)
    draw.ellipse([dot_x - dot_r, dot_y - dot_r,
                  dot_x + dot_r, dot_y + dot_r], fill=0)


def _icon_thunder(draw, x: int, y: int, size: int) -> None:
    """Cloud + filled lightning-bolt polygon."""
    _cloud_body(draw, x, y, size)
    by = y + int(size * .67)
    bx = x + int(size * .52)
    w = int(size * .22)
    h = int(size * .30)
    pts = [
        (bx + w // 2,     by),
        (bx - w // 4,     by + h // 2),
        (bx + w // 4,     by + h // 2),
        (bx - w // 2,     by + h),
        (bx + w // 4,     by + int(h * .42)),
        (bx - w // 4 + 2, by + int(h * .42)),
    ]
    draw.polygon(pts, fill=0)


def _icon_fog(draw, x: int, y: int, size: int) -> None:
    """Three horizontal bars of varying width."""
    bar_h = max(2, size // 12)
    specs = [(0.12, 0.88), (0.20, 0.80), (0.08, 0.70)]
    for i, (fs, fe) in enumerate(specs):
        bar_y = y + int(size * (0.20 + i * 0.27))
        draw.rectangle([
            x + int(size * fs), bar_y,
            x + int(size * fe), bar_y + bar_h,
        ], fill=0)


_ICON_DRAWERS = {
    "clear":         _icon_clear,
    "partly_cloudy": _icon_partly_cloudy,
    "cloudy":        _icon_cloudy,
    "light_rain":    _icon_light_rain,
    "rain":          _icon_rain,
    "snow":          _icon_snow,
    "sleet":         _icon_sleet,
    "thunder":       _icon_thunder,
    "fog":           _icon_fog,
}


def draw_weather_icon(draw, x: int, y: int, size: int, symbol_code: int) -> None:
    """
    Draw a weather condition icon at top-left (x, y) in a size×size bounding box.

    *draw* must be a PIL ImageDraw.Draw instance on a 1-bit ('1') image.
    The icon is drawn in black (fill=0).  Callers own clipping / bounds checks.
    """
    category = SYMBOL_CATEGORY.get(symbol_code, "cloudy")
    _ICON_DRAWERS.get(category, _icon_cloudy)(draw, x, y, size)


# =============================================================================
# WEATHER CLIENT
# =============================================================================

class FMIWeatherClient:
    """
    Fetches the current temperature from FMI Open Data.

    Results are cached for `cache_minutes` minutes so the FMI API is not
    called on every bus-schedule refresh cycle.
    """

    FMI_WFS_URL = (
        "https://opendata.fmi.fi/wfs"
        "?service=WFS&version=2.0.0&request=getFeature"
        "&storedquery_id=fmi::forecast::harmonie::surface::point::simple"
        "&place={place}&endtime={endtime}"
        "&parameters=Temperature,WeatherSymbol3"
    )

    def __init__(self, cache_minutes: int = 30):
        self._cache_minutes = cache_minutes
        self._cache: dict[str, WeatherData] = {}  # keyed by place name (lower-case)
        self._cache_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "weather_cache.json")
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self._cache[k] = WeatherData(
                            temperature=v["temperature"],
                            description=v["description"],
                            symbol_code=v["symbol_code"],
                            location=v["location"],
                            fetched_at=v["fetched_at"]
                        )
        except Exception as e:
            print(f"[weather] Failed to load weather cache: {e}")

    def _save_cache(self):
        try:
            data = {}
            for k, v in self._cache.items():
                data[k] = {
                    "temperature": v.temperature,
                    "description": v.description,
                    "symbol_code": v.symbol_code,
                    "location": v.location,
                    "fetched_at": v.fetched_at
                }
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[weather] Failed to save weather cache: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_current(self, place: str) -> Optional[WeatherData]:
        """
        Return a WeatherData for *place*, using the cache when still valid.

        Returns None on any error so callers can degrade gracefully.
        """
        key = place.lower()

        # Return cached value if still fresh
        cached = self._cache.get(key)
        if cached and self._is_fresh(cached):
            return cached

        try:
            data = self._fetch_from_fmi(place)
            if data:
                self._cache[key] = data
                self._save_cache()
            return data
        except Exception as exc:
            print(f"[weather] FMI fetch failed for '{place}': {exc}")
            # Return stale cache rather than nothing
            return cached

    def invalidate(self, place: str) -> None:
        """Force the next fetch to go to FMI (e.g. after a config change)."""
        self._cache.pop(place.lower(), None)
        self._save_cache()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_fresh(self, data: WeatherData) -> bool:
        age_seconds = time.time() - data.fetched_at
        return age_seconds < self._cache_minutes * 60

    def _fetch_from_fmi(self, place: str) -> Optional[WeatherData]:
        endtime = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = self.FMI_WFS_URL.format(place=place, endtime=endtime)

        response = requests.get(url, timeout=15)
        response.raise_for_status()

        return self._parse_response(response.text, place)

    def _parse_response(self, xml_text: str, place: str) -> Optional[WeatherData]:
        """
        Parse the BsWfs simple-format XML response.

        We group all (Time, ParameterName, ParameterValue) triples by timestamp
        and pick the entry whose timestamp is nearest to *now* (rounding forward).
        """
        member_pattern = re.compile(
            r'<BsWfs:Time>([^<]+)</BsWfs:Time>\s*'
            r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>\s*'
            r'<BsWfs:ParameterValue>([^<]*)</BsWfs:ParameterValue>',
            re.DOTALL,
        )

        data_by_time: dict[str, dict[str, float]] = {}

        for match in member_pattern.finditer(xml_text):
            time_str = match.group(1).strip()
            param = match.group(2).strip()
            raw = match.group(3).strip()

            if time_str not in data_by_time:
                data_by_time[time_str] = {}

            try:
                value = float(raw) if raw and raw != "NaN" else None
            except ValueError:
                value = None

            if value is not None:
                data_by_time[time_str][param] = value

        if not data_by_time:
            print(f"[weather] No data parsed from FMI response for '{place}'")
            return None

        # Find the entry whose timestamp is closest to now (first future timestamp,
        # or the last past one if all are in the past).
        now_utc = datetime.now(timezone.utc)
        best_time_str: Optional[str] = None
        best_delta: Optional[timedelta] = None

        for ts in sorted(data_by_time.keys()):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            delta = dt - now_utc
            # Prefer the first timestamp that is in the future (or least past)
            if best_delta is None or (delta > timedelta(0) and (best_delta < timedelta(0) or delta < best_delta)):
                best_delta = delta
                best_time_str = ts

        if best_time_str is None:
            # Fall back to the most recent entry
            best_time_str = sorted(data_by_time.keys())[-1]

        params = data_by_time[best_time_str]
        temperature = params.get("Temperature")
        symbol_val = int(params.get("WeatherSymbol3", 1) or 1)

        if temperature is None:
            return None

        description = WEATHER_SYMBOLS.get(symbol_val, "Cloudy")

        return WeatherData(
            temperature=round(temperature, 1),
            description=description,
            symbol_code=symbol_val,
            location=place,
            fetched_at=time.time(),
        )


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

# A single shared instance reused across the API and display loop.
# Cache TTL is initialised with the default; reconfigure via
# `weather_client._cache_minutes = config.weather.cache_minutes`.
weather_client = FMIWeatherClient(cache_minutes=30)
