"""Tests for FMI weather parsing (no network)."""

from datetime import datetime, timedelta, timezone

from weather import FMIWeatherClient, WEATHER_SYMBOLS, SYMBOL_CATEGORY


def _bswfs_xml(entries):
    """Build a minimal BsWfs simple-format XML from (time, param, value) triples."""
    members = "".join(
        f"<wfs:member><BsWfs:BsWfsElement>"
        f"<BsWfs:Time>{t}</BsWfs:Time>"
        f"<BsWfs:ParameterName>{p}</BsWfs:ParameterName>"
        f"<BsWfs:ParameterValue>{v}</BsWfs:ParameterValue>"
        f"</BsWfs:BsWfsElement></wfs:member>"
        for t, p, v in entries
    )
    return f'<wfs:FeatureCollection xmlns:wfs="x" xmlns:BsWfs="y">{members}</wfs:FeatureCollection>'


def test_parse_response_picks_nearest_future_timestamp():
    client = FMIWeatherClient(cache_minutes=30)
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = _bswfs_xml([
        (future, "Temperature", "-3.4"),
        (future, "WeatherSymbol3", "52"),
        (later, "Temperature", "10.0"),
        (later, "WeatherSymbol3", "1"),
    ])

    data = client._parse_response(xml, "Helsinki")
    assert data is not None
    assert data.temperature == -3.4
    assert data.symbol_code == 52
    assert data.description == "Snow"
    assert data.location == "Helsinki"


def test_parse_response_handles_nan_and_empty():
    client = FMIWeatherClient(cache_minutes=30)
    now = datetime.now(timezone.utc)
    ts = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = _bswfs_xml([(ts, "Temperature", "NaN"), (ts, "WeatherSymbol3", "")])
    # Temperature is NaN -> unusable -> returns None
    assert client._parse_response(xml, "Helsinki") is None


def test_parse_response_empty_returns_none():
    client = FMIWeatherClient(cache_minutes=30)
    assert client._parse_response("<empty/>", "Helsinki") is None


def test_is_fresh_respects_cache_minutes():
    import time
    client = FMIWeatherClient(cache_minutes=30)
    from weather import WeatherData

    fresh = WeatherData(1.0, "Clear", 1, "Helsinki", time.time())
    stale = WeatherData(1.0, "Clear", 1, "Helsinki", time.time() - 31 * 60)
    assert client._is_fresh(fresh) is True
    assert client._is_fresh(stale) is False


def test_every_symbol_has_a_draw_category():
    # Every described weather symbol must map to an icon category, and every
    # category must have a registered drawer.
    from weather import _ICON_DRAWERS
    for code in WEATHER_SYMBOLS:
        category = SYMBOL_CATEGORY.get(code)
        assert category is not None, f"symbol {code} has no category"
        assert category in _ICON_DRAWERS, f"category {category} has no drawer"


def test_parse_response_picks_most_recent_when_all_past():
    """FMI can return only past entries; the freshest one is the useful one."""
    client = FMIWeatherClient(cache_minutes=30)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = _bswfs_xml([
        (old, "Temperature", "-20.0"),
        (old, "WeatherSymbol3", "1"),
        (recent, "Temperature", "5.0"),
        (recent, "WeatherSymbol3", "1"),
    ])

    data = client._parse_response(xml, "Helsinki")
    assert data is not None
    assert data.temperature == 5.0


def test_parse_response_prefers_future_over_nearer_past():
    client = FMIWeatherClient(cache_minutes=30)
    now = datetime.now(timezone.utc)
    just_past = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (now + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = _bswfs_xml([
        (just_past, "Temperature", "-20.0"),
        (just_past, "WeatherSymbol3", "1"),
        (future, "Temperature", "5.0"),
        (future, "WeatherSymbol3", "1"),
    ])

    data = client._parse_response(xml, "Helsinki")
    assert data is not None
    assert data.temperature == 5.0


def test_set_cache_minutes_changes_freshness():
    import time
    from weather import WeatherData

    client = FMIWeatherClient(cache_minutes=30)
    reading = WeatherData(1.0, "Clear", 1, "Helsinki", time.time() - 20 * 60)
    assert client._is_fresh(reading) is True

    client.set_cache_minutes(10)
    assert client._is_fresh(reading) is False


def test_fmi_request_encodes_the_place_name(monkeypatch):
    """A place with a space must be encoded, not spliced into the URL."""
    seen = {}

    class _Response:
        text = "<empty/>"

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None):
        seen["url"] = url
        seen["params"] = params
        return _Response()

    monkeypatch.setattr("weather.requests.get", fake_get)

    client = FMIWeatherClient(cache_minutes=30)
    client._fetch_from_fmi("Turun lentoasema")

    assert " " not in seen["url"]
    assert seen["params"]["place"] == "Turun lentoasema"
    assert seen["params"]["storedquery_id"].startswith("fmi::forecast")
