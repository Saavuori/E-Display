"""Tests for API handlers, called directly (no server, no network)."""

import pytest

import api
import config
from api import ConfigModel, LayoutModel


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
