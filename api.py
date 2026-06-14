"""
FastAPI backend for E-Display configuration and preview.
"""

import os
import base64
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Import from config module
from config import (
    PIC_DIR, FONT_DIR, REFRESH_TRIGGER_FILE, TRIGGER_DIR,
    load_config, save_config, Config as ConfigData,
    Fonts, StopConfig, DisplaySettings, LayoutConfig, WeatherConfig
)

# Import display engine components
import sys
sys.path.append('lib')
from display import HSLClient, DisplayRenderer, BusArrival, Alert, PREVIEW_MODE
from waveshare_epd import epd_mock
from weather import weather_client, WeatherData

app = FastAPI(title="E-Display API", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = Path(__file__).parent
PREVIEW_FILE = BASE_DIR / "preview.png"


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

class ConfigModel(BaseModel):
    hsl_api_url: str
    hsl_api_key: str
    stops: list[StopModel] = []
    refresh_interval_seconds: int = 300
    display: DisplayModel = DisplayModel()
    layout: LayoutModel = LayoutModel()
    weather: 'WeatherModel | None' = None


class WeatherModel(BaseModel):
    enabled: bool = True
    location: str = "Helsinki"
    cache_minutes: int = 30


ConfigModel.model_rebuild()


# =============================================================================
# PREVIEW GENERATION
# =============================================================================

def generate_preview() -> str:
    """Generate preview image and return path."""
    config = load_config()
    
    # Initialize components
    # Initialize components
    epd = epd_mock.EPD()
    fonts = Fonts(layout=config.layout)
    renderer = DisplayRenderer(
        epd, fonts, PIC_DIR,
        layout=config.layout,
        max_items=config.display.max_items,
        show_minutes_threshold=config.display.show_arrival_minutes_threshold
    )
    
    # Fetch weather (uses shared cache — fast on subsequent calls)
    current_weather = None
    if config.weather.enabled:
        try:
            weather_client._cache_minutes = config.weather.cache_minutes
            current_weather = weather_client.fetch_current(config.weather.location)
        except Exception as exc:
            print(f"Weather fetch failed in preview: {exc}")

    # Fetch bus data
    hsl_client = HSLClient(config.hsl_api_url, config.hsl_api_key)
    stop_ids = [s.id for s in config.stops]
    
    try:
        responses = hsl_client.fetch_stop_data(stop_ids)
        min_seconds = config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = hsl_client.parse_arrivals(responses, min_seconds)
    except Exception as e:
        print(f"Error fetching HSL data: {e}")
        arrivals, alerts = [], []
    
    # Render preview
    output_bw, output_red = renderer.render_schedule(arrivals, alerts, weather=current_weather)
    renderer.write_to_screen(output_bw, output_red)
    
    return str(PREVIEW_FILE)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    config = load_config()
    return config.to_dict()

@app.post("/api/config")
async def update_config(config: ConfigModel):
    """Update configuration."""
    # Convert Pydantic model to dataclass
    layout_data = config.layout.model_dump() if config.layout else {}
    weather_cfg = WeatherConfig(
        enabled=config.weather.enabled if config.weather else True,
        location=config.weather.location if config.weather else "Helsinki",
        cache_minutes=config.weather.cache_minutes if config.weather else 30,
    )
    # Invalidate weather cache if location changed
    if config.weather:
        weather_client.invalidate(config.weather.location)
    config_data = ConfigData(
        hsl_api_url=config.hsl_api_url,
        hsl_api_key=config.hsl_api_key,
        stops=[StopConfig(
            id=s.id, 
            name=s.name, 
            routes=[{'name': r.name, 'mode': r.mode} for r in s.routes] if s.routes else None
        ) for s in config.stops],
        refresh_interval_seconds=config.refresh_interval_seconds,
        display=DisplaySettings(
            max_items=config.display.max_items,
            show_arrival_minutes_threshold=config.display.show_arrival_minutes_threshold,
            hide_arrival_before_minutes=config.display.hide_arrival_before_minutes
        ),
        layout=LayoutConfig.from_dict(layout_data),
        weather=weather_cfg,
    )
    save_config(config_data)
    return {"status": "ok", "message": "Configuration saved"}

@app.get("/api/preview")
async def get_preview():
    """Generate and return preview image."""
    preview_path = generate_preview()
    
    if not os.path.exists(preview_path):
        raise HTTPException(status_code=500, detail="Failed to generate preview")
    
    return FileResponse(
        preview_path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/api/preview/base64")
async def get_preview_base64():
    """Generate and return preview as base64 for easy embedding."""
    preview_path = generate_preview()
    
    with open(preview_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    return {"image": f"data:image/png;base64,{image_data}"}

@app.post("/api/refresh")
async def refresh_display():
    """Trigger a display refresh (both preview and physical screen)."""
    # Generate preview
    generate_preview()
    
    # Create trigger file to signal display.py to refresh the physical screen
    try:
        if not os.path.exists(TRIGGER_DIR):
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
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/version")
async def get_version():
    """Return build version information injected at Docker build time."""
    return {
        "version":    os.environ.get("APP_VERSION", "dev"),
        "build_date": os.environ.get("APP_BUILD_DATE", ""),
        "git_sha":    os.environ.get("APP_GIT_SHA", ""),
    }


@app.get("/api/weather")
async def get_weather():
    """Get current weather from FMI for the configured location."""
    config = load_config()
    if not config.weather.enabled:
        return {"enabled": False, "temperature": None, "description": None, "location": None}

    try:
        weather_client._cache_minutes = config.weather.cache_minutes
        data = weather_client.fetch_current(config.weather.location)
        if data is None:
            raise HTTPException(status_code=503, detail="Weather data unavailable")
        return {
            "enabled": True,
            "temperature": data.temperature,
            "description": data.description,
            "location": data.location,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/arrivals")
async def get_arrivals():
    """Get current bus arrivals for the layout editor."""
    config = load_config()
    
    hsl_client = HSLClient(config.hsl_api_url, config.hsl_api_key)
    stop_ids = [s.id for s in config.stops]
    
    try:
        responses = hsl_client.fetch_stop_data(stop_ids)
        min_seconds = config.display.hide_arrival_before_minutes * 60
        arrivals, alerts = hsl_client.parse_arrivals(responses, min_seconds)
        
        # Get current time for minutes calculation
        current_seconds = HSLClient._seconds_since_midnight()
        
        # Format arrivals for the layout editor
        arrivals_data = []
        for bus in arrivals[:config.display.max_items]:
            minutes_away = bus.minutes_until_arrival(current_seconds)
            if minutes_away < config.display.show_arrival_minutes_threshold:
                time_text = f"{int(minutes_away)}"
            else:
                time_text = bus.formatted_time()
            
            arrivals_data.append({
                "route": bus.route,
                "destination": bus.headsign,
                "time": time_text
            })
        
        return {
            "arrivals": arrivals_data,
            "alerts": [{"header": a.header_text, "severity": a.severity_level} for a in alerts]
        }
    except Exception as e:
        print(f"Error fetching arrivals: {e}")
        return {"arrivals": [], "alerts": [], "error": str(e)}


@app.get("/api/stops/search")
async def search_stops(
    q: str = Query(..., description="Address or location to search near"),
    radius: int = Query(500, description="Search radius in meters")
):
    """Search for stops near an address."""
    config = load_config()
    api_key = config.hsl_api_key
    
    if not api_key:
        raise HTTPException(status_code=400, detail="HSL API key not configured")
    
    headers = {"digitransit-subscription-key": api_key}
    
    # Step 1: Geocode the address to get coordinates
    geocode_url = f"https://api.digitransit.fi/geocoding/v1/search?text={q}&size=1"
    try:
        geo_response = requests.get(geocode_url, headers=headers)
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
    graphql_url = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
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
            graphql_url,
            headers={**headers, "Content-Type": "application/json"},
            json={"query": query}
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
async def get_layout():
    """Get current layout configuration."""
    config = load_config()
    return config.layout.to_dict()


@app.put("/api/layout")
async def update_layout(layout: LayoutModel):
    """Update layout configuration."""
    config = load_config()
    config.layout = LayoutConfig.from_dict(layout.model_dump())
    save_config(config)
    return {"status": "ok", "message": "Layout saved"}


@app.get("/api/layout/elements")
async def get_layout_elements():
    """Get layout elements with their positions for the visual editor."""
    config = load_config()
    layout = config.layout
    max_items = config.display.max_items
    
    def calc_x(x: int, width: int, anchor: str) -> int:
        """Calculate actual x position based on anchor type.
        First character: l=left, m=middle, r=right
        Second character: t=top, a=ascender (baseline)
        """
        h_align = anchor[0] if anchor else 'l'
        if h_align == 'r':
            return x - width  # Right-aligned: right edge at x
        elif h_align == 'm':
            return x - width // 2  # Middle-aligned: center at x
        return x  # Left-aligned: left edge at x
    
    elements = [
        {
            "id": "clock",
            "name": "Clock",
            "type": "text",
            "x": calc_x(layout.clock_x, 200, "mt"),
            "y": layout.clock_y,
            "width": 200,
            "height": 80,
            "anchor": "mt",
            "font": "clock",
            "sample": "12:34"
        },
        {
            "id": "weather_temp",
            "name": "Weather Temp",
            "type": "text",
            "x": calc_x(layout.weather_x, 120, "ra"),
            "y": layout.weather_y,
            "width": 120,
            "height": 30,
            "anchor": "ra",
            "font": "header",
            "sample": "+12.5°C"
        },
        {
            "id": "weather_icon",
            "name": "Weather Icon",
            "type": "area",
            "x": layout.weather_x - 120 - 10 - 46,
            "y": layout.weather_y,
            "width": 46,
            "height": 46,
            "sample": "☀️"
        },
        {
            "id": "header_route",
            "name": "Header: Route",
            "type": "text",
            "x": 10,
            "y": layout.header_y,
            "width": 60,
            "height": 30,
            "anchor": "la",
            "font": "header",
            "sample": "Linja"
        },
        {
            "id": "header_destination",
            "name": "Header: Destination",
            "type": "text",
            "x": layout.destination_col_x,
            "y": layout.header_y,
            "width": 150,
            "height": 30,
            "anchor": "la",
            "font": "header",
            "sample": "Määränpää"
        },
        {
            "id": "header_time",
            "name": "Header: Time",
            "type": "text",
            "x": calc_x(layout.time_col_x, 100, "ra"),
            "y": layout.header_y,
            "width": 100,
            "height": 30,
            "anchor": "ra",
            "font": "header",
            "sample": "Aika/min"
        },
        {
            "id": "grid_top",
            "name": "Grid Top Line",
            "type": "line",
            "x": 0,
            "y": layout.top_line_y,
            "width": 800,
            "height": 4
        },
        {
            "id": "grid_bottom",
            "name": "Grid Bottom Line",
            "type": "line",
            "x": 0,
            "y": layout.top_line_y + max_items * layout.line_gap,
            "width": 800,
            "height": 4
        },
        {
            "id": "alerts",
            "name": "Alerts Area",
            "type": "area",
            "type": "area",
            "x": (800 - getattr(layout, 'alert_width', 780)) // 2,
            "y": layout.alert_y,
            "width": getattr(layout, 'alert_width', 780),
            "height": 60
        }
    ]
    
    # Add arrival row elements
    for i in range(max_items):
        y_offset = layout.top_line_y - 5 + i * layout.line_gap
        elements.extend([
            {
                "id": f"row_{i}_route",
                "name": f"Row {i+1}: Route",
                "type": "text",
                "x": calc_x(layout.route_col_x, 50, "la"),
                "y": y_offset,
                "width": 50,
                "height": 50,
                "anchor": "la",
                "font": "numbers",
                "sample": "550"
            },
            {
                "id": f"row_{i}_destination",
                "name": f"Row {i+1}: Destination",
                "type": "text",
                "x": layout.destination_col_x,
                "y": y_offset + 15,
                "width": 400,
                "height": 30,
                "anchor": "la",
                "font": "text",
                "sample": "Itäkeskus"
            },
            {
                "id": f"row_{i}_time",
                "name": f"Row {i+1}: Time",
                "type": "text",
                "x": calc_x(layout.time_col_x, 50, "ra"),
                "y": y_offset,
                "width": 50,
                "height": 50,
                "anchor": "ra",
                "font": "numbers",
                "sample": "5"
            }
        ])
    
    return {
        "display_width": 800,
        "display_height": 480,
        "elements": elements,
        "layout": layout.to_dict()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
