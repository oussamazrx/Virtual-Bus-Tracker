# CMC Bus Tracker — Campus Transit as a Service (SaaS)

CMC Bus Tracker is a lightweight, privacy-aware SaaS for campus transit: live vehicle tracking, ETAs, notifications, and deployment options for startups, campuses, and transit operators.

Visit the web demo in `frontend/landing.html` for a professional landing page, live demo, and pricing.

## Highlights
- Live bus location and route visualization
- Per-vehicle ETAs, nearest-bus lookup, and browser notifications
- Pluggable routing: OSRM (free) fallback, optional Google Directions
- Multi-vehicle simulated backend, easy to connect to real telemetry
- Deploy on-premises or in the cloud; enterprise support available

## Quickstart (Backend)

1. Install dependencies and run the backend API

```powershell
cd backend
pip install -r requirements.txt
# Optional: configure vehicles and API keys
$env:VEHICLE_COUNT = "4"
$env:GOOGLE_MAPS_API_KEY = "<your-google-key>"
python main.py
```

2. Serve the frontend (simple static server)

```powershell
cd frontend
python -m http.server 8080
# then open http://localhost:8080/landing.html
```

## Frontend Pages
- `landing.html` — Professional landing + pricing and CTAs
- `index.html` — Live map demo (WebSocket + real-time updates)
- `route.html` — Route & stops
- `pricing.html` — Detailed pricing and FAQs
- `about.html` — Project overview and roadmap

## API Endpoints (selected)
- `GET /api/vehicles` — list simulated vehicles and positions
- `GET /api/nearest_vehicle?lat=&lon=` — nearest vehicle to coordinates
- `GET /api/vehicles/{id}/eta?stop_name=` — vehicle ETA to a stop
- `GET /api/directions` — server-side route geometry (Google/OSRM)
- `WS /ws` — WebSocket for live vehicle broadcasts

## Production & Scaling
- For a free routing source use OSRM (demo or self-hosted). For higher accuracy you can connect Google Directions.
- To scale, deploy backend with Uvicorn + Gunicorn or containerize with Docker and use a managed DB for analytics.

## Contributing
- Fork, create a feature branch, and open a pull request. Provide tests or a short demo for major features.

## License
MIT (add `LICENSE` file)

## Contact
For sales or enterprise integrations: `sales@cmc.ac.ma`

