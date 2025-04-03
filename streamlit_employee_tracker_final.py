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
import base64
from streamlit.components.v1 import html

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

# ====================
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
    """Initialize session state variables."""
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'row_index' not in st.session_state:
        st.session_state.row_index = None
    if 'persistent_login' not in st.session_state:
        st.session_state.persistent_login = False
    if 'avatar_uploaded' not in st.session_state:
        st.session_state.avatar_uploaded = False
    if 'last_action' not in st.session_state:
        st.session_state.last_action = None
    if 'break_started' not in st.session_state:
        st.session_state.break_started = False
    if 'break_ended' not in st.session_state:
        st.session_state.break_ended = False
    if 'logout_confirmation' not in st.session_state:
        st.session_state.logout_confirmation = False
    if 'credentials_verified' not in st.session_state:
        st.session_state.credentials_verified = False

def verify_persistent_login():
    """Verify login credentials if not already verified."""
    if st.session_state.persistent_login and not st.session_state.credentials_verified:
        st.write("Verifying persistent login for user: ", st.session_state.user)
        try:
            sheet1, _ = connect_to_google_sheets()
            if sheet1:
                users = sheet1.get_all_values()[1:]  # Skip header
                user_exists = any(user[0] == st.session_state.user for user in users if len(user) >= 2)
                if not user_exists:
                    st.write("User does not exist: ", st.session_state.user)
                    st.session_state.user = None
                    st.session_state.persistent_login = False
                    st.rerun()
                else:
                    st.session_state.credentials_verified = True
                    st.write("User verified: ", st.session_state.user)
        except Exception as e:
            st.error(f"Login verification failed: {str(e)}")
            st.session_state.user = None
            st.session_state.persistent_login = False
            st.rerun()

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme."""
    st.set_page_config(
        page_title="PixsEdit Employee Tracker",
        layout="wide",
        page_icon="🕒",
        initial_sidebar_state="expanded"
    )
    apply_cream_theme()

    init_session_state()
    verify_persistent_login()

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

        .main {
            background-color: var(--primary);
            color: var(--text);
        }

        .sidebar .sidebar-content {
            background-color: var(--secondary) !important;
            background-image: linear-gradient(to bottom, #f8f8f3, #e8e8e3);
        }

        .stButton>button {
            background-color: var(--secondary) !important;
            color: var(--text) !important;
            border: 1px solid var(--accent) !important;
            border-radius: 8px !important;
            transition: all 0.3s ease;
            padding: 0.5rem 1rem;
            font-weight: 500;
        }

        .stButton>button:hover {
            background-color: var(--accent) !important;
            color: white !important;
            border-color: var(--accent) !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }

        .metric-card {
            background-color: white;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            border-left: 4px solid var(--highlight);
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            transition: transform 0.3s ease;
        }

        .metric-card:hover {
            transform: translateY(-5px);
        }

        .metric-card h3 {
            color: var(--accent);
            font-size: 1rem;
            margin-bottom: 0.5rem;
        }

        .metric-card h1, .metric-card h2 {
            color: var(--text);
            margin-top: 0;
        }

        .stTextInput>div>div>input,
        .stTextArea>div>div>textarea {
            background-color: white !important;
            border: 1px solid var(--accent) !important;
            border-radius: 8px !important;
        }

        .stDataFrame {
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }

        .stAlert {
            border-radius: 8px;
        }

        .stProgress>div>div>div {
            background-color: var(--highlight) !important;
        }

        .st-bb {
            background-color: var(--primary);
        }

        .st-at {
            background-color: var(--highlight);
        }

        .st-ax {
            color: var(--text);
        }

        hr {
            border-color: var(--accent);
            opacity: 0.2;
        }

        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--secondary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--accent);
            border-radius: 4px;
        }

        /* Custom tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }

        .stTabs [data-baseweb="tab"] {
            background: var(--secondary) !important;
            border-radius: 8px 8px 0 0 !important;
            padding: 0.5rem 1rem !important;
            transition: all 0.3s ease;
        }

        .stTabs [aria-selected="true"] {
            background: white !important;
            color: var(--highlight) !important;
            font-weight: 600;
        }

        /* Custom success/warning/error messages */
        .stAlert [data-testid="stMarkdownContainer"] {
            color: var(--text);
        }

        .stSuccess {
            background-color: rgba(92, 184, 92, 0.1) !important;
            border-left: 4px solid var(--success) !important;
        }

        .stWarning {
            background-color: rgba(240, 173, 78, 0.1) !important;
            border-left: 4px solid var(--warning) !important;
        }

        .stError {
            background-color: rgba(217, 83, 79, 0.1) !important;
            border-left: 4px solid var(--danger) !important;
        }

        /* Custom avatar styling */
        .avatar-container {
            display: flex;
            justify-content: center;
            margin-bottom: 1.5rem;
        }

        .avatar-image {
            border-radius: 50%;
            border: 3px solid var(--highlight);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }

        .avatar-image:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 16px rgba(0,0,0,0.15);
        }

        /* Landing page styling */
        .landing-header {
            text-align: center;
            padding: 3rem 0;
            background: linear-gradient(to right, #f8f8f3, #ffffff);
            border-radius: 12px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }

        .landing-header h1 {
            color: var(--highlight);
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }

        .landing-header p {
            color: var(--accent);
            font-size: 1.2rem;
            max-width: 700px;
            margin: 0 auto;
        }

        /* Button icons */
        .button-icon {
            margin-right: 8px;
            vertical-align: middle;
        }

        /* Feature cards for landing page */
        .feature-card {
            background-color: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            height: 100%;
        }

        .feature-card h3 {
            color: var (--accent);
            margin-bottom: 0.5rem;
        }

        .feature-card p {
            color: var(--text);
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
            return "<span style='color: #5cb85c'>✅ Complete</span>"
        elif break_min > 50:
            return "<span style='color: #d9534f'>❌ Over Break</span>"
        else:
            return "<span style='color: #d9534f'>❌ Incomplete</span>"
    except:
        return ""

def export_to_csv(sheet):
    """Export sheet data to CSV file."""
    try:
        data = sheet.get_all_values()
        filename = f"Daily_Logs_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)
        return filename
    except Exception as e:
        st.error(f"Export failed: {str(e)}")
        return None

def send_email_with_csv(to_email, file_path):
    """Send email with CSV attachment."""
    try:
        if not os.path.exists(file_path):
            st.error("File not found for email attachment")
            return False

        msg = EmailMessage()
        msg["Subject"] = f"Daily Employee Report - {datetime.datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = config["EMAIL_ADDRESS"]
        msg["To"] = to_email
        msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

        with open(file_path, "rb") as f:
            file_data = f.read()
            msg.add_attachment(
                file_data,
                maintype="text",
                subtype="csv",
                filename=os.path.basename(file_path),
            )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(config["EMAIL_ADDRESS"], config["EMAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email failed: {str(e)}")
        return False

def image_to_base64(image_path):
    """Convert image to base64 for HTML display."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

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

def render_avatar_section():
    """Handle avatar upload and display."""
    if st.session_state.user:
        avatar_path = AVATAR_DIR / f"{st.session_state.user}.png"
        if avatar_path.exists():
            st.markdown(f"""
            <div class="avatar-container">
                <img src="data:image/png;base64,{image_to_base64(avatar_path)}" 
                     class="avatar-image" width="120" height="120" alt="User Avatar">
            </div>
            """, unsafe_allow_html=True)
            st.markdown(f"<p style='text-align: center; font-weight: 500; color: #333333;'>{st.session_state.user}</p>", 
                       unsafe_allow_html=True)

        new_avatar = st.file_uploader("🖼️ Update Avatar", type=["jpg", "jpeg", "png"])
        if new_avatar:
            with open(avatar_path, "wb") as f:
                f.write(new_avatar.read())
            st.success("Avatar updated successfully!")
            st.session_state.avatar_uploaded = True
            time.sleep(1)
            st.rerun()
    else:
        uploaded_avatar = st.file_uploader("🖼️ Upload Avatar (optional)", type=["jpg", "jpeg", "png"])
        if uploaded_avatar:
            temp_path = AVATAR_DIR / "temp_avatar.png"
            with open(temp_path, "wb") as f:
                f.write(uploaded_avatar.read())
            st.markdown(f"""
            <div class="avatar-container">
                <img src="data:image/png;base64,{image_to_base64(temp_path)}" 
                     class="avatar-image" width="100" height="100" alt="Preview Avatar">
            </div>
            """, unsafe_allow_html=True)

def render_login_section():
    """Handle login/logout functionality with persistent sessions."""
    st.markdown("---")
    if st.session_state.user:
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            st.session_state.logout_confirmation = True
            
        if st.session_state.get('logout_confirmation'):
            st.warning("Are you sure you want to logout?")
            col1, col2 = st.columns(2)
            
            if col1.button("✅ Yes, Logout", use_container_width=True, key="confirm_logout"):
                handle_logout()
            
            if col2.button("❌ Cancel", use_container_width=True, key="cancel_logout"):
                st.session_state.logout_confirmation = False
                st.rerun()
    else:
        st.markdown("### 🔐 Authentication")
        username = st.text_input("👤 Username", placeholder="Enter your username", key="username_input")
        password = st.text_input("🔒 Password", type="password", placeholder="Enter your password", key="password_input")

        col1, col2 = st.columns(2)
        if col1.button("Login", use_container_width=True, key="login_btn"):
            handle_login(username, password)
        if col2.button("Register", use_container_width=True, key="register_btn"):
            handle_registration(username, password)

def handle_login(username, password):
    "Process login attempt with"
