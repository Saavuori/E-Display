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

// The layout is edited and saved separately through /api/layout, so the
// settings form neither needs nor sends it.
export interface Config {
    hsl_api_url: string;
    hsl_api_key: string;
    stops: Stop[];
    refresh_interval_seconds: number;
    epd_driver?: string;
    display: DisplaySettings;
    weather?: WeatherSettings;
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
