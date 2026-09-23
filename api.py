"""
FastAPI backend for E-Display configuration and preview.

Endpoints are plain `def`, not `async def`: they make blocking HTTP calls
(HSL, FMI, geocoding) and render with PIL, so FastAPI runs them in its
threadpool instead of stalling the event loop for every other request.
"""

import os
import time
import base64
import threading
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

# Import from config module
from config import (
    REFRESH_TRIGGER_FILE, TRIGGER_DIR,
    load_config, save_config, Config as ConfigData,
    StopConfig, DisplaySettings, LayoutConfig, WeatherConfig
)

# Import display engine components (importing display also puts lib/ on sys.path)
from display import HSLClient, DisplayRenderer
from waveshare_epd import epd_mock
from weather import current_weather, weather_client

app = FastAPI(title="E-Display API", version=os.environ.get("APP_VERSION", "dev"))

# Enable CORS for Next.js frontend.
# The API uses no cookies/credentials, so allow_credentials must be False —
# browsers reject the wildcard origin when credentials are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = Path(__file__).parent
# Where epd_mock.EPD.display() writes its composite image.
PREVIEW_FILE = BASE_DIR / "preview.png"

# Previews render into shared files (pic/*.png and preview.png); requests now
# run in parallel threads, so renders are serialised to keep reads whole.
_preview_lock = threading.Lock()


# =============================================================================
# PYDANTIC MODELS (for API validation)
# =============================================================================

class RouteModel(BaseModel):
    name: str
    mode: str

class StopModel(BaseModel):
    id: str
    name: str
    routes: list[RouteModel] | None = None

class DisplayModel(BaseModel):
    max_items: int = 5
    show_arrival_minutes_threshold: int = 10
    hide_arrival_before_minutes: int = 10

class LayoutModel(BaseModel):
    """Layout configuration model."""
    top_line_y: int = 90
    line_gap: int = 60
    clock_x: int = 400
    clock_y: int = 10
    route_col_x: int = 40
    route_col_width: int = 100
    destination_col_x: int = 100
    time_col_x: int = 770
    time_col_width: int = 180
    header_y: int = 50
    alert_y: int = 390
    alert_width: int = 780
    font_clock: int = 100
    font_numbers: int = 60
    font_text: int = 30
    font_header: int = 30
    font_small: int = 22
    weather_x: int = 790
    weather_y: int = 15

class WeatherModel(BaseModel):
    enabled: bool = True
    location: str = "Helsinki"
    cache_minutes: int = 30

class ConfigModel(BaseModel):
    hsl_api_url: str
    hsl_api_key: str
    stops: list[StopModel] = []
    refresh_interval_seconds: int = 300
    epd_driver: str = "epd7in5b_V2"
    display: DisplayModel = DisplayModel()
    # The layout editor owns the layout (PUT /api/layout). When omitted, the
    # saved layout is kept, so a settings save can't revert layout edits.
    layout: LayoutModel | None = None
    weather: WeatherModel | None = None


# =============================================================================
# PREVIEW GENERATION
# =============================================================================

def generate_preview() -> bytes:
    """Render a preview of the display and return it as PNG bytes."""
    config = load_config()

    # Weather is cached, so this is fast on subsequent calls
    weather = current_weather(config.weather)

    hsl_client = HSLClient(config.hsl_api_url, config.hsl_api_key)
    stop_ids = [s.id for s in config.stops]
    try:
        min_seconds = config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = hsl_client.fetch_arrivals(stop_ids, min_seconds)
    except Exception as e:
        print(f"Error fetching HSL data: {e}")
        arrivals, alerts = [], []

    with _preview_lock:
        renderer = DisplayRenderer.from_config(epd_mock.EPD(), config)
        image_bw, image_red = renderer.render_schedule(arrivals, alerts, weather=weather)
        renderer.write_to_screen(image_bw, image_red)
        return PREVIEW_FILE.read_bytes()


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/api/config")
def get_config():
    """Get current configuration."""
    config = load_config()
    return config.to_dict()

@app.post("/api/config")
def update_config(config: ConfigModel):
    """Update configuration."""
    if config.layout is not None:
        layout = LayoutConfig.from_dict(config.layout.model_dump())
    else:
        layout = load_config().layout
    weather = WeatherConfig(**config.weather.model_dump()) if config.weather else WeatherConfig()
    config_data = ConfigData(
        hsl_api_url=config.hsl_api_url,
        hsl_api_key=config.hsl_api_key,
        stops=[StopConfig(
            id=s.id,
            name=s.name,
            routes=[{'name': r.name, 'mode': r.mode} for r in s.routes] if s.routes else None
        ) for s in config.stops],
        refresh_interval_seconds=config.refresh_interval_seconds,
        epd_driver=config.epd_driver,
        display=DisplaySettings(**config.display.model_dump()),
        layout=layout,
        weather=weather,
    )
    save_config(config_data)
    return {"status": "ok", "message": "Configuration saved"}

@app.get("/api/preview")
def get_preview():
    """Generate and return preview image."""
    return Response(
        content=generate_preview(),
        media_type="image/png",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/api/preview/base64")
def get_preview_base64():
    """Generate and return preview as base64 for easy embedding."""
    image_data = base64.b64encode(generate_preview()).decode('utf-8')
    return {"image": f"data:image/png;base64,{image_data}"}

@app.post("/api/refresh")
def refresh_display():
    """Trigger a display refresh (both preview and physical screen)."""
    # Generate preview
    generate_preview()

    # Create trigger file to signal display.py to refresh the physical screen
    try:
        os.makedirs(TRIGGER_DIR, exist_ok=True)
        with open(REFRESH_TRIGGER_FILE, 'w') as f:
            f.write('refresh')
        physical_triggered = True
    except Exception as e:
        print(f"Could not create trigger file: {e}")
        physical_triggered = False

    return {
        "status": "ok",
        "message": "Display refreshed",
        "physical_display_triggered": physical_triggered
    }

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/version")
def get_version():
    """Return build version information injected at Docker build time."""
    return {
        "version":    os.environ.get("APP_VERSION", "dev"),
        "build_date": os.environ.get("APP_BUILD_DATE", ""),
        "git_sha":    os.environ.get("APP_GIT_SHA", ""),
    }


@app.get("/api/weather")
def get_weather():
    """Get current weather from FMI for the configured location."""
    config = load_config()
    if not config.weather.enabled:
        return {"enabled": False, "temperature": None, "description": None, "location": None}

    try:
        data = weather_client.fetch_current(config.weather.location, config.weather.cache_minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if data is None:
        raise HTTPException(status_code=503, detail="Weather data unavailable")
    return {
        "enabled": True,
        "temperature": data.temperature,
        "description": data.description,
        "location": data.location,
    }


@app.get("/api/arrivals")
def get_arrivals():
    """Get current bus arrivals for the layout editor."""
    config = load_config()

    hsl_client = HSLClient(config.hsl_api_url, config.hsl_api_key)
    stop_ids = [s.id for s in config.stops]

    try:
        min_seconds = config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = hsl_client.fetch_arrivals(stop_ids, min_seconds)
    except Exception as e:
        print(f"Error fetching arrivals: {e}")
        return {"arrivals": [], "alerts": [], "error": str(e)}

    now = time.time()
    threshold = config.display.show_arrival_minutes_threshold
    return {
        "arrivals": [
            {"route": bus.route, "destination": bus.headsign, "time": bus.display_time(now, threshold)}
            for bus in arrivals[:config.display.max_items]
        ],
        "alerts": [{"header": a.header_text, "severity": a.severity_level} for a in alerts]
    }


@app.get("/api/stops/search")
def search_stops(
    q: str = Query(..., description="Address or location to search near"),
    radius: int = Query(500, description="Search radius in meters")
):
    """Search for stops near an address."""
    config = load_config()
    api_key = config.hsl_api_key

    if not api_key:
        raise HTTPException(status_code=400, detail="HSL API key not configured")

    headers = {"digitransit-subscription-key": api_key}

    # Step 1: Geocode the address to get coordinates. params= URL-encodes the
    # text, so an address containing '&' or '#' is not cut short.
    try:
        geo_response = requests.get(
            "https://api.digitransit.fi/geocoding/v1/search",
            params={"text": q, "size": 1},
            headers=headers,
            timeout=15,
        )
        geo_response.raise_for_status()
        geo_data = geo_response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Geocoding failed: {str(e)}")

    features = geo_data.get("features", [])
    if not features:
        return {"stops": [], "message": "No location found for this address"}

    # Get coordinates from first result
    coords = features[0]["geometry"]["coordinates"]
    lon, lat = coords[0], coords[1]
    location_name = features[0]["properties"].get("label", q)

    # Step 2: Search for stops near those coordinates using GraphQL
    query = f'''
    {{
        stopsByRadius(lat: {lat}, lon: {lon}, radius: {radius}) {{
            edges {{
                node {{
                    stop {{
                        gtfsId
                        name
                        code
                        lat
                        lon
                        routes {{
                            shortName
                            mode
                        }}
                    }}
                    distance
                }}
            }}
        }}
    }}
    '''

    try:
        stops_response = requests.post(
            config.hsl_api_url,
            headers={**headers, "Content-Type": "application/json"},
            json={"query": query},
            timeout=15,
        )
        stops_response.raise_for_status()
        stops_data = stops_response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Stop search failed: {str(e)}")

    # Parse the response
    edges = stops_data.get("data", {}).get("stopsByRadius", {}).get("edges", [])

    stops = []
    for edge in edges:
        node = edge.get("node", {})
        stop = node.get("stop", {})
        routes = stop.get("routes", [])

        stops.append({
            "id": stop.get("gtfsId"),
            "name": stop.get("name"),
            "code": stop.get("code"),
            "lat": stop.get("lat"),
            "lon": stop.get("lon"),
            "distance": node.get("distance"),
            "routes": [{"name": r.get("shortName"), "mode": r.get("mode")} for r in routes]
        })

    return {
        "location": location_name,
        "coordinates": {"lat": lat, "lon": lon},
        "radius": radius,
        "stops": stops
    }


@app.get("/api/layout")
def get_layout():
    """Get current layout configuration."""
    config = load_config()
    return config.layout.to_dict()


@app.put("/api/layout")
def update_layout(layout: LayoutModel):
    """Update layout configuration."""
    config = load_config()
    config.layout = LayoutConfig.from_dict(layout.model_dump())
    save_config(config)
    return {"status": "ok", "message": "Layout saved"}


if __name__ == "__main__":
    import uvicorn
    # reload needs the app as an import string; passing the object makes
    # uvicorn log an error and exit.
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
