"""Tests for API handlers, called directly (no server, no network)."""

import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from PIL import Image

import api
import config
from api import ConfigModel, LayoutModel, PriceLayoutModel, PricesModel
from prices import PriceData, PriceSlot, current_slot, to_c_kwh


@pytest.fixture
def config_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", str(path))
    monkeypatch.delenv("HSL_API_KEY", raising=False)
    return path


def test_settings_save_keeps_layout_saved_by_layout_editor(config_file):
    """The dashboard's settings form used to post the layout it loaded at page
    open, reverting anything saved in the layout editor since."""
    api.update_layout(LayoutModel(clock_x=123))
    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k", refresh_interval_seconds=120))

    saved = config.load_config()
    assert saved.layout.clock_x == 123
    assert saved.refresh_interval_seconds == 120


def test_settings_save_with_layout_still_writes_it(config_file):
    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k", layout=LayoutModel(clock_x=321)))
    assert config.load_config().layout.clock_x == 321


def test_stop_search_url_encodes_query(config_file, monkeypatch):
    config.save_config(config.Config.from_dict({"hsl_api_key": "k"}))
    seen = {}

    class Geo:
        def raise_for_status(self):
            pass

        def json(self):
            return {"features": []}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["url"], seen["params"] = url, params
        return Geo()

    monkeypatch.setattr(api.requests, "get", fake_get)
    api.search_stops(q="Kauppakatu 1 & 2 #B", radius=500)
    assert "?" not in seen["url"]
    assert seen["params"]["text"] == "Kauppakatu 1 & 2 #B"


# --- spot-price screen ---------------------------------------------------------

@pytest.fixture
def trigger_file(monkeypatch, tmp_path):
    path = tmp_path / "triggers" / "refresh"
    monkeypatch.setattr(api, "TRIGGER_DIR", str(path.parent))
    monkeypatch.setattr(api, "REFRESH_TRIGGER_FILE", str(path))
    return path


def _price_data(hours_back: int = 2, count: int = 4 * 30):
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_back)
    q = timedelta(minutes=15)
    slots = [PriceSlot(start + i * q, start + (i + 1) * q, 40.0 + i % 8) for i in range(count)]
    return PriceData(slots=slots, resolution_minutes=15, fetched_at=time.time())


def test_settings_save_switches_screen_and_triggers_redraw(config_file, trigger_file):
    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k"))
    assert config.load_config().screen == "transit"
    assert not trigger_file.exists()  # nothing changed, nothing to redraw

    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k", screen="prices",
                                  prices=PricesModel(vat_percent=10)))
    saved = config.load_config()
    assert saved.screen == "prices"
    assert saved.prices.vat_percent == 10
    assert trigger_file.exists()


def test_settings_save_keeps_screen_prices_and_price_layout_when_omitted(config_file, trigger_file):
    api.update_price_layout(PriceLayoutModel(chart_y=260))
    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k", screen="prices",
                                  prices=PricesModel(chart_hours=24)))
    api.update_config(ConfigModel(hsl_api_url="u", hsl_api_key="k"))

    saved = config.load_config()
    assert saved.screen == "prices"
    assert saved.prices.chart_hours == 24
    assert saved.price_layout.chart_y == 260
    assert api.get_price_layout()["chart_y"] == 260


def test_price_layout_model_defaults_match_dataclass():
    assert PriceLayoutModel().model_dump() == config.PriceLayoutConfig().to_dict()
    assert PricesModel().model_dump() == asdict(config.PricesConfig())


def test_get_prices_returns_view(config_file, monkeypatch):
    data = _price_data()
    monkeypatch.setattr(api, "current_prices", lambda settings: data)
    body = api.get_prices()

    current = current_slot(data.slots, datetime.now(timezone.utc))
    assert body["current"]["price"] == pytest.approx(to_c_kwh(current.eur_mwh, 25.5))
    assert body["today"] is not None
    assert body["cheapest"]["hours"] == 3
    assert body["points"] and all("start" in p and "price" in p for p in body["points"])
    assert body["stale"] is False


def test_get_prices_unavailable(config_file, monkeypatch):
    monkeypatch.setattr(api, "current_prices", lambda settings: None)
    with pytest.raises(HTTPException) as exc:
        api.get_prices()
    assert exc.value.status_code == 503


def test_preview_renders_price_screen(config_file, monkeypatch, tmp_path):
    config.save_config(config.Config.from_dict({"screen": "prices", "weather": {"enabled": False}}))
    monkeypatch.setattr(api, "current_prices", lambda settings: _price_data())
    monkeypatch.setattr(api, "PREVIEW_FILE", tmp_path / "preview.png")
    called = {}

    def spy(self, view, weather=None):  # stands in for drawing, which test_display covers
        called["view"] = view
        blank = Image.new("1", (800, 480), 255)
        return blank, blank

    monkeypatch.setattr(api.DisplayRenderer, "render_prices", spy)
    monkeypatch.setattr(api.DisplayRenderer, "write_to_screen",
                        lambda self, bw, red: (tmp_path / "preview.png").write_bytes(b"png"))
    assert api.generate_preview() == b"png"
    assert called["view"].has_data
