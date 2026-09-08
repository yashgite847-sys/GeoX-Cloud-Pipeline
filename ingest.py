import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import paho.mqtt.client as mqtt
import psycopg2
import joblib
import pandas as pd

# ==========================================
# 0. DUMMY HTTP SERVER (Keeps Render Free Tier Happy)
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"GeoX Ingest Service is active and monitoring.")

    def log_message(self, format, *args):
        # Silence HTTP access logs in Render console
        return

def start_dummy_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"--> [Render HTTP] Binding dummy web server to port {port}")
    server.serve_forever()

# Launch HTTP server on a separate background thread
threading.Thread(target=start_dummy_http_server, daemon=True).start()


# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
MQTT_BROKER = os.environ.get("MQTT_BROKER")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 8883))
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
TOPIC = "geox/aizawl/node1/telemetry"

# Load Pre-trained Machine Learning Model
MODEL_PATH = "landslide_model.joblib"
model = None
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
    print("--> ML Model loaded successfully.")
else:
    print(f"--> WARNING: {MODEL_PATH} not found. Defaulting risk calculations.")


# ==========================================
# 2. DATABASE SETUP
# ==========================================
def init_db():
    try:
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id SERIAL PRIMARY KEY,
                node_id VARCHAR(50),
                rainfall_mm FLOAT,
                soil_moisture_0_10cm FLOAT,
                soil_moisture_10_40cm FLOAT,
                soil_moisture_40_100cm FLOAT,
                slope_angle_deg FLOAT,
                landslide_probability FLOAT,
                risk_level VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("--> Neon PostgreSQL Database table verified.")
    except Exception as e:
        print(f"--> Database Initialization Error: {e}")

init_db()


# ==========================================
# 3. MQTT CALL BACKS & RISK LOGIC
# ==========================================
def calculate_risk(rainfall, soil_0_10, soil_10_40, soil_40_100, slope):
    if model:
        try:
            features = pd.DataFrame([[rainfall, soil_0_10, soil_10_40, soil_40_100, slope]],
                                    columns=['rainfall_mm', 'soil_moisture_0_10cm', 
                                             'soil_moisture_10_40cm', 'soil_moisture_40_100cm', 'slope_angle_deg'])
            prob = float(model.predict_proba(features)[0][1])
        except Exception as e:
            print(f"--> Prediction Error: {e}")
            prob = 0.05
    else:
        prob = 0.05

    if prob > 0.70 or rainfall > 50:
        level = "CRITICAL"
    elif prob > 0.40 or rainfall > 25:
        level = "WARNING"
    else:
        level = "NORMAL"

    return prob, level


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("--> Connected to HiveMQ Cloud MQTT Broker!")
        client.subscribe(TOPIC)
        print(f"--> Subscribed to topic: {TOPIC}")
    else:
        print(f"--> Connection failed with status code {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"--> Incoming Telemetry Payload: {payload}")

        node_id = payload.get("node_id", "node_1")
        rainfall = float(payload.get("rainfall_mm", 0.0))
        soil_0_10 = float(payload.get("soil_moisture_0_10cm", 0.0))
        soil_10_40 = float(payload.get("soil_moisture_10_40cm", 0.0))
        soil_40_100 = float(payload.get("soil_moisture_40_100cm", 0.0))
        slope = float(payload.get("slope_angle_deg", 35.0))

        prob, risk_level = calculate_risk(rainfall, soil_0_10, soil_10_40, soil_40_100, slope)

        # Write to Neon Database
        conn = psycopg2.connect(dsn=DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO telemetry 
            (node_id, rainfall_mm, soil_moisture_0_10cm, soil_moisture_10_40cm, soil_moisture_40_100cm, slope_angle_deg, landslide_probability, risk_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (node_id, rainfall, soil_0_10, soil_10_40, soil_40_100, slope, prob, risk_level))
        conn.commit()
        cur.close()
        conn.close()
        print(f"--> Record Saved to Database: Node {node_id} | Risk: {risk_level} ({prob*100:.1f}%)")

        # Trigger physical buzzer relay if CRITICAL
        if risk_level == "CRITICAL":
            alert_topic = f"geox/aizawl/{node_id}/control"
            client.publish(alert_topic, json.dumps({"relay": "ON", "alarm": "CRITICAL_LANDSLIDE"}))
            print(f"--> 🚨 CRITICAL ALARM PUBLISHED to {alert_topic}")

    except Exception as e:
        print(f"--> Error processing message: {e}")


# ==========================================
# 4. MAIN LOOP
# ==========================================
if __name__ == "__main__":
    client = mqtt.Client(client_id="GeoX_Cloud_Worker", protocol=mqtt.MQTTv311)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message

    print("--> Connecting to HiveMQ...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()
