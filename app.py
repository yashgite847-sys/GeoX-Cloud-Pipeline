import os
import streamlit as st
import psycopg2
import pandas as pd
import time

st.set_page_config(
    page_title="GeoX — Landslide Monitoring Dashboard",
    page_icon="🏔️",
    layout="wide"
)

st.title("🏔️ GeoX — Early Warning System Dashboard")

DB_URL = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))

def get_data():
    if not DB_URL:
        st.error("DATABASE_URL variable is missing! Please configure secrets.")
        return pd.DataFrame()
    try:
        conn = psycopg2.connect(DB_URL)
        df = pd.read_sql_query("SELECT * FROM telemetry ORDER BY id DESC LIMIT 50", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return pd.DataFrame()

placeholder = st.empty()

while True:
    df = get_data()
    with placeholder.container():
        if not df.empty:
            latest = df.iloc[0]
            
            # Status Banner
            status_color = "red" if latest["status"] == "CRITICAL" else "green"
            st.markdown(f"### System Status: :{status_color}[{latest['status']}]")

            # Key Metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Node ID", str(latest["node_id"]))
            c2.metric("Soil Moisture", f"{latest['soil_moisture']}%")
            c3.metric("Tilt Status", "⚠️ ALERT" if latest["tilt_alert"] == 1 else "✅ OK")
            c4.metric("Risk Score", f"{latest['risk_score']}%")

            st.markdown("---")

            # Chart Section
            col_chart, col_map = st.columns([2, 1])
            with col_chart:
                st.subheader("📊 Moisture & Displacement Trends")
                st.line_chart(df[["soil_moisture", "distance_cm"]])

            with col_map:
                st.subheader("📍 Node GPS Location")
                if latest["lat"] != 0.0 and latest["lng"] != 0.0:
                    map_df = pd.DataFrame({'lat': [latest["lat"]], 'lon': [latest["lng"]]})
                    st.map(map_df, zoom=12)
                else:
                    st.info("No GPS fix available.")

            st.markdown("---")
            st.subheader("📋 Recent Telemetry Logs")
            st.dataframe(df[["timestamp", "node_id", "soil_moisture", "temp_c", "humidity", "risk_score", "status"]], use_container_width=True)

        else:
            st.info("Waiting for data from GeoX field nodes...")
            
    time.sleep(3)