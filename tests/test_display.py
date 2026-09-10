"""Tests for the display data models and HSL parsing (no hardware / network)."""

import pytest

from display import BusArrival, HSLClient, load_epd_driver


def test_bus_arrival_is_late():
    assert BusArrival("9", "Somewhere", 40000, delay=120).is_late is True
    assert BusArrival("9", "Somewhere", 40000, delay=30).is_late is False


def test_bus_arrival_minutes_until():
    bus = BusArrival("9", "Somewhere", arrival_seconds=3600)
    assert bus.minutes_until_arrival(3000) == 10.0


def test_bus_arrival_formatted_time():
    # 8*3600 + 5*60 = 29100 seconds -> 8:05
    assert BusArrival("9", "X", 29100).formatted_time() == "8:05"


def _response(stoptimes):
    return {"data": {"stop": {"stoptimesWithoutPatterns": stoptimes}}}


def test_parse_arrivals_filters_and_sorts():
    client = HSLClient("url", "key")
    now = HSLClient._seconds_since_midnight()

    stoptimes = [
        {  # far future -> kept (later)
            "trip": {"route": {"shortName": "9", "alerts": []}},
            "realtimeArrival": now + 1200,
            "arrivalDelay": 0,
            "headsign": "Late Bus",
        },
        {  # near future -> kept (earlier), should sort first
            "trip": {"route": {"shortName": "7", "alerts": []}},
            "realtimeArrival": now + 600,
            "arrivalDelay": 0,
            "headsign": "Early Bus",
        },
        {  # too soon -> filtered out by min_seconds_away
            "trip": {"route": {"shortName": "1", "alerts": []}},
            "realtimeArrival": now + 60,
            "arrivalDelay": 0,
            "headsign": "Skip",
        },
    ]

    arrivals, alerts = client.parse_arrivals([_response(stoptimes)], min_seconds_away=300)

    assert [a.route for a in arrivals] == ["7", "9"]  # sorted by arrival time
    assert all(a.headsign != "Skip" for a in arrivals)
    assert alerts == []


def test_parse_arrivals_extracts_warning_alerts():
    client = HSLClient("url", "key")
    now = HSLClient._seconds_since_midnight()

    stoptimes = [{
        "trip": {"route": {"shortName": "9", "alerts": [
            {"alertHeaderText": "Delays expected", "alertSeverityLevel": "WARNING"},
            {"alertHeaderText": "Minor info", "alertSeverityLevel": "INFO"},
        ]}},
        "realtimeArrival": now + 900,
        "arrivalDelay": 0,
        "headsign": "Dest",
    }]

    _, alerts = client.parse_arrivals([_response(stoptimes)], min_seconds_away=0)
    assert len(alerts) == 1
    assert alerts[0].header_text == "Delays expected"


def test_parse_arrivals_handles_malformed_response():
    client = HSLClient("url", "key")
    arrivals, alerts = client.parse_arrivals([{"errors": "boom"}], min_seconds_away=0)
    assert arrivals == []
    assert alerts == []


def test_load_epd_driver_falls_back_to_mock():
    module, preview = load_epd_driver("does_not_exist_driver")
    assert preview is True
    assert hasattr(module, "EPD")


def test_formatted_time_wraps_past_midnight():
    """GTFS counts a post-midnight departure as hour 24+ of the service day."""
    # 24*3600 + 25*60 = 87900 -> 00:25, not 24:25
    assert BusArrival("9", "X", 87900).formatted_time() == "0:25"
    assert BusArrival("9", "X", 25 * 3600).formatted_time() == "1:00"


def test_arrival_falls_back_to_scheduled_when_no_realtime():
    """A trip with no realtime feed still belongs on the screen."""
    client = HSLClient("url", "key")
    now = HSLClient._seconds_since_midnight()

    stoptimes = [{
        "trip": {"route": {"shortName": "9", "alerts": []}},
        "realtimeArrival": None,
        "scheduledArrival": now + 900,
        "arrivalDelay": None,
        "headsign": "Scheduled Only",
    }]

    arrivals, _ = client.parse_arrivals([_response(stoptimes)], min_seconds_away=300)
    assert [a.headsign for a in arrivals] == ["Scheduled Only"]
    assert arrivals[0].delay == 0


def test_arrival_dropped_when_no_time_at_all():
    client = HSLClient("url", "key")
    stoptimes = [{
        "trip": {"route": {"shortName": "9", "alerts": []}},
        "realtimeArrival": None,
        "scheduledArrival": None,
        "headsign": "Nothing",
    }]
    arrivals, _ = client.parse_arrivals([_response(stoptimes)], min_seconds_away=0)
    assert arrivals == []


def test_repeated_route_alert_is_reported_once():
    """The same route alert rides along on every stoptime of that route."""
    client = HSLClient("url", "key")
    now = HSLClient._seconds_since_midnight()
    alert = {"alertHeaderText": "Delays expected", "alertSeverityLevel": "WARNING"}

    stoptimes = [
        {
            "trip": {"route": {"shortName": "9", "alerts": [alert]}},
            "realtimeArrival": now + 600 + i * 60,
            "arrivalDelay": 0,
            "headsign": "Dest",
        }
        for i in range(3)
    ]

    _, alerts = client.parse_arrivals([_response(stoptimes)], min_seconds_away=0)
    assert len(alerts) == 1


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_one_failing_stop_does_not_lose_the_others(monkeypatch):
    import requests as requests_module

    calls = []

    def fake_post(**kwargs):
        stop_id = kwargs["json"]["variables"]["stopId"]
        calls.append(stop_id)
        if stop_id == "HSL:bad":
            raise requests_module.ConnectionError("boom")
        return _FakeResponse(_response([]))

    monkeypatch.setattr("display.requests.post", fake_post)

    client = HSLClient("url", "key")
    responses = client.fetch_stop_data(["HSL:bad", "HSL:good"])

    assert calls == ["HSL:bad", "HSL:good"]
    assert len(responses) == 1  # the good stop still came through


def test_total_failure_raises_so_the_error_screen_shows(monkeypatch):
    import requests as requests_module

    def fake_post(**kwargs):
        raise requests_module.ConnectionError("boom")

    monkeypatch.setattr("display.requests.post", fake_post)

    client = HSLClient("url", "key")
    with pytest.raises(requests_module.RequestException):
        client.fetch_stop_data(["HSL:1", "HSL:2"])


def test_stop_id_travels_as_a_query_variable(monkeypatch):
    """An id from config.json must never be spliced into the query document."""
    seen = {}

    def fake_post(**kwargs):
        seen.update(kwargs["json"])
        return _FakeResponse(_response([]))

    monkeypatch.setattr("display.requests.post", fake_post)

    HSLClient("url", "key").fetch_stop_data(['HSL:1") { x } #'])

    assert seen["variables"] == {"stopId": 'HSL:1") { x } #'}
    assert 'HSL:1") { x } #' not in seen["query"]
