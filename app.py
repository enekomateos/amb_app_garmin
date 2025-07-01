from flask import Flask, jsonify, request
import requests
from google.transit import gtfs_realtime_pb2
import time
import os
import pandas as pd
import csv
import json

app = Flask(__name__)

# --- Configuration ---
GTFS_RT_URL = "https://www.ambmobilitat.cat/transit/trips-updates/trips.bin"
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Paradas.xlsx")

# --- Helper Functions ---
def load_stop_names():
    """Loads stop names from the Excel file into a dictionary."""
    try:
        paradas_df = pd.read_excel(EXCEL_PATH)
        # Assuming the first column is stop_id and the second is stop_name
        return dict(zip(paradas_df.iloc[:, 0].astype(str), paradas_df.iloc[:, 1]))
    except FileNotFoundError:
        # Return an empty dictionary if the file doesn't exist
        return {}

stop_id_to_name = load_stop_names()

def get_stop_name(stop_id):
    """Gets the stop name from the loaded dictionary, falling back to the ID."""
    return stop_id_to_name.get(stop_id.lstrip('0'), stop_id)

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

@app.route('/')
def index():
    return "Bus Time API is running. Visit /bus_time to get data."

@app.route('/bus_time')
def get_bus_time():
    # Get parameters from the query string, with default values
    stop_id = request.args.get('stop', default='108', type=str)
    line_prefix = request.args.get('line_prefix', default='211.', type=str)

    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        now = time.time()
        
        # Clean the requested stop_id by removing leading zeros
        cleaned_request_stop_id = stop_id.lstrip('0')

        # First, try to find the specific line requested
        next_arrival_min = None
        found_line = line_prefix

        for entity in feed.entity:
            if entity.HasField('trip_update') and entity.trip_update.trip.trip_id.startswith(line_prefix):
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id.lstrip('0') == cleaned_request_stop_id:
                        event_time = None
                        if stop_time_update.HasField('arrival'):
                            event_time = stop_time_update.arrival.time
                        elif stop_time_update.HasField('departure'):
                            event_time = stop_time_update.departure.time

                        if event_time:
                            time_diff_min = round((event_time - now) / 60)
                            if time_diff_min >= 0:
                                if next_arrival_min is None or time_diff_min < next_arrival_min:
                                    next_arrival_min = time_diff_min
        
        # If no arrival was found for the specific line, search for any line at that stop
        if next_arrival_min is None:
            for entity in feed.entity:
                if entity.HasField('trip_update'):
                    for stop_time_update in entity.trip_update.stop_time_update:
                        if stop_time_update.stop_id.lstrip('0') == cleaned_request_stop_id:
                            event_time = None
                            if stop_time_update.HasField('arrival'):
                                event_time = stop_time_update.arrival.time
                            elif stop_time_update.HasField('departure'):
                                event_time = stop_time_update.departure.time

                            if event_time:
                                time_diff_min = round((event_time - now) / 60)
                                if time_diff_min >= 0:
                                    if next_arrival_min is None or time_diff_min < next_arrival_min:
                                        next_arrival_min = time_diff_min
                                        found_line = entity.trip_update.trip.trip_id.split('.')[0]


        if next_arrival_min is not None:
            return jsonify({
                "line": found_line,
                "stop": stop_id,
                "arrival_min": next_arrival_min
            })
        else:
            return jsonify({
                "error": f"Could not find any upcoming arrivals at stop {stop_id}.",
                "stop": stop_id
            })
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to fetch real-time data: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500



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
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
