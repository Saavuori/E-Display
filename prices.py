"""
Electricity spot prices for E-Display.

Day-ahead prices for Finland come from the fingrid-viewer's public
`/api/prices` endpoint (github.com/Saavuori/fingrid-data-collector), which
fetches them from ENTSO-E with a token kept on that server. Its body is

    {"resolutionMinutes": 15, "points": [[epoch_ms, eur_per_mwh], ...], ...}

with each price holding from its time until the next. Everything here apart
from `PriceClient` is pure, so the maths behind the screen is testable
offline: unit conversion, the current slot, daily stats, the cheapest window
and the chart's bar geometry. Times are in Finnish local time, since the
prices are for the Finnish bidding zone.
"""

import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from config import PricesConfig

HELSINKI = ZoneInfo("Europe/Helsinki")

#: Data older than this is flagged on screen as possibly out of date.
STALE_AFTER_SECONDS = 3600


# =============================================================================
# DATA MODEL
# =============================================================================

@dataclass(frozen=True)
class PriceSlot:
    """One price period: `eur_mwh` holds over [start, end), both UTC-aware."""
    start: datetime
    end: datetime
    eur_mwh: float

    def c_kwh(self, vat_percent: float) -> float:
        """The price in c/kWh with VAT, as the screen shows it."""
        return to_c_kwh(self.eur_mwh, vat_percent)


@dataclass
class PriceData:
    """A parsed price response and when it was fetched (time.time())."""
    slots: list[PriceSlot]
    resolution_minutes: int
    fetched_at: float


@dataclass
class DayStats:
    """Min, max and time-weighted average of one local day, in c/kWh with VAT."""
    day: date
    min_price: float
    min_start: datetime
    max_price: float
    max_start: datetime
    avg_price: float


@dataclass
class PriceWindow:
    """A run of consecutive slots, e.g. the cheapest three hours."""
    start: datetime
    end: datetime
    avg_price: float


@dataclass
class Bar:
    """One chart bar: pixel columns [x0, x1) and its price in c/kWh with VAT."""
    x0: int
    x1: int
    start: datetime
    price: float
    is_current: bool


@dataclass
class PriceView:
    """Everything the price screen draws, worked out from one PriceData."""
    now: datetime
    current: Optional[PriceSlot] = None
    current_price: Optional[float] = None
    today: Optional[DayStats] = None
    tomorrow: Optional[DayStats] = None
    cheapest: Optional[PriceWindow] = None
    chart_start: Optional[datetime] = None
    chart_end: Optional[datetime] = None
    chart_slots: list[PriceSlot] = field(default_factory=list)
    fetched_at: Optional[float] = None
    stale: bool = False

    @property
    def has_data(self) -> bool:
        return self.current is not None or bool(self.chart_slots)


# =============================================================================
# PURE HELPERS
# =============================================================================

def to_c_kwh(eur_mwh: float, vat_percent: float) -> float:
    """EUR/MWh to c/kWh, with VAT on positive prices only.

    Negative prices are shown as they are, as Finnish spot-price services do:
    VAT is not refunded on them.
    """
    cents = eur_mwh / 10
    return cents * (1 + vat_percent / 100) if cents > 0 else cents


def format_price(value: float) -> str:
    """One decimal with a Finnish decimal comma: 8,4 or -0,3."""
    text = f"{value:.1f}"
    if text == "-0.0":
        text = "0.0"
    return text.replace(".", ",")


def parse_viewer_response(data: dict, fetched_at: Optional[float] = None) -> PriceData:
    """Read the viewer's JSON into slots, oldest first.

    Malformed or non-finite points are skipped. A slot ends where the next one
    starts, or after one resolution if the next one is further away (or there
    is none), so a gap in the data never stretches a price across it.
    """
    resolution = data.get("resolutionMinutes") or 15
    try:
        resolution = int(resolution)
    except (TypeError, ValueError):
        resolution = 15
    if resolution <= 0:
        resolution = 15
    step = timedelta(minutes=resolution)

    points: dict[int, float] = {}
    for point in data.get("points") or []:
        try:
            ms, price = int(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(price):
            points[ms] = price

    starts = sorted(points)
    slots = []
    for i, ms in enumerate(starts):
        start = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        end = start + step
        if i + 1 < len(starts):
            following = datetime.fromtimestamp(starts[i + 1] / 1000, tz=timezone.utc)
            end = min(end, following)
        slots.append(PriceSlot(start, end, points[ms]))

    return PriceData(
        slots=slots,
        resolution_minutes=resolution,
        fetched_at=time.time() if fetched_at is None else fetched_at,
    )


def current_slot(slots: list[PriceSlot], now: datetime) -> Optional[PriceSlot]:
    """The slot covering *now*, if any."""
    for slot in slots:
        if slot.start <= now < slot.end:
            return slot
    return None


def _weighted_average(slots: list[PriceSlot], vat_percent: float) -> float:
    total = sum((s.end - s.start).total_seconds() for s in slots)
    if total <= 0:
        return 0.0
    return sum(s.c_kwh(vat_percent) * (s.end - s.start).total_seconds() for s in slots) / total


def day_stats(slots: list[PriceSlot], day: date, vat_percent: float) -> Optional[DayStats]:
    """Stats over the slots starting on *day* in Finnish time.

    The day is taken from each slot's local start, so a 23- or 25-hour day at
    a daylight-saving change needs no special handling.
    """
    on_day = [s for s in slots if s.start.astimezone(HELSINKI).date() == day]
    if not on_day:
        return None
    cheapest = min(on_day, key=lambda s: s.eur_mwh)
    dearest = max(on_day, key=lambda s: s.eur_mwh)
    return DayStats(
        day=day,
        min_price=cheapest.c_kwh(vat_percent),
        min_start=cheapest.start,
        max_price=dearest.c_kwh(vat_percent),
        max_start=dearest.start,
        avg_price=_weighted_average(on_day, vat_percent),
    )


def cheapest_window(slots: list[PriceSlot], hours: float, now: datetime,
                    vat_percent: float) -> Optional[PriceWindow]:
    """The cheapest unbroken run of *hours* from the current slot onwards.

    Runs start on a slot boundary, beginning with the slot covering *now*, and
    never bridge a gap in the data. Ties go to the earliest run. None when the
    known prices do not reach *hours* ahead.
    """
    if hours <= 0:
        return None
    target = timedelta(hours=hours)
    upcoming = [s for s in slots if s.end > now]
    best: Optional[PriceWindow] = None

    for i, first in enumerate(upcoming):
        run = []
        covered = timedelta(0)
        for slot in upcoming[i:]:
            if run and slot.start != run[-1].end:
                break  # a gap in the data
            run.append(slot)
            covered += slot.end - slot.start
            if covered >= target:
                break
        if covered != target:
            continue  # ran out of data, or slots don't line up with the length
        avg = _weighted_average(run, vat_percent)
        if best is None or avg < best.avg_price - 1e-9:
            best = PriceWindow(first.start, run[-1].end, avg)
    return best


def chart_window(slots: list[PriceSlot], now: datetime,
                 chart_hours: int) -> Optional[tuple[datetime, datetime]]:
    """The span the chart covers: two hours back from the start of the current
    hour, through the last known price, at most *chart_hours* long."""
    if not slots:
        return None
    hour_start = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = hour_start - timedelta(hours=2)
    end = min(start + timedelta(hours=max(chart_hours, 1)), slots[-1].end)
    if end <= start:
        return None
    return start, end


def _hourly(slots: list[PriceSlot]) -> list[PriceSlot]:
    """Average finer slots into whole hours (weighted by length)."""
    groups: dict[datetime, list[PriceSlot]] = {}
    for slot in slots:
        groups.setdefault(slot.start.replace(minute=0, second=0, microsecond=0), []).append(slot)
    hourly = []
    for hour, group in sorted(groups.items()):
        total = sum((s.end - s.start).total_seconds() for s in group)
        avg = sum(s.eur_mwh * (s.end - s.start).total_seconds() for s in group) / total
        hourly.append(PriceSlot(hour, max(s.end for s in group), avg))
    return hourly


def chart_bars(slots: list[PriceSlot], start: datetime, end: datetime,
               x: int, width: int, now: datetime, vat_percent: float,
               min_bar_px: int = 3) -> list[Bar]:
    """Bars for the slots inside [start, end), placed by time across *width*
    pixels from *x*.

    When a bar would be narrower than *min_bar_px*, slots are averaged into
    hours first, so a long window stays readable on the panel.
    """
    span = (end - start).total_seconds()
    inside = [s for s in slots if s.start >= start and s.start < end]
    if not inside or span <= 0 or width <= 0:
        return []
    if width * (inside[0].end - inside[0].start).total_seconds() / span < min_bar_px:
        inside = _hourly(inside)

    def px(t: datetime) -> int:
        offset = min(max((t - start).total_seconds(), 0), span)
        return x + round(offset / span * width)

    return [
        Bar(
            x0=px(s.start),
            x1=max(px(min(s.end, end)), px(s.start) + 1),
            start=s.start,
            price=s.c_kwh(vat_percent),
            is_current=s.start <= now < s.end,
        )
        for s in inside
    ]


def nice_axis(low: float, high: float, ticks: int = 4) -> tuple[float, float, float]:
    """A y-axis range that includes zero, with a round step: (low, high, step)."""
    low, high = min(low, 0.0), max(high, 0.0)
    if high - low < 1e-9:
        high = low + 1
    raw = (high - low) / max(ticks, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return math.floor(low / step) * step, math.ceil(high / step) * step, step


def seconds_until_next_slot(now: datetime, resolution_minutes: int = 15, grace: int = 5) -> int:
    """Seconds from *now* to just after the next price period starts.

    Periods start on whole multiples of the resolution in UTC, which for 15
    and 60 minutes are the quarter-hours and hours of Finnish time too.
    *grace* seconds are added so the redraw lands inside the new period.
    """
    period = max(resolution_minutes, 1) * 60
    ts = now.timestamp()
    next_start = (math.floor(ts / period) + 1) * period
    return max(1, math.ceil(next_start - ts + grace))


def build_view(data: Optional[PriceData], settings: PricesConfig, now: datetime) -> PriceView:
    """Work out everything the screen shows at *now* (an aware datetime)."""
    now = now.astimezone(HELSINKI)
    view = PriceView(now=now)
    if data is None or not data.slots:
        return view

    vat = settings.vat_percent
    slots = data.slots
    view.fetched_at = data.fetched_at
    view.stale = time.time() - data.fetched_at > STALE_AFTER_SECONDS
    view.current = current_slot(slots, now)
    if view.current is not None:
        view.current_price = view.current.c_kwh(vat)
    view.today = day_stats(slots, now.date(), vat)
    view.tomorrow = day_stats(slots, now.date() + timedelta(days=1), vat)
    view.cheapest = cheapest_window(slots, settings.cheapest_window_hours, now, vat)
    window = chart_window(slots, now, settings.chart_hours)
    if window is not None:
        view.chart_start, view.chart_end = window
        view.chart_slots = [s for s in slots if window[0] <= s.start < window[1]]
    return view


# =============================================================================
# CLIENT
# =============================================================================

class PriceClient:
    """Fetches prices from the viewer, cached for `cache_minutes`.

    When a fetch fails, the last good prices are kept for as long as they
    still cover the present: prices are published a day ahead, so an outage
    of the viewer for hours leaves the screen correct.
    """

    # Network timeout (seconds) so a hung request never freezes the display loop.
    REQUEST_TIMEOUT = 15

    def __init__(self):
        self._data: Optional[PriceData] = None
        self._url: Optional[str] = None

    def fetch(self, settings: PricesConfig, now: Optional[datetime] = None) -> Optional[PriceData]:
        """Prices for *settings*, from the cache when fresh enough."""
        now = now or datetime.now(timezone.utc)
        cached = self._data if self._url == settings.source_url else None
        if cached is not None and time.time() - cached.fetched_at < settings.cache_minutes * 60:
            return cached

        try:
            response = requests.get(settings.source_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = parse_viewer_response(response.json())
        except (requests.RequestException, ValueError) as e:
            print(f"Price fetch failed: {e}", flush=True)
            if cached is not None and current_slot(cached.slots, now) is not None:
                return cached
            return None

        if not data.slots and cached is not None and current_slot(cached.slots, now) is not None:
            return cached  # an empty answer never replaces good prices
        self._data, self._url = data, settings.source_url
        return data


# Module-level singleton, like weather_client in weather.py.
price_client = PriceClient()


def current_prices(settings: PricesConfig) -> Optional[PriceData]:
    """Prices from the shared client; None when none are available."""
    return price_client.fetch(settings)
