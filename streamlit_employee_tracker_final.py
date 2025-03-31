# ====================
# PAGE CONFIG (MUST BE FIRST)
# ====================
import streamlit as st
st.set_page_config(
    page_title="PixsEdit Employee Tracker",
    layout="wide",
    page_icon="🕒",
    initial_sidebar_state="expanded"
)

# ====================
# IMPORTS (AFTER PAGE CONFIG)
# ====================
import os
import datetime
import csv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.message import EmailMessage
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import time
import base64
from streamlit.components.v1 import html
import hashlib
from typing import Optional, Dict, Tuple

# ====================
# CONSTANTS
# ====================
COOKIE_EXPIRY_DAYS = 7  # Session persists for 7 days
SESSION_TIMEOUT_MIN = 30  # Inactivity timeout in minutes

# ====================
# CONFIGURATION
# ====================
def load_config() -> Optional[Dict]:
    """Load configuration from secrets and environment."""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
        
        # Validate secrets exist
        if "GOOGLE_CREDENTIALS" not in st.secrets:
            st.error("Google credentials missing in secrets")
            st.stop()
            
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)

        return {
            "SPREADSHEET_ID": st.secrets["SPREADSHEET_ID"],
            "EMAIL_ADDRESS": st.secrets["EMAIL_ADDRESS"],
            "EMAIL_PASSWORD": st.secrets["EMAIL_PASSWORD"],
            "client": client,
            "AVATAR_DIR": Path("avatars"),
            "SESSION_SECRET": st.secrets.get("SESSION_SECRET", "default-secret-key")
        }
    except Exception as e:
        st.error(f"Configuration error: {str(e)}")
        st.stop()
        return None

# Initialize config
config = load_config()
AVATAR_DIR = config["AVATAR_DIR"]

# Create avatar directory if it doesn't exist
try:
    AVATAR_DIR.mkdir(exist_ok=True)
except Exception as e:
    st.error(f"Failed to create avatar directory: {str(e)}")
    AVATAR_DIR = Path("/tmp/avatars")  # Fallback
    AVATAR_DIR.mkdir(exist_ok=True)

# ====================
# COOKIE MANAGEMENT
# ====================
def get_cookie(name: str) -> Optional[str]:
    """Get cookie value from session state or URL params."""
    if name in st.session_state:
        return st.session_state[name]
    
    params = st.experimental_get_query_params()
    return params.get(name, [None])[0]

def set_cookie(name: str, value: str, days: int = COOKIE_EXPIRY_DAYS) -> None:
    """Set cookie in session state and URL params."""
    st.session_state[name] = value
    st.experimental_set_query_params(**{name: value})

def delete_cookie(name: str) -> None:
    """Remove cookie from session state and URL params."""
    if name in st.session_state:
        del st.session_state[name]
    params = st.experimental_get_query_params()
    if name in params:
        new_params = {k: v for k, v in params.items() if k != name}
        st.experimental_set_query_params(**new_params)

# ====================
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
    """Initialize all required session state variables."""
    required_states = {
        'user': None,
        'row_index': None,
        'persistent_login': False,
        'avatar_uploaded': False,
        'last_action': None,
        'break_started': False,
        'break_ended': False,
        'logout_confirmation': False,
        'credentials_verified': False,
        'last_activity': datetime.datetime.now(),
        'login_time': None,
        'google_sheets_initialized': False
    }
    
    for key, default in required_states.items():
        if key not in st.session_state:
            st.session_state[key] = default

def check_session_timeout() -> bool:
    """Check if session has timed out due to inactivity."""
    if not st.session_state.user:
        return False
        
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = datetime.datetime.now()
        return False
        
    inactive_min = (datetime.datetime.now() - st.session_state.last_activity).total_seconds() / 60
    if inactive_min > SESSION_TIMEOUT_MIN:
        handle_logout()
        st.warning(f"Session timed out after {SESSION_TIMEOUT_MIN} minutes of inactivity")
        return True
    return False

def update_activity() -> None:
    """Update last activity timestamp."""
    st.session_state.last_activity = datetime.datetime.now()

# ====================
# AUTHENTICATION
# ====================
def check_persistent_login() -> None:
    """Check for valid login credentials."""
    if st.session_state.user:
        return
        
    username = get_cookie("username")
    auth_token = get_cookie("auth_token")
    
    if username and auth_token:
        try:
            sheet1, _ = connect_to_google_sheets()
            if not sheet1:
                return
                
            users = sheet1.get_all_values()[1:]  # Skip header
            user_dict = {u[0]: u[1] for u in users if len(u) >= 2}
            
            if username in user_dict:
                salted_pass = config["SESSION_SECRET"] + user_dict[username]
                hashed_pass = hashlib.sha256(salted_pass.encode()).hexdigest()
                
                if hashed_pass == auth_token:
                    st.session_state.update({
                        'user': username,
                        'persistent_login': True,
                        'credentials_verified': True,
                        'login_time': datetime.datetime.now()
                    })
                    st.rerun()
        except Exception as e:
            st.error(f"Login verification failed: {str(e)}")
            clear_auth_cookies()

def clear_auth_cookies() -> None:
    """Clear authentication cookies."""
    delete_cookie("username")
    delete_cookie("auth_token")

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme."""
    apply_cream_theme()
    init_session_state()
    check_persistent_login()

def apply_cream_theme():
    """Apply elegant cream white theme with soft accents."""
    st.markdown("""
    <style>
        :root {
            --primary: #f5f5f0;
            --secondary: #e8e8e3;
            --accent: #8b8b83;
            --text: #333333;
            --highlight: #d4af37;
            --success: #5cb85c;
            --warning: #f0ad4e;
            --danger: #d9534f;
        }
        
        /* Rest of your CSS styles... */
    </style>
    """, unsafe_allow_html=True)

# ====================
# UTILITY FUNCTIONS
# ====================
def format_duration(minutes):
    """Convert minutes to HH:MM format."""
    try:
        hrs = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hrs:02d}:{mins:02d}"
    except:
        return "00:00"

def evaluate_status(break_str, work_str):
    """Evaluate employee status based on break and work time."""
    def to_minutes(t):
        try:
            h, m = map(int, t.split(":"))
            return h * 60 + m
        except:
            return 0

    try:
        break_min = to_minutes(break_str) if break_str else 0
        work_min = to_minutes(work_str) if work_str else 0

        if work_min >= 540 and break_min <= 50:
            return "<span style='color: #5cb85c'>✅ Complete</span>"
        elif break_min > 50:
            return "<span style='color: #d9534f'>❌ Over Break</span>"
        else:
            return "<span style='color: #d9534f'>❌ Incomplete</span>"
    except:
        return ""

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
@st.cache_resource(ttl=300)
def get_google_sheets_client():
    """Get cached Google Sheets client."""
    return config["client"]

def connect_to_google_sheets():
    """Connect to Google Sheets and get required worksheets."""
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(config["SPREADSHEET_ID"])
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        sheet_name = f"Daily Logs {today}"

        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(
                title=sheet_name, 
                rows=100, 
                cols=10
            )
            sheet.append_row([
                "Employee Name", "Login Time", "Logout Time", 
                "Break Start", "Break End", "Break Duration",
                "Total Work Time", "Status"
            ])

        try:
            users_sheet = spreadsheet.worksheet("Registered Employees")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(
                title="Registered Employees", 
                rows=100, 
                cols=2
            )
            users_sheet.append_row(["Username", "Password"])

        return users_sheet, sheet
    except Exception as e:
        st.error(f"Google Sheets connection failed: {str(e)}")
        st.stop()
        return None, None

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components."""
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #8b8b83; font-size: 1.8rem;">PixsEdit Tracker</h1>
            <p style="color: #a0a099; font-size: 0.9rem;">Elegant Time Management</p>
        </div>
        """, unsafe_allow_html=True)
        
        render_avatar_section()
        render_login_section()

# [Rest of your component functions...]

# ====================
# MAIN CONTENT AREAS
# ====================
def render_main_content():
    """Render the appropriate content based on user state."""
    if st.session_state.get('persistent_login') and st.session_state.user:
        if st.session_state.user == "admin":
            render_admin_dashboard()
        else:
            render_employee_dashboard()
    else:
        render_landing_page()

# [Rest of your rendering functions...]

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point."""
    try:
        setup_page()
        
        if check_session_timeout():
            return
            
        update_activity()
        
        if st.session_state.get('persistent_login') or not st.session_state.user:
            render_sidebar()
            render_main_content()
    except Exception as e:
        st.error(f"Application error: {str(e)}")
        st.exception(e)  # Show full traceback for debugging

if __name__ == "__main__":
    main()
