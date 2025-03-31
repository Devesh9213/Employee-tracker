
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import io
import altair as alt

# --- CONFIG ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes/export?format=csv"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "tracker123"  # You can change this

# --- SESSION STATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🔐 Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.success("Login successful!")
        else:
            st.error("Invalid credentials")
    st.stop()

# --- AUTO REFRESH ---
st_autorefresh(interval=30 * 1000, key="refresh")

# --- TITLE ---
st.title("👥 Live Employee Tracker Dashboard")

# --- LOAD DATA ---
@st.cache_data(ttl=20)
def load_data():
    df = pd.read_csv(SHEET_URL)
    df.fillna("", inplace=True)
    return df

df = load_data()

# --- FORMAT DATE ---
if "Timestamp" in df.columns:
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')

# --- FILTERS ---
st.sidebar.header("🔍 Filters")
names = df["Name"].unique().tolist()
selected_names = st.sidebar.multiselect("Select Employee(s)", names, default=names)

if "Timestamp" in df.columns:
    min_date = df["Timestamp"].min().date()
    max_date = df["Timestamp"].max().date()
    start_date = st.sidebar.date_input("Start Date", min_date)
    end_date = st.sidebar.date_input("End Date", max_date)
else:
    start_date = end_date = None

# --- APPLY FILTERS ---
filtered_df = df[df["Name"].isin(selected_names)]

if start_date and end_date:
    mask = (df["Timestamp"].dt.date >= start_date) & (df["Timestamp"].dt.date <= end_date)
    filtered_df = filtered_df[mask]

# --- STATUS INTERPRETATION ---
def interpret_status(row):
    status = row.get("Status", "").strip().lower()
    if status == "working":
        return "🟢 Working"
    elif status == "break":
        return "🟡 On Break"
    elif status == "logged out":
        return "🔴 Logged Out"
    else:
        return "⚪ Unknown"

filtered_df["Live Status"] = filtered_df.apply(interpret_status, axis=1)

# --- EXPORT ---
csv_buffer = io.StringIO()
filtered_df.to_csv(csv_buffer, index=False)
st.sidebar.download_button("⬇️ Export CSV", csv_buffer.getvalue(), "employee_data.csv", "text/csv")

# --- DASHBOARD DISPLAY ---
st.subheader("📊 Current Employee Status")
for _, row in filtered_df.iterrows():
    with st.container():
        st.markdown(f"### {row.get('Name', 'Unnamed')}")
        st.markdown(f"**Status:** {row['Live Status']}")
        st.markdown(f"**Last Updated:** {row.get('Timestamp', 'N/A')}")
        st.markdown(f"**Total Work:** {row.get('Total Work', 'N/A')}")
        st.markdown(f"**Total Break:** {row.get('Total Break', 'N/A')}")
        st.markdown("---")

# --- ANALYTICS ---
st.subheader("📈 Work Analytics Summary")

# Work Summary Table
work_summary = filtered_df.groupby("Name").agg({
    "Total Work": lambda x: ", ".join(x.dropna().astype(str)),
    "Total Break": lambda x: ", ".join(x.dropna().astype(str))
}).reset_index()

st.dataframe(work_summary)

# Bar Chart Placeholder (convert durations to numbers if needed)
st.subheader("📊 Work Duration Chart (Sample)")
chart_df = filtered_df.copy()
chart_df["Total Work (hrs)"] = pd.to_numeric(chart_df["Total Work"].str.extract(r"(\d+)")[0], errors='coerce')

work_chart = alt.Chart(chart_df.dropna(subset=["Total Work (hrs)"])).mark_bar().encode(
    x='Name',
    y='Total Work (hrs)',
    color='Name'
).properties(title="Total Work Hours")

st.altair_chart(work_chart, use_container_width=True)
