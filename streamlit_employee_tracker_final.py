
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import io
import altair as alt

# --- SECURE GOOGLE SHEETS CONNECTION ---
creds_dict = st.secrets["gcp_service_account"]
scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(credentials)

# Open Google Sheet and worksheet
sheet_url = "https://docs.google.com/spreadsheets/d/1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"
worksheet = gc.open_by_url(sheet_url).sheet1
data = worksheet.get_all_records()
df = pd.DataFrame(data)

# --- CONFIG ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "tracker123"

# --- SESSION STATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "username" not in st.session_state:
    st.session_state.username = ""

# --- LOGIN ---
def login():
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.session_state.user_role = "admin"
            st.success("Admin login successful!")
        elif username and password == "":
            st.session_state.authenticated = True
            st.session_state.user_role = "employee"
            st.session_state.username = username
            st.success(f"Welcome, {username}!")
        else:
            st.error("Invalid credentials or format. Employees use only their name as username (no password).")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- AUTO REFRESH ---
st_autorefresh(interval=30 * 1000, key="refresh")

# --- FORMAT DATE ---
if "Timestamp" in df.columns:
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors='coerce')

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

df["Live Status"] = df.apply(interpret_status, axis=1)

# --- ADMIN DASHBOARD ---
def admin_view():
    st.title("👥 Admin Dashboard")

    names = df["Name"].unique().tolist()
    selected_names = st.sidebar.multiselect("Select Employee(s)", names, default=names)

    if "Timestamp" in df.columns:
        min_date = df["Timestamp"].min().date()
        max_date = df["Timestamp"].max().date()
        start_date = st.sidebar.date_input("Start Date", min_date)
        end_date = st.sidebar.date_input("End Date", max_date)
    else:
        start_date = end_date = None

    filtered_df = df[df["Name"].isin(selected_names)]

    if start_date and end_date:
        mask = (filtered_df["Timestamp"].dt.date >= start_date) & (filtered_df["Timestamp"].dt.date <= end_date)
        filtered_df = filtered_df[mask]

    # --- Export ---
    csv_buffer = io.StringIO()
    filtered_df.to_csv(csv_buffer, index=False)
    st.sidebar.download_button("⬇️ Export CSV", csv_buffer.getvalue(), "employee_data.csv", "text/csv")

    # --- Live Statuses ---
    st.subheader("📊 Current Employee Status")
    for _, row in filtered_df.iterrows():
        with st.container():
            st.markdown(f"### {row.get('Name', 'Unnamed')}")
            st.markdown(f"**Status:** {row['Live Status']}")
            st.markdown(f"**Last Updated:** {row.get('Timestamp', 'N/A')}")
            st.markdown(f"**Total Work:** {row.get('Total Work', 'N/A')}")
            st.markdown(f"**Total Break:** {row.get('Total Break', 'N/A')}")
            st.markdown("---")

    # --- Analytics ---
    st.subheader("📈 Work Analytics Summary")
    work_summary = filtered_df.groupby("Name").agg({
        "Total Work": lambda x: ", ".join(x.dropna().astype(str)),
        "Total Break": lambda x: ", ".join(x.dropna().astype(str))
    }).reset_index()
    st.dataframe(work_summary)

    chart_df = filtered_df.copy()
    chart_df["Total Work (hrs)"] = pd.to_numeric(chart_df["Total Work"].str.extract(r"(\d+)")[0], errors='coerce')
    work_chart = alt.Chart(chart_df.dropna(subset=["Total Work (hrs)"])).mark_bar().encode(
        x='Name',
        y='Total Work (hrs)',
        color='Name'
    ).properties(title="Total Work Hours")
    st.altair_chart(work_chart, use_container_width=True)

# --- EMPLOYEE DASHBOARD ---
def employee_view(username):
    st.title(f"👤 Welcome, {username}")

    personal_df = df[df["Name"].str.lower() == username.lower()]

    if personal_df.empty:
        st.warning("No data found for your name.")
        return

    latest = personal_df.sort_values("Timestamp", ascending=False).iloc[0]
    st.markdown(f"**Current Status:** {latest['Live Status']}")
    st.markdown(f"**Last Updated:** {latest.get('Timestamp', 'N/A')}")
    st.markdown(f"**Total Work:** {latest.get('Total Work', 'N/A')}")
    st.markdown(f"**Total Break:** {latest.get('Total Break', 'N/A')}")

    st.subheader("📆 Activity History")
    st.dataframe(personal_df.sort_values("Timestamp", ascending=False))

    csv_buffer = io.StringIO()
    personal_df.to_csv(csv_buffer, index=False)
    st.download_button("⬇️ Download My Data", csv_buffer.getvalue(), f"{username}_data.csv", "text/csv")

# --- ROLE BASED VIEW ---
if st.session_state.user_role == "admin":
    admin_view()
elif st.session_state.user_role == "employee":
    employee_view(st.session_state.username)
