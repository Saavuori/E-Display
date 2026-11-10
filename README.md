# E-Display

**[📖 Project site — saavuori.github.io/E-Display](https://saavuori.github.io/E-Display/)**

**E-Display** is a smart, e-ink public transport display for Helsinki Regional Transport (HSL) data that can also show Finnish electricity spot prices. It is designed to run on a Raspberry Pi connected to a Waveshare 7.5" E-Ink display (Black/White/Red).

The project consists of two main components:
1.  **Backend**: A Python application that fetches data from the HSL API, renders the schedule, and updates the e-ink display. It also provides a REST API for configuration.
2.  **Web UI**: A modern Next.js web application for configuring stops, customizing the layout, and previewing what the display will look like in real-time.

## Features

-   **Real-time Departures**: Shows upcoming bus/tram/train departures for configured stops.
-   **Spot Prices**: A second screen with the current Finnish electricity price (c/kWh incl. VAT), today's and tomorrow's min/avg/max, the cheapest hours ahead and a 36-hour chart. Switch between the two screens in the web UI.
-   **E-Ink Support**: Optimized for Waveshare 7.5" E-Ink displays (supports 3-color rendering).
-   **Web Configuration**: Easy-to-use web interface to search for stops and manage settings.
-   **Live Preview**: visual editor to adjust the layout and see how it will look on the actual screen.
-   **Visual Layout Editor**: Drag-and-drop or slider-based adjustments for all display elements.
-   **Alerts**: Displays disruption alerts from HSL.
-   **Dockerized**: Easy deployment using Docker Compose.

## Screenshots

### E-Ink Display Preview
![Display Preview](screenshots/preview.png)
*Real-time departure view generated for the 7.5" E-Ink Display*

### Web Configuration UI
![Web Dashboard](screenshots/webui.png)
*Modern dashboard for managing stops, layout, and settings*

## Hardware Requirements

-   **Raspberry Pi** (Zero W, 3, or 4 recommended).
-   **Waveshare 7.5" E-Paper Display (B)** (Black/White/Red) or compatible.
-   **MicroSD Card** for the OS.

## Quick Start (Docker)

The easiest way to run E-Display is using Docker.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Saavuori/E-Display.git
    cd E-Display
    ```

2.  **Configure API Key:**
    You need an API key from the [Digitransit](https://portal-api.digitransit.fi/).
    Create a `.env` file in the root directory:
    ```bash
    HSL_API_KEY=your_hsl_api_key_here
    ```

3.  **Run with Docker Compose:**
    ```bash
    docker-compose up -d
    ```

    This will start:
    -   **Backend API** on port `8000`.
    -   **Web UI** on port `3000`.
    -   **Display Driver** (runs the e-ink screen).

4.  **Access the Web UI:**
    Open `http://<your-pi-ip>:3000` in your browser to configure your stops and layout.

## Development Setup

### Backend (Python)

Dependencies are managed with [uv](https://docs.astral.sh/uv/). Install it once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

1.  Create the environment and install dependencies:
    ```bash
    uv sync
    ```
    This creates `.venv/` using the Python version pinned in `.python-version`,
    downloading it automatically if you don't have it. On a Raspberry Pi, add
    the hardware extra to pull in `RPi.GPIO` and `spidev`:
    ```bash
    uv sync --extra pi
    ```

2.  Run the API server:
    ```bash
    uv run python api.py
    ```
    The API will be available at `http://localhost:8000`.

3.  Run the Display script (standalone):
    ```bash
    uv run python display.py
    ```
    *Note: On non-Raspberry Pi systems, this will run in "Mock Mode" and generate a preview image instead of driving hardware.*

### Frontend (Next.js)

1.  Navigate to the web-ui directory:
    ```bash
    cd web-ui
    ```

2.  Install dependencies:
    ```bash
    npm install
    ```

3.  Run the development server:
    ```bash
    npm run dev
    ```
    The UI will be available at `http://localhost:3000`.

## Testing

The backend has a unit-test suite that runs without hardware or network access
(the e-ink driver falls back to a mock automatically):

```bash
uv run pytest
```

## Configuration

Configuration is stored in `config.json` in the root directory. You can edit this file manually or use the Web UI.

**Example `config.json`:**
```json
{
    "hsl_api_url": "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1",
    "hsl_api_key": "YOUR_API_KEY",
    "stops": [
        {
            "id": "HSL:123456",
            "name": "My Stop",
            "routes": null
        }
    ],
    "refresh_interval_seconds": 300,
    "display": {
        "max_items": 5,
        "show_arrival_minutes_threshold": 10,
        "hide_arrival_before_minutes": 0
    },
    "layout": {
        "top_line_y": 90,
        "line_gap": 60,
        "clock_x": 400,
        "clock_y": 10,
        ...
    }
}
```

### Spot-price screen

Set `"screen": "prices"` (or pick **Spot prices** in the web UI) to show
electricity prices instead of departures. The panel then redraws at every
quarter-hour, when a new price period starts.

```json
{
    "screen": "prices",
    "prices": {
        "source_url": "https://fingrid.saavuori.live/api/prices",
        "vat_percent": 25.5,
        "cheap_threshold": 5.0,
        "expensive_threshold": 20.0,
        "cheapest_window_hours": 3,
        "chart_hours": 36,
        "cache_minutes": 15
    }
}
```

Prices are the day-ahead prices for Finland from the
[ENTSO-E Transparency Platform](https://transparency.entsoe.eu), read through
the public `/api/prices` endpoint of
[fingrid-data-collector](https://github.com/Saavuori/fingrid-data-collector)'s
viewer. The viewer holds the ENTSO-E token, so the Pi needs none. Thresholds
are in c/kWh including VAT. VAT is added to positive prices only. Tomorrow's
prices appear after they are published, around 14:00 Finnish time. The price
screen's positions and font sizes live in `price_layout` and are edited in the
web UI.

## License

[MIT](LICENSE)