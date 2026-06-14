"""
FMI (Finnish Meteorological Institute) weather client for E-Display.

Fetches current temperature and weather condition via FMI Open Data WFS.
No API key required.

Data is cached for `cache_minutes` to avoid hammering the FMI API on
every 5-minute bus refresh cycle.
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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
    location: str               # FMI place name used for the query
    fetched_at: float           # time.monotonic() timestamp


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
            return data
        except Exception as exc:
            print(f"[weather] FMI fetch failed for '{place}': {exc}")
            # Return stale cache rather than nothing
            return cached

    def invalidate(self, place: str) -> None:
        """Force the next fetch to go to FMI (e.g. after a config change)."""
        self._cache.pop(place.lower(), None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_fresh(self, data: WeatherData) -> bool:
        age_seconds = time.monotonic() - data.fetched_at
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
            location=place,
            fetched_at=time.monotonic(),
        )


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

# A single shared instance reused across the API and display loop.
# Cache TTL is initialised with the default; reconfigure via
# `weather_client._cache_minutes = config.weather.cache_minutes`.
weather_client = FMIWeatherClient(cache_minutes=30)
