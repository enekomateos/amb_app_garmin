from flask import Flask, jsonify
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
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(GTFS_RT_URL)
        response.raise_for_status()
        feed.ParseFromString(response.content)

        now = time.time()
        next_arrival_min = None
        trip_id_for_next_arrival = None

        for entity in feed.entity:
            if entity.HasField('trip_update'):
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id == TARGET_STOP_ID:
                        
                        arrival = stop_time_update.arrival
                        departure = stop_time_update.departure
                        
                        # Use departure time if arrival time is not available
                        event_time = None
                        if stop_time_update.HasField('arrival'):
                            event_time = arrival.time
                        elif stop_time_update.HasField('departure'):
                            event_time = departure.time

                        if event_time:
                            time_diff_min = round((event_time - now) / 60)
                            
                            if time_diff_min >= 0:
                                if next_arrival_min is None or time_diff_min < next_arrival_min:
                                    next_arrival_min = time_diff_min
                                    trip_id_for_next_arrival = entity.trip_update.trip.trip_id

        if next_arrival_min is not None:
            return jsonify({
                "stop": TARGET_STOP_ID,
                "arrival_min": next_arrival_min,
                "trip_id_found": trip_id_for_next_arrival
            })
        else:
            return jsonify({
                "error": "Could not find any scheduled arrivals or departures for this stop.",
                "stop": TARGET_STOP_ID
            }), 404

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch GTFS data: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)
