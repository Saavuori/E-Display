"""Tests for spot-price parsing and the maths behind the price screen (no network)."""

import time
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

import prices
from config import PricesConfig
from prices import (
    HELSINKI, PriceClient, PriceSlot, build_view, chart_bars, chart_window,
    cheapest_window, current_slot, day_stats, format_price, nice_axis,
    parse_viewer_response, seconds_until_next_slot, to_c_kwh,
)

QUARTER = timedelta(minutes=15)


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _slots(start: datetime, values: list[float], step: timedelta = QUARTER) -> list[PriceSlot]:
    return [PriceSlot(start + i * step, start + (i + 1) * step, v) for i, v in enumerate(values)]


def _response(start: datetime, values: list[float], resolution: int = 15) -> dict:
    ms = int(start.timestamp() * 1000)
    return {
        "area": "FI", "currency": "EUR", "unit": "MWH",
        "resolutionMinutes": resolution,
        "points": [[ms + i * resolution * 60_000, v] for i, v in enumerate(values)],
    }


# --- conversion and formatting ------------------------------------------------

def test_to_c_kwh_adds_vat_to_positive_prices_only():
    assert to_c_kwh(100.0, 25.5) == pytest.approx(12.55)
    assert to_c_kwh(0.0, 25.5) == 0.0
    assert to_c_kwh(-5.0, 25.5) == pytest.approx(-0.5)


def test_format_price_uses_decimal_comma():
    assert format_price(8.44) == "8,4"
    assert format_price(-0.31) == "-0,3"
    assert format_price(-0.01) == "0,0"


# --- parsing -----------------------------------------------------------------

def test_parse_viewer_response_builds_contiguous_slots():
    start = _utc(2026, 11, 10, 22)
    data = parse_viewer_response(_response(start, [10.0, 20.0, 30.0]), fetched_at=1.0)

    assert data.resolution_minutes == 15
    assert data.fetched_at == 1.0
    assert [s.eur_mwh for s in data.slots] == [10.0, 20.0, 30.0]
    assert data.slots[0].start == start
    assert data.slots[0].end == data.slots[1].start
    assert data.slots[-1].end == start + 3 * QUARTER


def test_parse_viewer_response_skips_bad_points_and_never_bridges_gaps():
    start = _utc(2026, 11, 10, 22)
    ms = int(start.timestamp() * 1000)
    body = {"resolutionMinutes": 15, "points": [
        [ms + 3_600_000, 5.0],           # an hour after the first
        [ms, 1.0],                       # out of order
        ["x", 2.0], [ms + 60_000], None, # malformed
        [ms + 900_000, float("nan")],    # not finite
    ]}
    slots = parse_viewer_response(body).slots

    assert [s.eur_mwh for s in slots] == [1.0, 5.0]
    assert slots[0].end == start + QUARTER  # not stretched to the next point


def test_parse_viewer_response_handles_empty_body():
    data = parse_viewer_response({})
    assert data.slots == []
    assert data.resolution_minutes == 15


# --- current slot, stats, cheapest window -----------------------------------

def test_current_slot_is_half_open():
    slots = _slots(_utc(2026, 11, 10, 12), [1.0, 2.0])
    assert current_slot(slots, _utc(2026, 11, 10, 12, 14, 59)).eur_mwh == 1.0
    assert current_slot(slots, _utc(2026, 11, 10, 12, 15)).eur_mwh == 2.0
    assert current_slot(slots, _utc(2026, 11, 10, 12, 30)) is None


def test_day_stats_uses_finnish_local_day():
    # 22:00 UTC on 10.11. is 00:00 on 11.11. in Helsinki (UTC+2).
    slots = _slots(_utc(2026, 11, 10, 21), [100.0] * 4 + [10.0, 50.0, -20.0, 30.0])
    stats = day_stats(slots, date(2026, 11, 11), vat_percent=0)

    assert stats.min_price == pytest.approx(-2.0)
    assert stats.max_price == pytest.approx(5.0)
    assert stats.avg_price == pytest.approx(1.75)
    assert stats.max_start.astimezone(HELSINKI).strftime("%H:%M") == "00:15"
    assert day_stats(slots, date(2026, 11, 12), 0) is None


def test_day_stats_covers_a_25_hour_dst_day():
    # Clocks go back on 25.10.2026 in Finland: that day runs 25 hours.
    day_start = datetime(2026, 10, 25, tzinfo=HELSINKI).astimezone(timezone.utc)
    hourly = _slots(day_start, [float(i) for i in range(26)], step=timedelta(hours=1))
    stats = day_stats(hourly, date(2026, 10, 25), vat_percent=0)

    assert stats.max_price == pytest.approx(2.4)  # hour 24, the 25th hour of the day
    assert stats.avg_price == pytest.approx(sum(range(25)) / 25 / 10)


def test_cheapest_window_finds_cheapest_run_from_now():
    start = _utc(2026, 11, 10, 12)
    # Hourly: 12 13 14 15 16 17 -> cheapest 2 h from now is 15–17.
    slots = _slots(start, [1.0, 50.0, 40.0, 10.0, 10.0, 90.0], step=timedelta(hours=1))
    window = cheapest_window(slots, 2, now=start + timedelta(hours=1, minutes=30), vat_percent=0)

    assert window.start == start + timedelta(hours=3)
    assert window.end == start + timedelta(hours=5)
    assert window.avg_price == pytest.approx(1.0)


def test_cheapest_window_includes_the_current_slot_and_skips_gaps():
    start = _utc(2026, 11, 10, 12)
    slots = _slots(start, [1.0, 1.0]) + _slots(start + timedelta(hours=1), [0.0, 0.0])
    # 12:15–12:30 then a gap: the only full half hour is 13:00–13:30.
    window = cheapest_window(slots, 0.5, now=start + timedelta(minutes=5), vat_percent=0)
    assert window.start == start + timedelta(hours=1)

    assert cheapest_window(slots, 5, now=start, vat_percent=0) is None


# --- chart geometry ------------------------------------------------------------

def test_chart_window_starts_two_hours_before_current_hour_and_is_capped():
    now = _utc(2026, 11, 10, 14, 40)
    slots = _slots(_utc(2026, 11, 10), [1.0] * 4 * 72)
    assert chart_window(slots, now, 36) == (_utc(2026, 11, 10, 12), _utc(2026, 11, 12, 0))

    short = _slots(_utc(2026, 11, 10), [1.0] * 4 * 22)  # ends 22:00
    assert chart_window(short, now, 36) == (_utc(2026, 11, 10, 12), _utc(2026, 11, 10, 22))
    assert chart_window([], now, 36) is None


def test_chart_bars_place_slots_by_time_and_mark_current():
    start = _utc(2026, 11, 10, 12)
    slots = _slots(start, [10.0, -10.0, 20.0, 30.0])
    bars = chart_bars(slots, start, start + timedelta(hours=1), x=100, width=400,
                      now=start + timedelta(minutes=20), vat_percent=0)

    assert [(b.x0, b.x1) for b in bars] == [(100, 200), (200, 300), (300, 400), (400, 500)]
    assert [b.price for b in bars] == pytest.approx([1.0, -1.0, 2.0, 3.0])
    assert [b.is_current for b in bars] == [False, True, False, False]


def test_chart_bars_fall_back_to_hours_when_too_narrow():
    start = _utc(2026, 11, 10)
    slots = _slots(start, [0.0, 10.0, 20.0, 30.0] * 36)  # 36 h of quarters
    bars = chart_bars(slots, start, start + timedelta(hours=36), x=0, width=300,
                      now=start, vat_percent=0)

    assert len(bars) == 36
    assert bars[0].price == pytest.approx(1.5)


def test_nice_axis_includes_zero_and_rounds():
    assert nice_axis(3.1, 14.2) == (0, 15, 5)
    low, high, step = nice_axis(-1.2, 8.0)
    assert low < -1.2 and low <= 0 and high >= 8.0 and step > 0
    assert nice_axis(0, 0) == (0, 1, 0.25)


def test_seconds_until_next_slot():
    assert seconds_until_next_slot(_utc(2026, 11, 10, 12, 14, 0)) == 65
    assert seconds_until_next_slot(_utc(2026, 11, 10, 12, 15, 0)) == 905
    assert seconds_until_next_slot(_utc(2026, 11, 10, 12, 59, 59), resolution_minutes=60, grace=0) == 1


# --- view ------------------------------------------------------------------

def test_build_view_without_tomorrow():
    now = datetime(2026, 11, 10, 9, 7, tzinfo=HELSINKI)
    day_start = datetime(2026, 11, 10, tzinfo=HELSINKI).astimezone(timezone.utc)
    data = parse_viewer_response(_response(day_start, [80.0] * 96), fetched_at=time.time())
    view = build_view(data, PricesConfig(vat_percent=25.5), now)

    assert view.has_data
    assert view.current_price == pytest.approx(10.04)
    assert view.today.avg_price == pytest.approx(10.04)
    assert view.tomorrow is None
    assert view.cheapest is not None
    assert view.chart_end == day_start + timedelta(days=1)
    assert view.stale is False


def test_build_view_with_no_data():
    view = build_view(None, PricesConfig(), datetime.now(timezone.utc))
    assert not view.has_data


# --- client ------------------------------------------------------------------

class _Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_client_caches_and_keeps_last_good_data_on_failure(monkeypatch):
    now = datetime.now(timezone.utc)
    body = _response(now - timedelta(hours=1), [50.0] * 12)
    calls = []

    def ok_get(url, timeout=None):
        calls.append(url)
        return _Response(body)

    monkeypatch.setattr(prices.requests, "get", ok_get)
    client = PriceClient()
    settings = PricesConfig(cache_minutes=15)
    first = client.fetch(settings)
    assert len(first.slots) == 12
    assert client.fetch(settings) is first and len(calls) == 1  # served from cache

    def failing_get(url, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(prices.requests, "get", failing_get)
    first.fetched_at -= 3600  # let the cache expire
    assert client.fetch(settings) is first  # still covers now

    assert client.fetch(settings, now=now + timedelta(days=1)) is None  # no longer does


def test_client_refetches_when_source_url_changes(monkeypatch):
    now = datetime.now(timezone.utc)
    seen = []

    def fake_get(url, timeout=None):
        seen.append(url)
        return _Response(_response(now, [1.0]))

    monkeypatch.setattr(prices.requests, "get", fake_get)
    client = PriceClient()
    client.fetch(PricesConfig(source_url="https://a"))
    client.fetch(PricesConfig(source_url="https://b"))
    assert seen == ["https://a", "https://b"]
