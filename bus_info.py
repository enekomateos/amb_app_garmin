import csv
import json
from flask import Flask, jsonify

app = Flask(__name__)

def get_bus_info(route_short_name, direction_headsign=None):
    # Find route_id for the given route_short_name
    route_id = None
    with open('GTFS_static/routes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['route_short_name'] == route_short_name:
                route_id = row['route_id']
                break

    if not route_id:
        return {"error": f"Route {route_short_name} not found"}

    # Get all trips for this route
    trip_ids = []
    with open('GTFS_static/trips.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['route_id'] == route_id:
                if direction_headsign:
                    if direction_headsign.lower() in row.get('trip_headsign', '').lower():
                        trip_ids.append(row['trip_id'])
                else:
                    trip_ids.append(row['trip_id'])

    if not trip_ids:
        return {"error": f"No trips found for route {route_short_name} with direction {direction_headsign}"}

    # Get stop times for these trips
    stop_times = []
    with open('GTFS_static/stop_times.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['trip_id'] in trip_ids:
                stop_times.append(row)

    # Get stop names
    stops = {}
    with open('GTFS_static/stops.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops[row['stop_id']] = row['stop_name']

    # Combine the data
    route_schedule = {}
    for stop_time in stop_times:
        stop_id = stop_time['stop_id']
        stop_name = stops.get(stop_id, "Unknown Stop")
        arrival_time = stop_time['arrival_time']
        
        if stop_name not in route_schedule:
            route_schedule[stop_name] = {
                "stop_id": stop_id,
                "stop_name": stop_name,
                "times": []
            }
        
        route_schedule[stop_name]["times"].append(arrival_time)

    # Sort times for each stop
    for stop_name in route_schedule:
        route_schedule[stop_name]["times"] = sorted(list(set(route_schedule[stop_name]["times"])))

    # Sort stops by stop_sequence
    stop_sequences = {}
    for stop_time in stop_times:
        stop_id = stop_time['stop_id']
        if stop_id not in stop_sequences:
            stop_sequences[stop_id] = int(stop_time['stop_sequence'])

    sorted_stops = sorted(route_schedule.values(), key=lambda x: stop_sequences.get(x['stop_id'], float('inf')))

    return sorted_stops

@app.route('/route_info/<string:route_name>/<string:direction>', methods=['GET'])
def route_info(route_name, direction):
    schedule = get_bus_info(route_name, direction)
    if "error" in schedule:
        return jsonify(schedule), 404
    return jsonify(schedule)

if __name__ == '__main__':
    app.run(debug=True)
