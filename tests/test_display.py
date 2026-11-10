"""Tests for the display data models and HSL parsing (no hardware / network)."""

import time
from datetime import datetime, timedelta, timezone

from config import Config, SCREEN_PRICES
from display import BusArrival, BusScheduleDisplay, DisplayRenderer, HSLClient, load_epd_driver, sleep_seconds
from prices import HELSINKI, build_view, parse_viewer_response
from waveshare_epd import epd_mock


def test_bus_arrival_is_late():
    assert BusArrival("9", "Somewhere", 40000, delay=120).is_late is True
    assert BusArrival("9", "Somewhere", 40000, delay=30).is_late is False


def test_bus_arrival_minutes_until():
    bus = BusArrival("9", "Somewhere", arrival_time=3600)
    assert bus.minutes_until_arrival(3000) == 10.0


def test_bus_arrival_formatted_time():
    arrival = datetime(2026, 1, 15, 8, 5).timestamp()
    assert BusArrival("9", "X", int(arrival)).formatted_time() == "8:05"


def test_bus_arrival_display_time_switches_at_threshold():
    now = 1_000_000
    assert BusArrival("9", "X", now + 5 * 60 + 30).display_time(now, 10) == "5"
    later = BusArrival("9", "X", now + 15 * 60)
    assert later.display_time(now, 10) == later.formatted_time()


def _response(stoptimes):
    return {"data": {"stop": {"stoptimesWithoutPatterns": stoptimes}}}


def _stoptime(route, service_day, realtime_arrival, headsign="Dest", alerts=()):
    return {
        "trip": {"route": {"shortName": route, "alerts": list(alerts)}},
        "serviceDay": service_day,
        "realtimeArrival": realtime_arrival,
        "arrivalDelay": 0,
        "headsign": headsign,
    }


def test_parse_arrivals_filters_and_sorts():
    client = HSLClient("url", "key")
    now = 1_700_000_000
    day = now - 36_000  # service day started ten hours ago

    stoptimes = [
        _stoptime("9", day, 36_000 + 1200, "Late Bus"),   # kept (later)
        _stoptime("7", day, 36_000 + 600, "Early Bus"),   # kept, sorts first
        _stoptime("1", day, 36_000 + 60, "Skip"),         # too soon
    ]

    arrivals, alerts = client.parse_arrivals([_response(stoptimes)], min_seconds_away=300, now=now)

    assert [a.route for a in arrivals] == ["7", "9"]  # sorted by arrival time
    assert all(a.headsign != "Skip" for a in arrivals)
    assert alerts == []


def test_parse_arrivals_across_midnight():
    """Just after midnight, trips of yesterday's service day (realtimeArrival
    past 24h) and of today's must land on one timeline."""
    client = HSLClient("url", "key")
    today = 1_700_006_400            # service day starting at "midnight"
    yesterday = today - 86_400
    now = today + 120                # 00:02

    stoptimes = [
        _stoptime("2", today, 900),              # 00:15 on today's service day
        _stoptime("1", yesterday, 86_400 + 600), # 00:10, yesterday's service day
    ]
    arrivals, _ = client.parse_arrivals([_response(stoptimes)], min_seconds_away=0, now=now)

    assert [a.route for a in arrivals] == ["1", "2"]
    assert [round(a.minutes_until_arrival(now)) for a in arrivals] == [8, 13]


def test_parse_arrivals_extracts_warning_alerts_once():
    client = HSLClient("url", "key")
    now = time.time()
    route_alerts = [
        {"alertHeaderText": "Delays expected", "alertSeverityLevel": "WARNING"},
        {"alertHeaderText": "Minor info", "alertSeverityLevel": "INFO"},
    ]
    # Two departures of the same route carry the same alert.
    stoptimes = [
        _stoptime("9", int(now), 900, alerts=route_alerts),
        _stoptime("9", int(now), 1500, alerts=route_alerts),
    ]

    _, alerts = client.parse_arrivals([_response(stoptimes)], min_seconds_away=0)
    assert [a.header_text for a in alerts] == ["Delays expected"]


def test_parse_arrivals_handles_malformed_response():
    client = HSLClient("url", "key")
    arrivals, alerts = client.parse_arrivals([{"errors": "boom"}], min_seconds_away=0)
    assert arrivals == []
    assert alerts == []


def test_stop_id_is_sent_as_graphql_variable(monkeypatch):
    sent = {}

    class FakeResponse:
        def json(self):
            return _response([])

    def fake_post(url, headers, json, timeout):
        sent.update(json)
        return FakeResponse()

    monkeypatch.setattr("display.requests.post", fake_post)
    HSLClient("url", "key").fetch_stop_data(['HSL:1"){evil}'])
    assert sent["variables"] == {"id": 'HSL:1"){evil}'}
    assert "evil" not in sent["query"]


def test_load_epd_driver_falls_back_to_mock():
    module, preview = load_epd_driver("does_not_exist_driver")
    assert preview is True
    assert hasattr(module, "EPD")


def test_screen_clear_runs_once_per_day():
    app = BusScheduleDisplay.__new__(BusScheduleDisplay)
    app._last_clear = None
    three_am = datetime(2026, 1, 15, 3, 0)

    assert app._clear_due(three_am) is True
    app._last_clear = three_am.date()
    assert app._clear_due(datetime(2026, 1, 15, 3, 5)) is False
    assert app._clear_due(datetime(2026, 1, 16, 3, 0)) is True
    assert app._clear_due(datetime(2026, 1, 16, 4, 0)) is False


def test_sleep_follows_screen():
    now = datetime(2026, 11, 10, 12, 14, 0, tzinfo=timezone.utc)
    transit = Config.from_dict({"refresh_interval_seconds": 120})
    assert sleep_seconds(transit, now) == 120

    prices = Config.from_dict({"screen": SCREEN_PRICES, "refresh_interval_seconds": 120})
    assert sleep_seconds(prices, now) == 65  # just past 12:15


def _price_body(start: datetime, values: list[float]) -> dict:
    ms = int(start.timestamp() * 1000)
    return {"resolutionMinutes": 15, "points": [[ms + i * 900_000, v] for i, v in enumerate(values)]}


def test_render_prices_draws_both_layers(tmp_path):
    """A smoke test over awkward data: negative prices, a price above the
    threshold, and a DST day with no tomorrow published yet."""
    cfg = Config.from_dict({"screen": SCREEN_PRICES})
    now = datetime(2026, 10, 25, 9, 7, tzinfo=HELSINKI)
    day_start = datetime(2026, 10, 25, tzinfo=HELSINKI).astimezone(timezone.utc)
    values = [(-20.0 if i % 7 == 0 else 50.0 + i) for i in range(100)] + [400.0]
    data = parse_viewer_response(_price_body(day_start, values), fetched_at=time.time() - 7200)
    view = build_view(data, cfg.prices, now)
    assert view.stale

    renderer = DisplayRenderer.from_config(epd_mock.EPD(), cfg, pic_dir=str(tmp_path))
    bw, red = renderer.render_prices(view)

    assert bw.size == red.size == (800, 480)
    assert bw.getextrema() == (0, 255) and red.getextrema() == (0, 255)  # both layers drawn on
    assert (tmp_path / "screen_output_bw.png").exists()


def test_render_prices_without_data(tmp_path):
    cfg = Config.from_dict({"screen": SCREEN_PRICES})
    view = build_view(None, cfg.prices, datetime.now(timezone.utc))
    bw, red = DisplayRenderer.from_config(epd_mock.EPD(), cfg, pic_dir=str(tmp_path)).render_prices(view)
    assert bw.getextrema() == (0, 255)
