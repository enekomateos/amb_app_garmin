from flask import Flask, jsonify, request
import requests
from google.transit import gtfs_realtime_pb2
import time
import os
import pandas as pd

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
            }), 404

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch GTFS data: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/bus_data_dump')
def get_bus_data_dump():
    line_prefix = request.args.get('line_prefix', default='211', type=str)

    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        now = time.time()
        data_dump = []

        for entity in feed.entity:
            if entity.HasField('trip_update') and entity.trip_update.trip.trip_id.startswith(line_prefix):
                trip_id = entity.trip_update.trip.trip_id
                for stop_time_update in entity.trip_update.stop_time_update:
                    event_time = None
                    event_type = None
                    delay = None

                    if stop_time_update.HasField('arrival') and stop_time_update.arrival.time > now:
                        event_time = stop_time_update.arrival.time
                        event_type = 'arrival'
                        delay = stop_time_update.arrival.delay
                    elif stop_time_update.HasField('departure') and stop_time_update.departure.time > now:
                        event_time = stop_time_update.departure.time
                        event_type = 'departure'
                        delay = stop_time_update.departure.delay

                    if event_time:
                        time_until_event = round((event_time - now) / 60)
                        data_dump.append({
                            "trip_id": trip_id,
                            "stop_id": stop_time_update.stop_id,
                            "stop_name": get_stop_name(stop_time_update.stop_id),
                            "event_type": event_type,
                            "event_time_unix": event_time,
                            "event_time_readable": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event_time)),
                            "time_until_event_min": time_until_event,
                            "delay_sec": delay
                        })
        
        return jsonify(data_dump)

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch GTFS data: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/debug_stop/<stop_id>')
def debug_stop(stop_id):
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        stop_data = []
        cleaned_request_stop_id = stop_id.lstrip('0')

        for entity in feed.entity:
            if entity.HasField('trip_update'):
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id.lstrip('0') == cleaned_request_stop_id:
                        # Convert protobuf to a string for inspection
                        stop_info = str(stop_time_update).replace('\n', ', ')
                        trip_id = entity.trip_update.trip.trip_id
                        stop_data.append({
                            "trip_id": trip_id,
                            "stop_time_update": stop_info
                        })
        
        if stop_data:
            return jsonify(stop_data)
        else:
            return jsonify({
                "message": "No trip updates found for the specified stop_id.",
                "stop_id_searched": stop_id
            }), 404

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred during debug: {e}"}), 500

@app.route('/debug/line/<line_prefix>')
def debug_line(line_prefix):
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        line_data = []

        for entity in feed.entity:
            if entity.HasField('trip_update') and entity.trip_update.trip.trip_id.startswith(line_prefix):
                trip_id = entity.trip_update.trip.trip_id
                stop_updates = []
                for stop_time_update in entity.trip_update.stop_time_update:
                    stop_updates.append(str(stop_time_update).replace('\n', ', '))
                
                line_data.append({
                    "trip_id": trip_id,
                    "stop_time_updates": stop_updates
                })
        
        if line_data:
            return jsonify(line_data)
        else:
            return jsonify({
                "message": "No trip updates found for the specified line_prefix.",
                "line_prefix_searched": line_prefix
            }), 404

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred during debug: {e}"}), 500

@app.route('/debug/all_stops')
def debug_all_stops():
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        stops = set()

        for entity in feed.entity:
            if entity.HasField('trip_update'):
                for stop_time_update in entity.trip_update.stop_time_update:
                    stops.add(stop_time_update.stop_id)
        
        return jsonify(sorted(list(stops)))

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred during debug: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)
