// Formatting for spot prices, matching what the e-paper screen shows.

// One decimal with a Finnish decimal comma: 8,4 or -0,3.
export function formatPrice(value: number): string {
    const text = value.toFixed(1);
    return (text === "-0.0" ? "0.0" : text).replace(".", ",");
}

// HH:MM of an ISO time from the API. The API already gives Finnish local
// time with its offset, so this reads it as written whatever the browser's
// own time zone is.
export function hhmm(iso: string): string {
    return iso.slice(11, 16);
}

// The calendar date (YYYY-MM-DD) of an ISO time from the API, in Finnish time.
export function isoDate(iso: string): string {
    return iso.slice(0, 10);
}

export type PriceLevel = "cheap" | "normal" | "expensive";

export function priceLevel(price: number, cheap: number, expensive: number): PriceLevel {
    if (price >= expensive) return "expensive";
    if (price <= cheap) return "cheap";
    return "normal";
}
