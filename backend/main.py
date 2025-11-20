from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json
import os
from typing import List, Optional
import requests
from bus_simulator import BusSimulator

app = FastAPI(title="CMC Bus Tracker API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize bus simulator (number of vehicles configurable via VEHICLE_COUNT env var)
num = 3
try:
    num = int(os.environ.get('VEHICLE_COUNT', '3'))
except Exception:
    num = 3
bus_simulator = BusSimulator(num_vehicles=num)

# Store active WebSocket connections
active_connections: List[WebSocket] = []

# Background task to update bus positions
async def bus_position_updater():
    """Background task that updates bus positions every 5 seconds and broadcasts them"""
    while True:
        # Update simulator (multi-vehicle)
        try:
            await bus_simulator.update_positions()
        except AttributeError:
            # Fallback to legacy single update if present
            try:
                await bus_simulator.update_position()
            except Exception:
                pass

        # Broadcast to all connected clients
        if active_connections:
            vehicles = bus_simulator.get_vehicles() if hasattr(bus_simulator, 'get_vehicles') else []
            message = json.dumps({'type': 'vehicles', 'vehicles': vehicles})

            disconnected = []
            for connection in active_connections:
                try:
                    await connection.send_text(message)
                except:
                    disconnected.append(connection)

            # Remove disconnected clients
            for conn in disconnected:
                if conn in active_connections:
                    active_connections.remove(conn)

        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    """Start background tasks on server startup"""
    # If GOOGLE_MAPS_API_KEY is provided, attempt to fetch a smoother route
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    try:
        # Build origin, destination and waypoints from current route stops
        stops = bus_simulator.route_data.get('stops', [])
        if len(stops) >= 2:
            origin = f"{stops[0]['lat']},{stops[0]['lon']}"
            destination = f"{stops[-1]['lat']},{stops[-1]['lon']}"
            waypoints = [f"{s['lat']},{s['lon']}" for s in stops[1:-1]]

            # Try Google (if key provided) then OSRM public demo as fallback
            try:
                points = fetch_directions_fallback(origin, destination, waypoints, api_key)
                if points:
                    bus_simulator.set_route_coordinates(points)
            except Exception:
                # Ignore failures and keep default static route
                pass
    except Exception:
        pass

    asyncio.create_task(bus_position_updater())


def decode_polyline(encoded: str) -> List[List[float]]:
    """Decode a polyline string into a list of [lat, lng] pairs.

    Implementation follows Google's polyline algorithm.
    """
    coords: List[List[float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        result = 1
        shift = 0
        b = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        delta_lat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += delta_lat

        result = 1
        shift = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1f:
                break
        delta_lng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += delta_lng

        coords.append([lat * 1e-5, lng * 1e-5])

    return coords


def fetch_google_directions(origin: str, destination: str, waypoints: Optional[List[str]], api_key: str) -> List[List[float]]:
    """Fetch directions from Google Directions API and return decoded polyline coordinates.

    origin and destination should be strings like 'lat,lng'. Waypoints is a list of 'lat,lng' strings.
    """
    base = 'https://maps.googleapis.com/maps/api/directions/json'
    params = {
        'origin': origin,
        'destination': destination,
        'key': api_key,
        'mode': 'driving'
    }

    if waypoints:
        # Join waypoints with '|'
        params['waypoints'] = '|'.join(waypoints)

    resp = requests.get(base, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Validate response
    if data.get('status') != 'OK' or not data.get('routes'):
        return []

    overview = data['routes'][0].get('overview_polyline', {}).get('points')
    if not overview:
        return []

    return decode_polyline(overview)


def fetch_osrm_directions(origin: str, destination: str, waypoints: Optional[List[str]] = None) -> List[List[float]]:
    """Fetch directions from the public OSRM demo server and return decoded polyline coordinates.

    origin and destination are 'lat,lng' strings. OSRM requires lon,lat ordering in path.
    This uses the demo server at router.project-osrm.org (suitable for prototyping only).
    """
    base = 'https://router.project-osrm.org/route/v1/driving/'

    def to_lonlat(s: str) -> str:
        lat, lon = [p.strip() for p in s.split(',')]
        return f"{lon},{lat}"

    coords = [to_lonlat(origin)]
    if waypoints:
        for w in waypoints:
            coords.append(to_lonlat(w))
    coords.append(to_lonlat(destination))

    coord_str = ';'.join(coords)
    params = {
        'overview': 'full',
        'geometries': 'polyline'
    }

    resp = requests.get(base + coord_str, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get('code') != 'Ok' or not data.get('routes'):
        return []

    geometry = data['routes'][0].get('geometry')
    if not geometry:
        return []

    return decode_polyline(geometry)


def fetch_directions_fallback(origin: str, destination: str, waypoints: Optional[List[str]], api_key: Optional[str] = None) -> List[List[float]]:
    """Unified fetch that tries Google (when API key provided) then falls back to OSRM public demo.

    Returns a list of [lat, lng] coordinates or empty list on failure.
    """
    # Try Google if API key was provided
    if api_key:
        try:
            points = fetch_google_directions(origin, destination, waypoints, api_key)
            if points:
                return points
        except Exception:
            # fall through to OSRM
            pass

    # Try OSRM public demo
    try:
        points = fetch_osrm_directions(origin, destination, waypoints)
        if points:
            return points
    except Exception:
        pass

    return []

@app.get("/")
async def root():
    return {
        "message": "CMC Bus Tracker API",
        "version": "1.0.0",
        "endpoints": {
            "bus_status": "/api/bus",
            "eta": "/api/eta",
            "route": "/api/route",
            "websocket": "/ws"
        }
    }

@app.get("/api/bus")
async def get_bus_status():
    """Get current bus position and status"""
    return bus_simulator.get_status()

@app.get("/api/eta")
async def get_eta():
    """Get estimated time of arrival for all stops"""
    return {
        "etas": bus_simulator.get_all_eta(),
        "current_time": bus_simulator.last_update.strftime('%H:%M:%S')
    }

@app.get("/api/eta/{stop_name}")
async def get_eta_for_stop(stop_name: str):
    """Get ETA for a specific stop"""
    eta_data = bus_simulator.calculate_eta_to_stop(stop_name)
    return {
        "stop_name": stop_name,
        **eta_data
    }

@app.get("/api/route")
async def get_route():
    """Get the complete bus route with stops"""
    return {
        "route_name": bus_simulator.route_data['name'],
        "stops": bus_simulator.route_data['stops'],
        "coordinates": bus_simulator.route_data['coordinates'],
        "total_stops": len(bus_simulator.route_data['stops'])
    }


@app.get("/api/directions")
async def get_directions(origin: Optional[str] = None, destination: Optional[str] = None):
    """Proxy endpoint to fetch Google Directions overview polyline decoded.

    Provide `origin` and `destination` as 'lat,lng'. If not provided, the route's first and
    last stops will be used. Requires environment variable `GOOGLE_MAPS_API_KEY`.
    """
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        return JSONResponse(status_code=400, content={"error": "GOOGLE_MAPS_API_KEY not set on server"})

    stops = bus_simulator.route_data.get('stops', [])
    if not origin or not destination:
        if len(stops) >= 2:
            origin = origin or f"{stops[0]['lat']},{stops[0]['lon']}"
            destination = destination or f"{stops[-1]['lat']},{stops[-1]['lon']}"
        else:
            return JSONResponse(status_code=400, content={"error": "origin/destination required or route stops insufficient"})

    try:
        waypoints = []
        if len(stops) > 2:
            for s in stops[1:-1]:
                waypoints.append(f"{s['lat']},{s['lon']}")

        coords = fetch_google_directions(origin, destination, waypoints, api_key)
        return {"coordinates": coords}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/vehicles")
async def list_vehicles(from_stop: Optional[str] = None, to_stop: Optional[str] = None):
    """List current vehicles. Optionally filter by `from_stop` and `to_stop` (stop names)."""
    if from_stop and to_stop and hasattr(bus_simulator, 'get_vehicles_for_stops'):
        vehicles = bus_simulator.get_vehicles_for_stops(from_stop, to_stop)
        return {"vehicles": vehicles}

    vehicles = bus_simulator.get_vehicles() if hasattr(bus_simulator, 'get_vehicles') else []
    return {"vehicles": vehicles}


@app.get("/api/vehicles/{vehicle_id}/eta")
async def vehicle_eta(vehicle_id: str, stop_name: Optional[str] = None):
    """Return ETA for a given vehicle to a named stop. If `stop_name` is omitted, returns ETA to next stop."""
    if not hasattr(bus_simulator, 'calculate_eta_for_vehicle'):
        return JSONResponse(status_code=400, content={"error": "Vehicle ETA not supported by simulator"})

    if not stop_name:
        # find next stop for vehicle by scanning route
        return JSONResponse(status_code=400, content={"error": "stop_name query parameter required"})

    eta = bus_simulator.calculate_eta_for_vehicle(vehicle_id, stop_name)
    return {"vehicle_id": vehicle_id, "stop_name": stop_name, **eta}


@app.get("/api/nearest_vehicle")
async def nearest_vehicle(lat: Optional[float] = None, lon: Optional[float] = None):
    """Return the nearest simulated vehicle to given coordinates (lat, lon)."""
    if lat is None or lon is None:
        return JSONResponse(status_code=400, content={"error": "lat and lon query parameters required"})

    vehicles = bus_simulator.get_vehicles() if hasattr(bus_simulator, 'get_vehicles') else []
    if not vehicles:
        return {"vehicle": None}

    def dist_km(a, b):
        return bus_simulator.calculate_distance(a[0], a[1], b[0], b[1])

    best = None
    best_d = float('inf')
    for v in vehicles:
        p = v['position']
        d = dist_km((lat, lon), (p['lat'], p['lon']))
        if d < best_d:
            best_d = d
            best = v

    return {"vehicle": best, "distance_km": round(best_d, 3)}


@app.get("/api/nearest_vehicle_to_stop")
async def nearest_vehicle_to_stop(stop_name: str):
    """Return the vehicle with the smallest ETA to the named stop."""
    if not hasattr(bus_simulator, 'vehicles'):
        return JSONResponse(status_code=400, content={"error": "Simulator does not support vehicles"})

    best = None
    best_eta = float('inf')
    for v in bus_simulator.vehicles:
        eta = bus_simulator.calculate_eta_for_vehicle(v['id'], stop_name)
        eta_min = eta.get('eta_minutes')
        if eta_min is not None:
            try:
                if eta_min < best_eta:
                    best_eta = eta_min
                    best = {'id': v['id'], 'position': {'lat': v['current_position'][0], 'lon': v['current_position'][1]}, 'eta': eta}
            except Exception:
                continue

    if not best:
        return {"vehicle": None, "error": "no vehicle with ETA available to this stop"}

    return {"vehicle": best, "eta_minutes": best_eta}

@app.get("/api/notifications/{stop_name}/{minutes_before}")
async def check_notification(stop_name: str, minutes_before: int):
    """Check if notification should be sent"""
    eta_data = bus_simulator.calculate_eta_to_stop(stop_name)
    
    if 'error' in eta_data:
        return {"should_notify": False, "error": eta_data['error']}
    
    eta_minutes = eta_data.get('eta_minutes', float('inf'))
    
    return {
        "should_notify": eta_minutes <= minutes_before and eta_minutes > 0,
        "eta_minutes": eta_minutes,
        "eta_time": eta_data.get('eta_time')
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        # Send initial vehicles list (if supported)
        if hasattr(bus_simulator, 'get_vehicles'):
            initial = {'type': 'vehicles', 'vehicles': bus_simulator.get_vehicles()}
        else:
            initial = bus_simulator.get_status()
        await websocket.send_text(json.dumps(initial))
        
        # Keep connection alive
        while True:
            # Wait for any message from client (ping/pong)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({"type": "ping"}))
    
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        if websocket in active_connections:
            active_connections.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)