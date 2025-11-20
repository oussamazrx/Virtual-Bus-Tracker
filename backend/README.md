# CMC Bus Tracker - Backend

FastAPI backend with WebSocket support for real-time bus tracking.

## Local Development

### Requirements
- Python 3.8+
- pip

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

The API will be available at `http://localhost:8000`

### Google Directions (optional)

If you want the server to use real road trajectories from Google Maps for smoother routes, set the environment variable `GOOGLE_MAPS_API_KEY` before starting the server. When present, the backend will attempt to fetch a route using the stops in `routes.json` and replace the internal coordinates with the Google overview polyline.

Example (PowerShell):

```powershell
$env:GOOGLE_MAPS_API_KEY = "YOUR_API_KEY_HERE"; python main.py
```

There is also a proxy endpoint `GET /api/directions?origin=lat,lng&destination=lat,lng` which returns decoded coordinates from Google (requires the same env var).

### Free fallback: OSRM public demo

If you prefer a free option (no API key) the backend will now automatically fall back to the public OSRM demo server (`router.project-osrm.org`) when Google Directions is not available or fails. This gives road-aligned trajectories without any billing.

Notes:
- The OSRM demo server is intended for prototyping and may be rate-limited or unreliable for production use.
- For production, self-host OSRM or Valhalla (Docker) or use a paid hosted routing service.

No changes are required in the frontend — the server will attempt Google first (if `GOOGLE_MAPS_API_KEY` is set) then OSRM, then fall back to static `routes.json` coordinates.

### Multi-bus & filtering

This project now simulates multiple buses by default (3 vehicles). New endpoints:

- `GET /api/vehicles` — returns current simulated vehicles and positions.
- `GET /api/vehicles?from_stop=Name&to_stop=Name` — filter vehicles between two stops.
- `GET /api/vehicles/{vehicle_id}/eta?stop_name=StopName` — ETA for a specific vehicle to a stop.

The WebSocket `/ws` now broadcasts messages with `type: "vehicles"` and a `vehicles` array. The frontend will display all active buses, allow filtering by stop, and show per-vehicle positions.

If you want more buses, edit the number passed to `BusSimulator()` in `main.py` (for example `BusSimulator(num_vehicles=5)`).

### API Endpoints

- `GET /` - API information
- `GET /api/bus` - Current bus status
- `GET /api/eta` - ETA for all stops
- `GET /api/route` - Complete route information
- `WS /ws` - WebSocket for real-time updates

## Deployment

### Deploy to Render.com (Free)

1. Create account at render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3

The service will auto-deploy on git push.