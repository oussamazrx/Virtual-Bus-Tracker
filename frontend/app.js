// Configuration
const API_URL = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';

// Global variables
let map;
let busMarker;
let routeLine;
let stopMarkers = [];
let vehicleMarkers = {};
let ws;
let reconnectInterval;
let notificationPermission = false;
let selectedStop = '';
let notificationMinutes = 5;
let lastNotificationTime = {};

// Initialize the application
document.addEventListener('DOMContentLoaded', async () => {
    initializeMap();
    await loadRoute();
    await loadETA();
    connectWebSocket();
    setupNotifications();
    
    // Refresh ETA every 30 seconds
    setInterval(loadETA, 30000);
});

// Initialize Leaflet map
function initializeMap() {
    // Center on Agadir, Morocco
    map = L.map('map').setView([30.4278, -9.5981], 13);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);
}

// Load and display route
async function loadRoute() {
    try {
        // Prefer server-provided Google directions (if backend has API key and provided coordinates)
        let data;
        try {
            const resp = await fetch(`${API_URL}/api/directions`);
            if (resp.ok) {
                const directions = await resp.json();
                if (directions.coordinates && directions.coordinates.length) {
                    // Build a pseudo route object to keep existing code paths
                    data = {
                        route_name: 'Google Directions Route',
                        stops: [],
                        coordinates: directions.coordinates
                    };
                }
            }
        } catch (err) {
            // ignore and fallback
        }

        if (!data) {
            const response = await fetch(`${API_URL}/api/route`);
            data = await response.json();
        }

        // If we used Google directions (which returns only coordinates), fetch stops separately
        if (!data.stops || data.stops.length === 0) {
            try {
                const routeResp = await fetch(`${API_URL}/api/route`);
                if (routeResp.ok) {
                    const routeInfo = await routeResp.json();
                    data.stops = routeInfo.stops || [];
                }
            } catch (err) {
                // ignore
                data.stops = [];
            }
        }
        
        // Draw route line
        const coordinates = data.coordinates.map(coord => [coord[0], coord[1]]);
        
        if (routeLine) {
            map.removeLayer(routeLine);
        }
        
        routeLine = L.polyline(coordinates, {
            color: '#2563eb',
            weight: 4,
            opacity: 0.7
        }).addTo(map);
        
        // Add stop markers
        stopMarkers.forEach(marker => map.removeLayer(marker));
        stopMarkers = [];
        
        const stopSelect = document.getElementById('stop-select');
        const fromSelect = document.getElementById('from-select');
        const toSelect = document.getElementById('to-select');
        if (stopSelect) {
            stopSelect.innerHTML = '<option value="">Choose a stop...</option>';
        }
        
        data.stops.forEach((stop, index) => {
            const marker = L.marker([stop.lat, stop.lon], {
                icon: L.divIcon({
                    className: 'stop-marker',
                    html: `<div style="background: white; border: 3px solid #2563eb; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px;">${index + 1}</div>`,
                    iconSize: [30, 30]
                })
            }).addTo(map);
            
            marker.bindPopup(`
                <div style="font-family: sans-serif;">
                    <strong>${stop.name}</strong><br>
                    <span style="color: #64748b; font-size: 12px;">
                        Stop ${index + 1} of ${data.stops.length}
                    </span>
                </div>
            `);
            
            stopMarkers.push(marker);
            
            // Add to select dropdown
            if (stopSelect) {
                const option = document.createElement('option');
                option.value = stop.name;
                option.textContent = stop.name;
                stopSelect.appendChild(option);
            }

            // Populate from/to selects if present
            if (fromSelect) {
                const o = document.createElement('option');
                o.value = stop.name;
                o.textContent = stop.name;
                fromSelect.appendChild(o);
            }

            if (toSelect) {
                const o2 = document.createElement('option');
                o2.value = stop.name;
                o2.textContent = stop.name;
                toSelect.appendChild(o2);
            }
        });
        
        // Fit map to show entire route
        map.fitBounds(routeLine.getBounds(), { padding: [50, 50] });
        
    } catch (error) {
        console.error('Error loading route:', error);
    }
}

// Setup bus filter UI
document.addEventListener('DOMContentLoaded', () => {
    const filterBtn = document.getElementById('filter-buses');
    const showAllBtn = document.getElementById('show-all-buses');

    if (filterBtn) {
        filterBtn.addEventListener('click', async () => {
            const from = document.getElementById('from-select').value;
            const to = document.getElementById('to-select').value;
            if (!from || !to) {
                alert('Please select both From and To stops to filter');
                return;
            }

            try {
                const resp = await fetch(`${API_URL}/api/vehicles?from_stop=${encodeURIComponent(from)}&to_stop=${encodeURIComponent(to)}`);
                const data = await resp.json();
                if (data.vehicles) updateVehiclesPositions(data.vehicles);
            } catch (err) {
                console.error('Error filtering vehicles', err);
            }
        });
    }

    if (showAllBtn) {
        showAllBtn.addEventListener('click', async () => {
            try {
                const resp = await fetch(`${API_URL}/api/vehicles`);
                const data = await resp.json();
                if (data.vehicles) updateVehiclesPositions(data.vehicles);
            } catch (err) {
                console.error('Error fetching vehicles', err);
            }
        });
    }
});

// Load ETA data
async function loadETA() {
    try {
        const response = await fetch(`${API_URL}/api/eta`);
        const data = await response.json();
        
        const etaList = document.getElementById('eta-list');
        if (!etaList) return;
        
        etaList.innerHTML = '';
        
        data.etas.forEach(eta => {
            if (eta.eta_minutes !== null && !eta.error) {
                const etaItem = document.createElement('div');
                etaItem.className = 'eta-item';
                etaItem.innerHTML = `
                    <div class="eta-stop-name">${eta.stop_name}</div>
                    <div class="eta-details">
                        <span class="eta-time">${Math.round(eta.eta_minutes)} min (${eta.eta_time})</span>
                        <span class="eta-distance">${eta.distance_km} km</span>
                    </div>
                `;
                etaList.appendChild(etaItem);
                
                // Check if notification should be sent
                checkNotification(eta.stop_name, eta.eta_minutes);
            }
        });
        
    } catch (error) {
        console.error('Error loading ETA:', error);
    }
}

// WebSocket connection
function connectWebSocket() {
    updateConnectionStatus('connecting', 'Connecting...');
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        updateConnectionStatus('connected', 'Live updates active');
        clearInterval(reconnectInterval);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'ping') {
            return;
        }
        // If server sends vehicles list
        if (data.type === 'vehicles' && Array.isArray(data.vehicles)) {
            updateVehiclesPositions(data.vehicles);
            return;
        }

        // Legacy single-bus update
        updateBusPosition(data);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus('disconnected', 'Connection error');
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus('disconnected', 'Reconnecting...');
        
        // Attempt to reconnect every 5 seconds
        reconnectInterval = setInterval(() => {
            console.log('Attempting to reconnect...');
            connectWebSocket();
        }, 5000);
    };
}

// Update bus position on map
function updateBusPosition(data) {
    const { position, is_moving, nearest_stop, speed_kmh, current_time } = data;
    
    // Update status bar
    document.getElementById('bus-status').textContent = is_moving ? '🟢 Moving' : '🔴 Stopped';
    document.getElementById('nearest-stop').textContent = nearest_stop;
    document.getElementById('bus-speed').textContent = `${speed_kmh} km/h`;
    document.getElementById('last-update').textContent = current_time;
    
    // Create or update bus marker
    if (!busMarker) {
        busMarker = L.marker([position.lat, position.lon], {
            icon: L.divIcon({
                className: 'bus-marker',
                html: '<div style="font-size: 30px;">🚌</div>',
                iconSize: [40, 40],
                iconAnchor: [20, 20]
            })
        }).addTo(map);
        
        busMarker.bindPopup(`
            <div style="font-family: sans-serif;">
                <strong>CMC Bus</strong><br>
                <span style="color: #64748b; font-size: 12px;">
                    ${is_moving ? 'In motion' : 'At stop'}
                </span>
            </div>
        `);
    } else {
        busMarker.setLatLng([position.lat, position.lon]);
        busMarker.setPopupContent(`
            <div style="font-family: sans-serif;">
                <strong>CMC Bus</strong><br>
                <span style="color: #64748b; font-size: 12px;">
                    ${is_moving ? 'In motion' : 'At stop'}<br>
                    Near: ${nearest_stop}
                </span>
            </div>
        `);
    }
}

// Update connection status indicator
function updateConnectionStatus(status, text) {
    const dot = document.getElementById('connection-dot');
    const statusText = document.getElementById('connection-text');
    
    if (dot) {
        dot.className = `dot ${status}`;
    }
    
    if (statusText) {
        statusText.textContent = text;
    }
}

// Setup notification system
function setupNotifications() {
    const enableBtn = document.getElementById('enable-notifications');
    const stopSelect = document.getElementById('stop-select');
    const timeSelect = document.getElementById('time-select');
    const statusDiv = document.getElementById('notification-status');
    
    if (!enableBtn) return;
    
    stopSelect.addEventListener('change', (e) => {
        selectedStop = e.target.value;
    });
    
    timeSelect.addEventListener('change', (e) => {
        notificationMinutes = parseInt(e.target.value);
    });
    
    enableBtn.addEventListener('click', async () => {
        if (!selectedStop) {
            showNotificationStatus('Please select a stop first', 'error');
            return;
        }
        
        if ('Notification' in window) {
            const permission = await Notification.requestPermission();
            
            if (permission === 'granted') {
                notificationPermission = true;
                showNotificationStatus(
                    `✓ Notifications enabled for ${selectedStop} (${notificationMinutes} min before)`,
                    'success'
                );
                
                // Send test notification
                new Notification('CMC Bus Tracker', {
                    body: `You'll be notified ${notificationMinutes} minutes before the bus arrives at ${selectedStop}`,
                    icon: '🚌'
                });
            } else {
                showNotificationStatus('Notification permission denied', 'error');
            }
        } else {
            showNotificationStatus('Notifications not supported in this browser', 'error');
        }
    });
}

// Show notification status message
function showNotificationStatus(message, type) {
    const statusDiv = document.getElementById('notification-status');
    if (!statusDiv) return;
    
    statusDiv.textContent = message;
    statusDiv.className = `notification-status ${type}`;
    
    setTimeout(() => {
        statusDiv.className = 'notification-status';
    }, 5000);
}

// Check if notification should be sent
function checkNotification(stopName, etaMinutes) {
    if (!notificationPermission || stopName !== selectedStop) {
        return;
    }
    
    const now = Date.now();
    const lastNotif = lastNotificationTime[stopName] || 0;
    
    // Only notify once every 5 minutes for the same stop
    if (now - lastNotif < 5 * 60 * 1000) {
        return;
    }
    
    if (etaMinutes <= notificationMinutes && etaMinutes > 0) {
        new Notification('🚌 Bus Alert!', {
            body: `The bus will arrive at ${stopName} in ${Math.round(etaMinutes)} minutes`,
            icon: '🚌',
            requireInteraction: true
        });
        
        lastNotificationTime[stopName] = now;
    }
}

// Update multiple vehicles positions
function updateVehiclesPositions(vehicles) {
    const listDiv = document.getElementById('vehicle-list');
    if (listDiv) listDiv.innerHTML = '';

    vehicles.forEach(v => {
        const id = v.id;
        const lat = v.position.lat;
        const lon = v.position.lon;

        // Create or update marker
        if (!vehicleMarkers[id]) {
            const marker = L.marker([lat, lon], {
                icon: L.divIcon({
                    className: 'bus-marker',
                    html: `<div style="font-size: 20px;">🚌</div>`,
                    iconSize: [30, 30],
                    iconAnchor: [15, 15]
                })
            }).addTo(map);
            marker.bindPopup(`<strong>${id}</strong>`);
            vehicleMarkers[id] = marker;
        } else {
            vehicleMarkers[id].setLatLng([lat, lon]);
            vehicleMarkers[id].setPopupContent(`<strong>${id}</strong>`);
        }

        if (listDiv) {
            const item = document.createElement('div');
            item.className = 'vehicle-item';
            item.textContent = `${id} — ${Math.round(v.speed_kmh || 0)} km/h`;
            listDiv.appendChild(item);
        }
    });
}

// Geolocation: locate user and fetch nearest vehicle
let userMarker = null;
async function locateUser() {
    if (!('geolocation' in navigator)) {
        alert('Geolocation not supported');
        return;
    }

    navigator.geolocation.getCurrentPosition(async (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        showUserMarker(lat, lon);

        // Request nearest vehicle from server
        try {
            const resp = await fetch(`${API_URL}/api/nearest_vehicle?lat=${lat}&lon=${lon}`);
            const data = await resp.json();
            const infoDiv = document.getElementById('nearest-text');
            if (data && data.vehicle) {
                const v = data.vehicle;
                infoDiv.textContent = `${v.id} is ${data.distance_km} km away`;
                // Highlight marker if exists
                if (vehicleMarkers[v.id]) {
                    vehicleMarkers[v.id].openPopup();
                }
            } else {
                infoDiv.textContent = 'No vehicles available nearby';
            }
        } catch (err) {
            console.error('Error fetching nearest vehicle', err);
        }

    }, (err) => {
        alert('Unable to retrieve location: ' + err.message);
    }, { enableHighAccuracy: true, maximumAge: 10000 });
}

function showUserMarker(lat, lon) {
    if (!map) return;
    if (!userMarker) {
        userMarker = L.marker([lat, lon], {
            icon: L.divIcon({ html: '<div style="font-size:18px">📍</div>', className: '' })
        }).addTo(map);
    } else {
        userMarker.setLatLng([lat, lon]);
    }
    map.panTo([lat, lon]);
}

// Hook locate me button
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('locate-me');
    if (btn) btn.addEventListener('click', locateUser);
});