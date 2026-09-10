"""Tests for configuration loading, saving, and defaults."""

import json

import config as config_module
from config import Config, DisplaySettings, LayoutConfig, WeatherConfig


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


def test_display_settings_tolerates_partial_and_unknown_keys():
    """A hand-edited config.json must not take the whole app down."""
    cfg = Config.from_dict({"display": {"max_items": 3, "future_setting": 9}})
    assert cfg.display.max_items == 3
    # Missing keys fall back to the dataclass defaults
    assert cfg.display.show_arrival_minutes_threshold == 10
    assert cfg.display.hide_arrival_before_minutes == 10


def test_display_from_dict_defaults_match_dataclass():
    assert DisplaySettings.from_dict({}) == DisplaySettings()


def test_weather_from_dict_defaults_match_dataclass():
    assert WeatherConfig.from_dict({}) == WeatherConfig()


def test_env_api_key_is_not_written_back_to_config(monkeypatch):
    """The key lives in .env on purpose; to_dict() must not persist it."""
    monkeypatch.setenv("HSL_API_KEY", "from-env")
    cfg = Config.from_dict({"hsl_api_key": ""})
    assert cfg.hsl_api_key == "from-env"       # env still wins at runtime
    assert cfg.to_dict()["hsl_api_key"] == ""  # but never reaches config.json


def test_file_api_key_survives_round_trip(monkeypatch):
    monkeypatch.delenv("HSL_API_KEY", raising=False)
    cfg = Config.from_dict({"hsl_api_key": "from-file"})
    assert cfg.to_dict()["hsl_api_key"] == "from-file"


def test_load_config_falls_back_on_unreadable_file(monkeypatch, tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_FILE", str(bad))
    cfg = config_module.load_config()
    assert cfg.stops == []
    assert cfg.display.max_items == 5
