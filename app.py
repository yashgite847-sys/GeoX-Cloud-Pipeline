import os
import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="GeoX — Landslide Early Warning System",
    page_icon="🏔️",
    layout="wide"
)

# Load Database URL from Streamlit Secrets or Environment Variables
DB_URL = st.secrets.get("DATABASE_URL", os.getenv("DATABASE_URL"))

def get_data():
    if not DB_URL:
        st.error("DATABASE_URL secret is missing! Please check Streamlit Cloud Settings -> Secrets.")
        return pd.DataFrame()
    try:
        # Using dsn parameter cleanly prevents port parsing errors
        conn = psycopg2.connect(dsn=DB_URL)
        query = "SELECT * FROM telemetry ORDER BY id DESC LIMIT 50"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return pd.DataFrame()

# Main Header
st.title("🏔️ GeoX — Early Warning System Dashboard")

# Fetch Telemetry Data
df = get_data()

if df.empty:
    st.info("Waiting for telemetry data from GeoX field nodes...")
else:
    # Most Recent Sensor Reading
    latest = df.iloc[0]

    # Alert Level Formatting
    risk_level = str(latest.get('risk_level', 'NORMAL')).upper()
    
    if risk_level == "CRITICAL":
        st.error(f"⚠️ CRITICAL LANDSLIDE RISK DETECTED AT NODE {latest.get('node_id', 'N/A')}")
    elif risk_level == "WARNING":
        st.warning(f"⚡ WARNING: ELEVATED LANDSLIDE RISK AT NODE {latest.get('node_id', 'N/A')}")
    else:
        st.success(f"✅ SYSTEM NORMAL AT NODE {latest.get('node_id', 'N/A')}")

    # Top Metric Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Node ID", str(latest.get('node_id', 'N/A')))
    col2.metric("Rainfall Rate", f"{latest.get('rainfall_mm', 0.0):.1f} mm/h")
    col3.metric("Soil Moisture", f"{latest.get('soil_moisture_0_10cm', 0.0):.1f} %")
    col4.metric("Risk Level", risk_level)
    col5.metric("Landslide Prob.", f"{latest.get('landslide_probability', 0.0) * 100:.1f}%")

    st.markdown("---")

    # Interactive Plots
    st.subheader("📊 Live Telemetry Analytics")
    
    # Sort chronological for plotting
    df_plot = df.sort_values(by="id", ascending=True)

    fig_prob = px.line(
        df_plot, 
        x="created_at" if "created_at" in df_plot.columns else df_plot.index, 
        y="landslide_probability",
        title="Landslide Risk Probability Over Time",
        labels={"landslide_probability": "Probability", "created_at": "Timestamp"},
        markers=True
    )
    fig_prob.update_traces(line_color="#E63946", line_width=2)
    st.plotly_chart(fig_prob, use_container_width=True)

    col_left, col_right = st.columns(2)

    with col_left:
        fig_rain = px.bar(
            df_plot,
            x="created_at" if "created_at" in df_plot.columns else df_plot.index,
            y="rainfall_mm",
            title="Precipitation Intensity (mm/h)",
            labels={"rainfall_mm": "Rainfall (mm)", "created_at": "Timestamp"}
        )
        fig_rain.update_traces(marker_color="#457B9D")
        st.plotly_chart(fig_rain, use_container_width=True)

    with col_right:
        fig_soil = px.line(
            df_plot,
            x="created_at" if "created_at" in df_plot.columns else df_plot.index,
            y="soil_moisture_0_10cm",
            title="Upper Soil Moisture Content (%)",
            labels={"soil_moisture_0_10cm": "Soil Moisture (%)", "created_at": "Timestamp"}
        )
        fig_soil.update_traces(line_color="#2A9D8F", line_width=2)
        st.plotly_chart(fig_soil, use_container_width=True)

    # Detailed Records Table
    st.subheader("📑 Recent Telemetry Logs")
    st.dataframe(df, use_container_width=True)

# Auto-refresh dashboard trigger
if st.button("🔄 Refresh Data"):
    st.rerun()
