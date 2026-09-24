"""Tests for the display data models and HSL parsing (no hardware / network)."""

import time
from datetime import datetime

from display import BusArrival, BusScheduleDisplay, HSLClient, load_epd_driver


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
