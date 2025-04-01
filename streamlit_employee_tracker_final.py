import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# ---- Google Sheets Setup ----
GOOGLE_CREDENTIALS = """
<PASTE YOUR SERVICE ACCOUNT JSON HERE>
"""

SPREADSHEET_ID = "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"

# Authorize
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_dict = json.loads(GOOGLE_CREDENTIALS)
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
client = gspread.authorize(credentials)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1  # Use the first sheet

# File to store registered users
USER_FILE = "users.txt"

# Load or create user file
if not os.path.exists(USER_FILE):
    with open(USER_FILE, "w") as f:
        pass

with open(USER_FILE, "r") as f:
    USERS = [line.strip() for line in f.readlines()]

# ---- Session Init ----
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

st.title("🕒 Employee Login System")

# ---- Registration ----
with st.expander("📝 New User? Register here"):
    new_user = st.text_input("Enter new username", key="reg_user")
    if st.button("Register"):
        if new_user.lower() in USERS:
            st.warning("Username already exists.")
        elif new_user.strip() == "":
            st.error("Please enter a valid name.")
        else:
            with open(USER_FILE, "a") as f:
                f.write(f"{new_user.lower()}\n")
            USERS.append(new_user.lower())
            st.success(f"User '{new_user}' registered! You can now log in.")

# ---- Login ----
if not st.session_state.logged_in:
    st.subheader("Login")
    username = st.text_input("Username", key="login_username")

    if st.button("Login"):
        if username.lower() in USERS:
            st.session_state.logged_in = True
            st.session_state.username = username.lower()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([username.lower(), "Login", timestamp])
            st.success(f"Logged in as {username}")
        else:
            st.error("User not found! Please register first.")

# ---- Logged In View ----
else:
    st.success(f"Welcome, {st.session_state.username} 👋")
    st.write("You're currently logged in.")

    if st.button("Logout"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([st.session_state.username, "Logout", timestamp])
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.success("Logged out successfully.")

# ---- Log Viewer ----
with st.expander("📄 View Log History"):
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    st.dataframe(df)
