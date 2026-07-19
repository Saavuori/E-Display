"""Tests for the display data models and HSL parsing (no hardware / network)."""

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
