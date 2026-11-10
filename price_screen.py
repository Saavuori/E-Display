"""
Drawing for the electricity spot-price screen.

Draws a `PriceView` (see prices.py) into the panel's black and red 1-bit
layers with PIL primitives only: no greyscale or anti-aliasing survives the
e-ink palette. Every position comes from `PriceLayoutConfig`.
"""

import os
from datetime import datetime, timedelta, timezone

from PIL import ImageDraw, ImageFont

from config import DISPLAY_WIDTH, FONT_DIR, PriceLayoutConfig, PricesConfig
from prices import HELSINKI, PriceView, chart_bars, format_price, nice_axis

BLACK = 0
WEEKDAYS = ("ma", "ti", "ke", "to", "pe", "la", "su")


class PriceFonts:
    """The fonts the price screen uses, sized from its layout."""

    def __init__(self, layout: PriceLayoutConfig, font_dir: str = FONT_DIR):
        path = os.path.join(font_dir, 'Font.ttc')
        self.clock = ImageFont.truetype(path, layout.font_clock)
        self.price = ImageFont.truetype(path, layout.font_price)
        self.unit = ImageFont.truetype(path, layout.font_unit)
        self.stats = ImageFont.truetype(path, layout.font_stats)
        self.axis = ImageFont.truetype(path, layout.font_axis)
        self.small = ImageFont.truetype(path, layout.font_small)


def _local(t: datetime) -> datetime:
    return t.astimezone(HELSINKI)


def _hhmm(t: datetime) -> str:
    return _local(t).strftime("%H:%M")


def _date_text(t: datetime) -> str:
    t = _local(t)
    return f"{WEEKDAYS[t.weekday()]} {t.day}.{t.month}."


def draw_price_screen(draw_bw: ImageDraw.ImageDraw, draw_red: ImageDraw.ImageDraw,
                      view: PriceView, settings: PricesConfig,
                      layout: PriceLayoutConfig, fonts: PriceFonts) -> None:
    """Draw the whole price screen except the weather overlay."""
    _draw_header(draw_bw, draw_red, view, settings, layout, fonts)
    draw_red.line([(0, layout.header_line_y), (DISPLAY_WIDTH, layout.header_line_y)], fill=BLACK, width=4)

    if not view.has_data:
        draw_bw.text((DISPLAY_WIDTH // 2, layout.chart_y + layout.chart_height // 2),
                     "Hintatietoja ei saatavilla", font=fonts.stats, fill=BLACK, anchor="mm")
        return

    _draw_stats(draw_bw, view, settings, layout, fonts)
    _draw_chart(draw_bw, draw_red, view, settings, layout, fonts)


def _draw_header(draw_bw, draw_red, view: PriceView, settings: PricesConfig,
                 layout: PriceLayoutConfig, fonts: PriceFonts) -> None:
    draw_bw.text((layout.clock_x, layout.clock_y), view.now.strftime("%H:%M"),
                 font=fonts.clock, fill=BLACK, anchor="la")
    draw_bw.text((layout.clock_x + 2, layout.date_y), _date_text(view.now),
                 font=fonts.small, fill=BLACK, anchor="la")

    if view.current_price is None:
        price_text, target = "–", draw_bw
    else:
        price_text = format_price(view.current_price)
        target = draw_red if view.current_price >= settings.expensive_threshold else draw_bw
    target.text((layout.price_x, layout.price_y), price_text, font=fonts.price, fill=BLACK, anchor="ra")

    # The unit sits on the number's baseline, just right of it.
    baseline = layout.price_y + fonts.price.getmetrics()[0]
    draw_bw.text((layout.price_x + 10, baseline), "c/kWh", font=fonts.unit, fill=BLACK, anchor="ls")

    if view.current is not None:
        label = f"nyt {_hhmm(view.current.start)}–{_hhmm(view.current.end)}"
        draw_bw.text((layout.price_x + 10, baseline + 6), label, font=fonts.small, fill=BLACK, anchor="la")

    if view.stale and view.fetched_at is not None:
        fetched = datetime.fromtimestamp(view.fetched_at, tz=timezone.utc)
        draw_red.text((layout.weather_x, layout.date_y), f"päivitetty {_hhmm(fetched)}",
                      font=fonts.small, fill=BLACK, anchor="ra")


def _draw_stats(draw_bw, view: PriceView, settings: PricesConfig,
                layout: PriceLayoutConfig, fonts: PriceFonts) -> None:
    def line(row: int, label: str, text: str) -> None:
        y = layout.stats_y + row * layout.stats_line_gap
        draw_bw.text((layout.stats_x, y), label, font=fonts.stats, fill=BLACK, anchor="la")
        draw_bw.text((layout.stats_value_x, y), text, font=fonts.stats, fill=BLACK, anchor="la")

    def stats_text(stats) -> str:
        return (f"min {format_price(stats.min_price)} ({_hhmm(stats.min_start)})   "
                f"ka {format_price(stats.avg_price)}   "
                f"max {format_price(stats.max_price)} ({_hhmm(stats.max_start)})")

    if view.today is not None:
        line(0, "Tänään", stats_text(view.today))
    if view.tomorrow is not None:
        line(1, "Huomenna", stats_text(view.tomorrow))
    else:
        line(1, "Huomenna", "hinnat julkaistaan noin klo 14")
    hours = settings.cheapest_window_hours
    if view.cheapest is not None:
        window = view.cheapest
        # Name the day unless the window starts today.
        day = "" if _local(window.start).date() == view.now.date() else f"{WEEKDAYS[_local(window.start).weekday()]} "
        line(2, f"Halvin {hours} h",
             f"{day}{_hhmm(window.start)}–{_hhmm(window.end)}   ka {format_price(window.avg_price)}")


def _dotted_hline(draw, x0: int, x1: int, y: int, on: int = 2, off: int = 6, width: int = 1) -> None:
    for x in range(x0, x1, on + off):
        draw.line([(x, y), (min(x + on - 1, x1), y)], fill=BLACK, width=width)


def _draw_chart(draw_bw, draw_red, view: PriceView, settings: PricesConfig,
                layout: PriceLayoutConfig, fonts: PriceFonts) -> None:
    if view.chart_start is None or view.chart_end is None:
        return
    vat = settings.vat_percent
    x0, top = layout.chart_x, layout.chart_y
    width, height = layout.chart_width, layout.chart_height
    bottom = top + height
    bars = chart_bars(view.chart_slots, view.chart_start, view.chart_end,
                      x0, width, view.now, vat)
    if not bars:
        return

    # Leave headroom above the tallest bar for the current-slot marker.
    low, high, step = nice_axis(min(b.price for b in bars), max(b.price for b in bars))
    marker = 10
    plot_top = top + marker + 4

    def y(value: float) -> int:
        return round(plot_top + (high - value) / (high - low) * (bottom - plot_top))

    # Gridlines and their labels
    tick = low
    while tick <= high + 1e-9:
        ty = y(tick)
        if abs(tick) < 1e-9:
            draw_bw.line([(x0, ty), (x0 + width, ty)], fill=BLACK, width=1)
        else:
            _dotted_hline(draw_bw, x0, x0 + width, ty)
        label = f"{tick:g}".replace(".", ",")
        draw_bw.text((x0 - 6, ty), label, font=fonts.axis, fill=BLACK, anchor="rm")
        tick += step

    # Bars: expensive ones solid red, cheap ones outlined, the rest solid
    # black; the current one gets a red marker on top.
    zero = y(0)
    for bar in bars:
        gap = 1 if bar.x1 - bar.x0 >= 4 else 0
        left, right = bar.x0 + gap, max(bar.x1 - 1 - gap, bar.x0)
        top_y, bottom_y = sorted((y(bar.price), zero))
        box = [left, top_y, right, max(bottom_y, top_y + 1)]
        if bar.price >= settings.expensive_threshold:
            draw_red.rectangle(box, fill=BLACK)
        elif bar.price <= settings.cheap_threshold and right - left >= 2:
            draw_bw.rectangle(box, outline=BLACK, width=1)
        else:
            draw_bw.rectangle(box, fill=BLACK)
        if bar.is_current:
            centre = (left + right) // 2
            tip = top_y - 3
            draw_red.polygon([(centre - marker // 2 - 2, tip - marker), (centre + marker // 2 + 2, tip - marker),
                              (centre, tip)], fill=BLACK)

    # Average over the chart as a dashed black line
    avg = sum(b.price * (b.x1 - b.x0) for b in bars) / max(sum(b.x1 - b.x0 for b in bars), 1)
    _dotted_hline(draw_bw, x0, x0 + width, y(avg), on=8, off=6, width=2)

    span = (view.chart_end - view.chart_start).total_seconds()

    def px(t: datetime) -> int:
        return x0 + round((t - view.chart_start).total_seconds() / span * width)

    # Hour labels every three hours, a solid line and the weekday at midnight
    hour = _local(view.chart_start).replace(minute=0, second=0, microsecond=0)
    end_local = _local(view.chart_end)
    while hour <= end_local:
        x = px(hour)
        if hour.hour == 0 and x > x0:
            draw_bw.line([(x, top), (x, bottom)], fill=BLACK, width=2)
            label = _date_text(hour)
            if x + 4 + fonts.axis.getlength(label) <= DISPLAY_WIDTH:  # never cut off at the edge
                draw_bw.text((x + 4, top), label, font=fonts.axis, fill=BLACK, anchor="la")
        if hour.hour % 3 == 0 and x0 <= x <= x0 + width:
            draw_bw.line([(x, bottom), (x, bottom + 4)], fill=BLACK, width=1)
            draw_bw.text((x, bottom + 6), f"{hour.hour:02d}", font=fonts.axis, fill=BLACK, anchor="mt")
        # Step in UTC so a daylight-saving change neither repeats nor skips an hour.
        hour = _local(hour.astimezone(timezone.utc) + timedelta(hours=1))

    # Cheapest window as a red bracket along the bottom of the plot
    if view.cheapest is not None:
        left = max(px(view.cheapest.start), x0)
        right = min(px(view.cheapest.end), x0 + width)
        if right > left:
            draw_red.rectangle([left, bottom - 1, right, bottom + 3], fill=BLACK)
