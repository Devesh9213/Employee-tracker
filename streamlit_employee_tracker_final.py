import os
import datetime
import csv
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.message import EmailMessage
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import time
from streamlit.components.v1 import html
from streamlit_autorefresh import st_autorefresh

# ====================
# CONFIGURATION
# ====================
def load_config():
    """Load configuration from secrets and environment."""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)

        return {
            "SPREADSHEET_ID": st.secrets["SPREADSHEET_ID"],
            "EMAIL_ADDRESS": st.secrets["EMAIL_ADDRESS"],
            "EMAIL_PASSWORD": st.secrets["EMAIL_PASSWORD"],
            "client": client,
            "AVATAR_DIR": Path("avatars"),
        }
    except Exception as e:
        st.error(f"Configuration error: {str(e)}")
        st.stop()
        return None

config = load_config()
AVATAR_DIR = config["AVATAR_DIR"]
AVATAR_DIR.mkdir(exist_ok=True)

# Auto-refresh every 30 seconds for live updates
st_autorefresh(interval=30 * 1000, key="data_refresh")

# ====================
# PERSISTENT SESSION MANAGEMENT
# ====================
def setup_persistent_session():
    """Initialize and maintain persistent session using browser localStorage."""
    # Inject JavaScript to handle session persistence
    js = """
    <script>
    // Store session state in localStorage
    function storeState(key, value) {
        localStorage.setItem(key, value);
    }
    
    // Retrieve session state from localStorage
    function getState(key) {
        return localStorage.getItem(key);
    }
    
    // Check for existing session on page load
    function checkSession() {
        const username = getState('username');
        const persistent = getState('persistent_login') === 'true';
        
        if (username && persistent) {
            window.parent.postMessage({
                type: 'STREAMLIT_PERSISTENT_SESSION',
                username: username
            }, '*');
        }
    }
    
    // Run check on page load
    checkSession();
    
    // Listen for Streamlit messages to update localStorage
    window.addEventListener('message', function(event) {
        if (event.data.type === 'STREAMLIT_UPDATE_SESSION') {
            storeState('username', event.data.username || '');
            storeState('persistent_login', event.data.persistent);
        }
    });
    </script>
    """
    html(js, height=0, width=0)

def update_persistent_session(username, persistent):
    """Update the browser's localStorage with current session info."""
    js = f"""
    <script>
    window.parent.postMessage({{
        type: 'STREAMLIT_UPDATE_SESSION',
        username: '{username}',
        persistent: {str(persistent).lower()}
    }}, '*');
    </script>
    """
    html(js, height=0, width=0)

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme."""
    st.set_page_config(
        page_title="🌟 PixsEdit Employee Tracker",
        layout="wide",
        page_icon="🕒",
        initial_sidebar_state="expanded"
    )
    
    # Apply custom CSS
    apply_theme()

def apply_theme():
    """Apply theme styling based on time of day or user preference."""
    current_hour = datetime.datetime.now().hour
    auto_dark = current_hour < 6 or current_hour >= 18
    dark_mode = st.session_state.get('dark_mode', auto_dark)
    
    if dark_mode:
        st.markdown("""
        <style>
            :root {
                --primary-color: #4a90e2;
                --background-color: #1e1e1e;
                --secondary-background-color: #2d2d2d;
                --text-color: #f5f5f5;
                --border-color: #6a6a6a;
            }
            
            .main {
                background-color: var(--background-color);
                color: var(--text-color);
            }
            
            .stButton>button {
                background-color: var(--secondary-background-color) !important;
                color: var(--text-color) !important;
                border: 1px solid var(--border-color) !important;
                transition: all 0.3s ease;
            }
            
            .stButton>button:hover {
                background-color: var(--primary-color) !important;
                transform: translateY(-2px);
            }
            
            .metric-card {
                background-color: var(--secondary-background-color);
                padding: 1rem;
                border-radius: 0.5rem;
                margin-bottom: 1rem;
                border-left: 4px solid var(--primary-color);
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            :root {
                --primary-color: #4a90e2;
                --background-color: #f6f9fc;
                --secondary-background-color: #ffffff;
                --text-color: #333333;
                --border-color: #e1e1e1;
            }
            
            .main {
                background-color: var(--background-color);
            }
            
            .stButton>button {
                background: linear-gradient(90deg, #007cf0, #00dfd8) !important;
                color: white !important;
                border: none !important;
                transition: all 0.3s ease;
            }
            
            .stButton>button:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            .metric-card {
                background-color: var(--secondary-background-color);
                padding: 1rem;
                border-radius: 0.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
                border-left: 4px solid var(--primary-color);
            }
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
            return "✅ Complete"
        elif break_min > 50:
            return "❌ Over Break"
        else:
            return "❌ Incomplete"
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
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
    """Initialize session state variables."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "row_index" not in st.session_state:
        st.session_state.row_index = None
    if "avatar_uploaded" not in st.session_state:
        st.session_state.avatar_uploaded = False
    if "last_action" not in st.session_state:
        st.session_state.last_action = None
    if "break_started" not in st.session_state:
        st.session_state.break_started = False
    if "break_ended" not in st.session_state:
        st.session_state.break_ended = False
    if "persistent_login" not in st.session_state:
        st.session_state.persistent_login = False
    if "dark_mode" not in st.session_state:
        current_hour = datetime.datetime.now().hour
        st.session_state.dark_mode = current_hour < 6 or current_hour >= 18

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components."""
    with st.sidebar:
        st.title("PixsEdit Tracker")
        
        # Theme toggle
        st.session_state.dark_mode = st.toggle(
            "🌙 Dark Mode", 
            value=st.session_state.dark_mode,
            key="dark_mode_toggle"
        )
        apply_theme()
        
        render_avatar_section()
        render_login_section()

def render_avatar_section():
    """Handle avatar upload and display."""
    if st.session_state.user:
        avatar_path = AVATAR_DIR / f"{st.session_state.user}.png"
        if avatar_path.exists():
            st.image(str(avatar_path), width=100, caption=f"Welcome {st.session_state.user}")

        new_avatar = st.file_uploader("Update Avatar", type=["jpg", "jpeg", "png"], key="avatar_uploader")
        if new_avatar:
            with open(avatar_path, "wb") as f:
                f.write(new_avatar.read())
            st.success("Avatar updated!")
            st.session_state.avatar_uploaded = True
            st.rerun()
    else:
        uploaded_avatar = st.file_uploader("Upload Avatar (optional)", type=["jpg", "jpeg", "png"], key="temp_avatar")
        if uploaded_avatar:
            temp_path = AVATAR_DIR / "temp_avatar.png"
            with open(temp_path, "wb") as f:
                f.write(uploaded_avatar.read())
            st.image(str(temp_path), width=100, caption="Preview")

def render_login_section():
    """Handle login/logout functionality."""
    st.markdown("---")
    if st.session_state.user:
        st.session_state.persistent_login = st.checkbox(
            "Keep me logged in", 
            value=st.session_state.persistent_login,
            key="persistent_login_checkbox"
        )
        update_persistent_session(st.session_state.user, st.session_state.persistent_login)
        
        if st.button("🚪 Logout", key="logout_button"):
            logout_user()
    else:
        st.markdown("### Login")
        username = st.text_input("👤 Username", key="username_input")
        password = st.text_input("🔒 Password", type="password", key="password_input")

        col1, col2 = st.columns(2)
        if col1.button("Login", key="login_button"):
            handle_login(username, password)
        if col2.button("Register", key="register_button"):
            handle_registration(username, password)

def logout_user():
    """Handle user logout process."""
    st.session_state.user = None
    st.session_state.row_index = None
    st.session_state.break_started = False
    st.session_state.break_ended = False
    st.session_state.last_action = None
    st.session_state.persistent_login = False
    update_persistent_session("", False)
    st.rerun()

def handle_login(username, password):
    """Process login attempt."""
    if not username or not password:
        st.error("Username and password are required")
        return

    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return

    users = sheet1.get_all_values()[1:]  # Skip header
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

    if username not in user_dict or user_dict[username] != password:
        st.error("Invalid credentials.")
    else:
        st.session_state.user = username
        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return

        # Find existing row or create new one
        rows = sheet2.get_all_values()
        st.session_state.row_index = None
        
        for i, row in enumerate(rows[1:]):  # Skip header
            if row and row[0] == username:
                st.session_state.row_index = i + 2  # +1 for header, +1 for 0-based index
                break

        if username != "admin" and st.session_state.row_index is None:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet2.append_row([username, now, "", "", "", "", "", ""])
            st.session_state.row_index = len(sheet2.get_all_values())

        st.rerun()

def handle_registration(username, password):
    """Process new user registration."""
    if not username or not password:
        st.error("Username and password are required")
        return

    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return

    users = sheet1.get_all_values()[1:]  # Skip header
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

    if username in user_dict:
        st.error("User already exists.")
    else:
        sheet1.append_row([username, password])
        st.success("Registration successful! Please login.")

# ====================
# ADMIN DASHBOARD
# ====================
def render_admin_dashboard():
    """Render the admin dashboard with live updates."""
    st.title("📊 Admin Dashboard")
    sheet1, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return

    try:
        data = sheet2.get_all_records()
        df = pd.DataFrame(data) if data else pd.DataFrame()
        
        # Calculate who is currently on break
        df['On Break Now'] = df.apply(lambda row: 
            pd.notna(row['Break Start']) and pd.isna(row['Break End']), 
            axis=1
        )
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        df = pd.DataFrame()

    render_admin_metrics(sheet1, df)
    render_employee_directory(df)
    render_admin_analytics(df)
    render_reporting_tools(sheet2)

def render_admin_metrics(sheet1, df):
    """Render admin metrics cards with live data."""
    st.subheader("📈 Live Employee Overview")
    col1, col2, col3, col4 = st.columns(4)

    try:
        total_employees = len(sheet1.get_all_values()) - 1
    except:
        total_employees = 0

    active_today = len(df) if not df.empty else 0
    on_break_now = df['On Break Now'].sum() if not df.empty and 'On Break Now' in df.columns else 0
    completed = len(df[df["Status"] == "✅ Complete"]) if not df.empty and "Status" in df.columns else 0

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Total Employees</h3>
                <h1>{total_employees}</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Active Today</h3>
                <h1>{active_today}</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>On Break Now</h3>
                <h1>{on_break_now}</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Completed</h3>
                <h1>{completed}</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Display real-time break status
    if on_break_now > 0:
        st.markdown("### 🚨 Employees Currently on Break")
        on_break_df = df[df['On Break Now']][['Employee Name', 'Break Start']]
        if not on_break_df.empty:
            st.dataframe(on_break_df, use_container_width=True)
        else:
            st.write("No employees currently on break")

def render_employee_directory(df):
    """Render employee directory table."""
    st.subheader("👥 Employee Directory")
    if not df.empty:
        # Format the dataframe for better display
        display_df = df.copy()
        if 'On Break Now' in display_df.columns:
            display_df['On Break Now'] = display_df['On Break Now'].map({True: 'Yes', False: 'No'})
        
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.warning("No employee data available")

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point."""
    try:
        # Initialize session and setup
        init_session_state()
        setup_page()
        setup_persistent_session()
        
        # Check for persistent session from browser storage
        if not st.session_state.user and st.session_state.persistent_login:
            # This would be set from the JavaScript message handler
            if st.session_state.get('username_from_storage'):
                st.session_state.user = st.session_state.username_from_storage
                st.rerun()
        
        # Render the appropriate content
        if st.session_state.user == "admin":
            render_admin_dashboard()
        elif st.session_state.user:
            render_employee_dashboard()
        else:
            render_landing_page()
            
    except Exception as e:
        st.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    main()
