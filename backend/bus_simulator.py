import json
import asyncio
import math
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

class BusSimulator:
    def __init__(self, route_file: str = "routes.json", num_vehicles: int = 3):
        with open(route_file, 'r') as f:
            data = json.load(f)
            self.route_data = data['bus_route']

        self.coordinates = self.route_data['coordinates']
        self.stops = self.route_data['stops']

        # Vehicles: list of dicts with id, position, index, speed, state
        self.vehicles: List[Dict] = []
        self.num_vehicles = max(1, num_vehicles)
        self.last_update = datetime.now()

        # Initialize vehicles evenly spaced along the route
        route_len = len(self.coordinates)
        for i in range(self.num_vehicles):
            idx = int((i * route_len) / self.num_vehicles)
            pos = self.coordinates[idx]
            vehicle = {
                'id': f'bus-{i+1}',
                'current_index': idx if idx < route_len else route_len - 1,
                'current_position': pos[:],
                'is_at_stop': False,
                'stop_wait_remaining': 0,
                'speed_kmh': 25 + (i * 5) % 15  # slight variation per vehicle
            }
            self.vehicles.append(vehicle)

    def set_route_coordinates(self, coordinates: List[List[float]]):
        """Replace the internal coordinates with a new list (e.g., from Google Directions).

        Resets the simulator position to the start of the new coordinates.
        """
        if not coordinates:
            return

        # Ensure coordinates are in [lat, lon] pairs
        self.coordinates = coordinates
        # Keep route_data in sync so API returns updated coordinates
        if isinstance(self.route_data, dict):
            self.route_data['coordinates'] = coordinates

        # Reinitialize vehicle positions along the new route
        route_len = len(self.coordinates)
        for i, vehicle in enumerate(self.vehicles):
            idx = int((i * route_len) / max(1, len(self.vehicles)))
            vehicle['current_index'] = idx if idx < route_len else route_len - 1
            vehicle['current_position'] = self.coordinates[vehicle['current_index']][:]
            vehicle['is_at_stop'] = False
            vehicle['stop_wait_remaining'] = 0

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in kilometers using Haversine formula"""
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def find_nearest_stop(self) -> Dict:
        """Find the nearest bus stop to the first vehicle (legacy)"""
        if not self.vehicles:
            return {}
        current_position = self.vehicles[0]['current_position']
        min_distance = float('inf')
        nearest_stop = None

        for stop in self.stops:
            distance = self.calculate_distance(
                current_position[0],
                current_position[1],
                stop['lat'],
                stop['lon']
            )
            if distance < min_distance:
                min_distance = distance
                nearest_stop = stop

        return {**nearest_stop, 'distance': min_distance} if nearest_stop else {}
    
    def calculate_eta_to_stop(self, stop_name: str) -> Dict:
        """Calculate ETA to a specific stop using the first vehicle (legacy)"""
        # Delegate to vehicle-specific calculation using vehicle 0
        if not self.vehicles:
            return {'eta_minutes': None, 'error': 'No vehicles available'}
        return self.calculate_eta_for_vehicle(self.vehicles[0]['id'], stop_name)

    def calculate_eta_for_vehicle(self, vehicle_id: str, stop_name: str) -> Dict:
        """Calculate ETA for a specific vehicle to a named stop"""
        vehicle = next((v for v in self.vehicles if v['id'] == vehicle_id), None)
        if not vehicle:
            return {'eta_minutes': None, 'error': 'Vehicle not found'}

        target_stop = next((s for s in self.stops if s['name'] == stop_name), None)
        if not target_stop:
            return {'eta_minutes': None, 'error': 'Stop not found'}

        total_distance = 0.0
        route_len = len(self.coordinates)
        cur_idx = vehicle['current_index']
        cur_lat, cur_lon = vehicle['current_position']

        # Distance from current position to next coordinate
        if cur_idx < route_len:
            total_distance += self.calculate_distance(cur_lat, cur_lon, self.coordinates[cur_idx][0], self.coordinates[cur_idx][1])

        # Walk along coordinates until we find the target stop within threshold
        target_found = False
        for i in range(cur_idx, route_len):
            coord = self.coordinates[i]
            distance_to_stop = self.calculate_distance(coord[0], coord[1], target_stop['lat'], target_stop['lon'])
            if distance_to_stop < 0.05:
                target_found = True
                break
            if i + 1 < route_len:
                total_distance += self.calculate_distance(coord[0], coord[1], self.coordinates[i+1][0], self.coordinates[i+1][1])

        if not target_found:
            return {'eta_minutes': None, 'error': 'Stop not on remaining route'}

        travel_time_hours = total_distance / vehicle.get('speed_kmh', 25)
        travel_time_minutes = travel_time_hours * 60

        # Add wait times for stops between current position and target
        wait_time_minutes = 0
        for stop in self.stops:
            stop_dist = self.calculate_distance(cur_lat, cur_lon, stop['lat'], stop['lon'])
            target_dist = self.calculate_distance(cur_lat, cur_lon, target_stop['lat'], target_stop['lon'])
            if 0.05 < stop_dist < target_dist:
                wait_time_minutes += stop.get('wait_time', 0) / 60

        total_minutes = travel_time_minutes + wait_time_minutes + (vehicle.get('stop_wait_remaining', 0) / 60)
        eta_time = datetime.now() + timedelta(minutes=total_minutes)

        return {
            'eta_minutes': round(total_minutes, 1),
            'eta_time': eta_time.strftime('%H:%M'),
            'distance_km': round(total_distance, 3)
        }
    
    async def update_positions(self):
        """Update all vehicle positions based on time elapsed"""
        now = datetime.now()
        elapsed_seconds = (now - self.last_update).total_seconds()
        self.last_update = now

        route_len = len(self.coordinates)

        for vehicle in self.vehicles:
            # If at stop, decrement wait
            if vehicle.get('is_at_stop'):
                vehicle['stop_wait_remaining'] -= elapsed_seconds
                if vehicle['stop_wait_remaining'] <= 0:
                    vehicle['is_at_stop'] = False
                    vehicle['current_index'] = min(vehicle['current_index'] + 1, route_len - 1)
                continue

            # If reached end, wrap to start
            if vehicle['current_index'] >= route_len:
                vehicle['current_index'] = 0
                vehicle['current_position'] = self.coordinates[0]
                continue

            distance_to_move_km = (vehicle.get('speed_kmh', 25) / 3600) * elapsed_seconds

            target = self.coordinates[vehicle['current_index']]
            current_lat, current_lon = vehicle['current_position']
            target_lat, target_lon = target

            distance_to_target = self.calculate_distance(current_lat, current_lon, target_lat, target_lon)
            if distance_to_target == 0:
                # Advance index
                vehicle['current_index'] = min(vehicle['current_index'] + 1, route_len - 1)
                continue

            if distance_to_move_km >= distance_to_target:
                vehicle['current_position'] = target
                # Check for stop
                for stop in self.stops:
                    if self.calculate_distance(target_lat, target_lon, stop['lat'], stop['lon']) < 0.02:
                        vehicle['is_at_stop'] = True
                        vehicle['stop_wait_remaining'] = stop.get('wait_time', 0)
                        break
                if not vehicle.get('is_at_stop'):
                    vehicle['current_index'] = min(vehicle['current_index'] + 1, route_len - 1)
            else:
                ratio = distance_to_move_km / distance_to_target
                new_lat = current_lat + (target_lat - current_lat) * ratio
                new_lon = current_lon + (target_lon - current_lon) * ratio
                vehicle['current_position'] = [new_lat, new_lon]
    
    def get_status(self) -> Dict:
        """Get a summary status (legacy) — returns first vehicle as primary"""
        if not self.vehicles:
            return {}
        v = self.vehicles[0]
        nearest_stop = self.find_nearest_stop()
        return {
            'position': {
                'lat': v['current_position'][0],
                'lon': v['current_position'][1]
            },
            'is_moving': not v.get('is_at_stop', False),
            'nearest_stop': nearest_stop.get('name') if nearest_stop else None,
            'distance_to_stop': round(nearest_stop.get('distance', 0), 2) if nearest_stop else None,
            'current_time': datetime.now().strftime('%H:%M:%S'),
            'speed_kmh': v.get('speed_kmh', 0) if not v.get('is_at_stop', False) else 0
        }
    
    def get_all_eta(self) -> List[Dict]:
        """Get ETA for all stops"""
        etas = []
        for stop in self.stops:
            eta_data = self.calculate_eta_to_stop(stop['name'])
            etas.append({
                'stop_name': stop['name'],
                **eta_data
            })
        return etas

    def get_vehicles(self) -> List[Dict]:
        """Return a copy of vehicle states for API consumption"""
        out = []
        for v in self.vehicles:
            out.append({
                'id': v['id'],
                'position': {'lat': v['current_position'][0], 'lon': v['current_position'][1]},
                'is_at_stop': v.get('is_at_stop', False),
                'speed_kmh': v.get('speed_kmh', 0),
                'current_index': v.get('current_index', 0)
            })
        return out

    def get_vehicles_for_stops(self, from_stop: str, to_stop: str) -> List[Dict]:
        """Return vehicles that are on the trajectory between two stops (by name).

        For this simplified simulator all vehicles follow same route; this filters
        by order of stops and returns vehicles that haven't passed the destination yet.
        """
        # find stop indices
        try:
            from_idx = next(i for i, s in enumerate(self.stops) if s['name'] == from_stop)
            to_idx = next(i for i, s in enumerate(self.stops) if s['name'] == to_stop)
        except StopIteration:
            return []
        if from_idx >= to_idx:
            return []

        matched = []
        for v in self.vehicles:
            # if vehicle current_index is before destination, include
            if v.get('current_index', 0) <= to_idx:
                matched.append({
                    'id': v['id'],
                    'position': {'lat': v['current_position'][0], 'lon': v['current_position'][1]},
                    'current_index': v.get('current_index', 0)
                })
        return matched