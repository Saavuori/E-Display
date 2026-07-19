"""Tests for configuration loading, saving, and defaults."""

import json

from config import Config, LayoutConfig, WeatherConfig


def _sample_config() -> Config:
    return Config.from_dict({
        "hsl_api_url": "https://example/api",
        "hsl_api_key": "secret",
        "stops": [{"id": "HSL:1", "name": "Stop One", "routes": [{"name": "9", "mode": "TRAM"}]}],
        "refresh_interval_seconds": 120,
        "epd_driver": "epd7in5_V2",
        "display": {
            "max_items": 4,
            "show_arrival_minutes_threshold": 8,
            "hide_arrival_before_minutes": 2,
        },
        "layout": {"clock_x": 123, "font_clock": 88},
        "weather": {"enabled": False, "location": "Tampere", "cache_minutes": 15},
    })


def test_config_round_trip_preserves_values():
    cfg = _sample_config()
    restored = Config.from_dict(cfg.to_dict())

    assert restored.hsl_api_url == "https://example/api"
    assert restored.refresh_interval_seconds == 120
    assert restored.epd_driver == "epd7in5_V2"
    assert restored.display.max_items == 4
    assert restored.stops[0].id == "HSL:1"
    assert restored.layout.clock_x == 123
    assert restored.layout.font_clock == 88
    assert restored.weather.enabled is False
    assert restored.weather.location == "Tampere"


def test_config_to_dict_is_json_serializable():
    cfg = _sample_config()
    # Should not raise
    json.dumps(cfg.to_dict())


def test_epd_driver_defaults_when_missing():
    cfg = Config.from_dict({})
    assert cfg.epd_driver == "epd7in5b_V2"


def test_api_key_env_override(monkeypatch):
    monkeypatch.setenv("HSL_API_KEY", "from-env")
    cfg = Config.from_dict({"hsl_api_key": "from-file"})
    assert cfg.hsl_api_key == "from-env"


def test_layout_from_dict_defaults_match_dataclass():
    """from_dict defaults should agree with the LayoutConfig dataclass defaults."""
    from_dict_defaults = LayoutConfig.from_dict({})
    dataclass_defaults = LayoutConfig()
    assert from_dict_defaults == dataclass_defaults


def test_weather_defaults():
    cfg = Config.from_dict({"weather": {}})
    assert isinstance(cfg.weather, WeatherConfig)
    assert cfg.weather.enabled is True
    assert cfg.weather.location == "Helsinki"
    assert cfg.weather.cache_minutes == 30
