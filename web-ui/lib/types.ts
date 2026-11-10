// Shapes of the backend's JSON (see ConfigModel / LayoutModel in api.py).

export interface Route {
    name: string;
    mode: string;
}

export interface Stop {
    id: string;
    name: string;
    routes?: Route[] | null;
}

export interface DisplaySettings {
    max_items: number;
    show_arrival_minutes_threshold: number;
    hide_arrival_before_minutes: number;
}

export interface WeatherSettings {
    enabled: boolean;
    location: string;
    cache_minutes: number;
}

// Which screen the panel shows (Config.screen in config.py).
export type Screen = "transit" | "prices";

// Spot-price screen settings (PricesConfig in config.py). Thresholds are in
// c/kWh including VAT.
export interface PricesSettings {
    source_url: string;
    vat_percent: number;
    cheap_threshold: number;
    expensive_threshold: number;
    cheapest_window_hours: number;
    chart_hours: number;
    cache_minutes: number;
}

// Layouts are edited and saved separately through /api/layout and
// /api/layout/prices, so the settings form neither needs nor sends them.
export interface Config {
    hsl_api_url: string;
    hsl_api_key: string;
    stops: Stop[];
    refresh_interval_seconds: number;
    epd_driver?: string;
    display: DisplaySettings;
    weather?: WeatherSettings;
    screen: Screen;
    prices: PricesSettings;
}

export interface LayoutConfig {
    top_line_y: number;
    line_gap: number;
    clock_x: number;
    clock_y: number;
    route_col_x: number;
    route_col_width: number;
    destination_col_x: number;
    time_col_x: number;
    time_col_width: number;
    header_y: number;
    alert_y: number;
    alert_width: number;
    font_clock: number;
    font_numbers: number;
    font_text: number;
    font_header: number;
    font_small: number;
    weather_x: number;
    weather_y: number;
}

export interface Arrival {
    route: string;
    destination: string;
    time: string;
}

export interface Alert {
    header: string;
    severity: string;
}

export interface ArrivalsData {
    arrivals: Arrival[];
    alerts: Alert[];
}

// Spot-price screen layout (PriceLayoutConfig in config.py), pixel values.
export interface PriceLayoutConfig {
    clock_x: number;
    clock_y: number;
    font_clock: number;
    date_y: number;
    price_x: number;
    price_y: number;
    font_price: number;
    font_unit: number;
    header_line_y: number;
    stats_x: number;
    stats_value_x: number;
    stats_y: number;
    stats_line_gap: number;
    font_stats: number;
    chart_x: number;
    chart_y: number;
    chart_width: number;
    chart_height: number;
    font_axis: number;
    weather_x: number;
    weather_y: number;
    font_small: number;
}

// GET /api/prices. Prices are c/kWh including VAT; times are ISO 8601 in
// Finnish time.
export interface PriceStats {
    min: number;
    min_at: string;
    avg: number;
    max: number;
    max_at: string;
}

export interface PricesData {
    current: { start: string; end: string; price: number } | null;
    today: PriceStats | null;
    tomorrow: PriceStats | null;
    cheapest: { hours: number; start: string; end: string; avg: number } | null;
    points: { start: string; price: number }[];
    cheap_threshold: number;
    expensive_threshold: number;
    fetched_at: string;
    stale: boolean;
}
