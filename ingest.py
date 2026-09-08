import os
import json
import ssl
import joblib
import numpy as np
import psycopg2
import paho.mqtt.client as mqtt

# Environment Variables
BROKER   = os.getenv("MQTT_BROKER", "4cb3de54aa5e4ab78741434c63f87829.s1.eu.hivemq.cloud")
PORT     = int(os.getenv("MQTT_PORT", 8883))
USER     = os.getenv("MQTT_USER", "geox_node1")
PASSWORD = os.getenv("MQTT_PASSWORD", "Geox1234!")
DB_URL   = os.getenv("DATABASE_URL")

TOPIC_DATA  = "geox/landslide/data"
TOPIC_ALERT = "geox/alerts/command"

# Load ML Model
try:
    model = joblib.load("landslide_model.joblib")
    print("[ML] Loaded Aizawl ML Model.")
except Exception as e:
    model = None
    print(f"[ML WARN] Model load failed: {e}")

def init_db():
    if not DB_URL:
        print("[DB WARN] DATABASE_URL not set.")
        return
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            node_id VARCHAR(50),
            soil_moisture REAL,
            temp_c REAL,
            humidity REAL,
            vib_alert INT,
            tilt_alert INT,
            distance_cm REAL,
            lat REAL,
            lng REAL,
            risk_score REAL,
            status VARCHAR(20)
        );
    ''')
    conn.commit()
    conn.close()
    print("[DB] PostgreSQL Table Verified.")

def evaluate_risk(data):
    soil = float(data.get("soil_moisture", 0))
    temp = float(data.get("temp_c", 0))
    hum = float(data.get("humidity", 0))
    vib = int(data.get("vib_alert", 0))
    tilt = int(data.get("tilt_alert", 0))
    dist = float(data.get("distance_cm", 0))

    if model:
        features = np.array([[0, 0, 0, 0, 0, 0, soil, soil, 0, 0, 0.33, temp, 6, 180, 1]])
        risk_prob = float(model.predict_proba(features)[0][1]) * 100.0
    else:
        risk_prob = (soil * 0.4) + (vib * 30) + (tilt * 30)

    status = "CRITICAL" if risk_prob >= 70.0 or tilt == 1 or vib == 1 else "NORMAL"
    return round(risk_prob, 2), status

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Cloud Engine Active & Connected to HiveMQ.")
        client.subscribe(TOPIC_DATA)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        risk_score, status = evaluate_risk(data)

        if status == "CRITICAL":
            client.publish(TOPIC_ALERT, "TRIGGER_ALERT")
            print(f"[ALERT] High Risk ({risk_score}%) -> Published TRIGGER_ALERT")
        else:
            client.publish(TOPIC_ALERT, "CLEAR_ALERT")

        if DB_URL:
            conn = psycopg2.connect(DB_URL)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO telemetry 
                (node_id, soil_moisture, temp_c, humidity, vib_alert, tilt_alert, distance_cm, lat, lng, risk_score, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                data.get("node_id"), data.get("soil_moisture"), data.get("temp_c"),
                data.get("humidity"), data.get("vib_alert"), data.get("tilt_alert"),
                data.get("distance_cm"), data.get("lat"), data.get("lng"),
                risk_score, status
            ))
            conn.commit()
            conn.close()
            print(f"[LOG] Node: {data.get('node_id')} | Risk: {risk_score}% | Status: {status}")

    except Exception as e:
        print(f"[ERR] Processing error: {e}")

if __name__ == "__main__":
    init_db()
    client = mqtt.Client(client_id="GeoX_Cloud_Worker", protocol=mqtt.MQTTv311)
    client.username_pw_set(USER, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()