from flask import Flask, jsonify, request
import requests
from google.transit import gtfs_realtime_pb2
import time
import os

app = Flask(__name__)

# Configuration
GTFS_RT_URL = "https://www.ambmobilitat.cat/transit/trips-updates/trips.bin"
TARGET_STOP_ID = "000108"   # The bus stop you are interested in

@app.route('/')
def index():
    return "Bus Time API is running. Visit /bus_time to get data."

@app.route('/bus_time')
def get_bus_time():
    # Get parameters from the query string, with default values
    stop_id = request.args.get('stop', default='000108', type=str)
    line_prefix = request.args.get('line_prefix', default='207.', type=str)

    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        now = time.time()
        next_arrival_min = None

        for entity in feed.entity:
            if entity.HasField('trip_update') and entity.trip_update.trip.trip_id.startswith(line_prefix):
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id == stop_id:
                        
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

        if next_arrival_min is not None:
            return jsonify({
                "line": line_prefix.strip('.'),
                "stop": stop_id,
                "arrival_min": next_arrival_min
            })
        else:
            return jsonify({
                "error": f"Could not find arrival for line starting with {line_prefix} at this stop.",
                "stop": stop_id
            }), 404

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

        for entity in feed.entity:
            if entity.HasField('trip_update'):
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id == stop_id:
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
