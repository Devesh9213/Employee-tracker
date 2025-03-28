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
from streamlit_js_eval import streamlit_js_eval
from typing import Optional, Dict, Any, Tuple, List, Union
from dataclasses import dataclass
from enum import Enum, auto
import hashlib
import time
from functools import wraps
import logging

# ====================
# SETUP & CONSTANTS
# ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STANDARD_WORK_HOURS = 8 * 60  # 8 hours in minutes
MAX_BREAK_MINUTES = 50
BREAK_WARNING_THRESHOLD = 60  # 1 hour in minutes
SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds

class ThemeMode(Enum):
    LIGHT = auto()
    DARK = auto()
    SYSTEM = auto()

class EmployeeStatus(Enum):
    ACTIVE = "Active"
    ON_BREAK = "On Break"
    COMPLETED = "Completed"
    INCOMPLETE = "Incomplete"
    OVER_BREAK = "Over Break"

# ====================
# DATA CLASSES
# ====================
@dataclass
class EmployeeRecord:
    name: str
    login_time: Optional[str] = None
    logout_time: Optional[str] = None
    break_start: Optional[str] = None
    break_end: Optional[str] = None
    break_duration: Optional[str] = None
    work_time: Optional[str] = None
    status: Optional[str] = None
    overtime: Optional[str] = None

@dataclass
class AppConfig:
    spreadsheet_id: str
    email_address: str
    email_password: str
    client: Any
    avatar_dir: Path
    session_timeout: int = SESSION_TIMEOUT

# ====================
# DECORATORS & HELPERS
# ====================
def retry(max_retries=3, delay=1):
    """Decorator to retry operations with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    time.sleep(delay * (2 ** attempt))
            raise last_exception if last_exception else Exception("Unknown error")
        return wrapper
    return decorator

def hash_password(password: str) -> str:
    """Securely hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_session_timeout():
    """Check if session has timed out"""
    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = time.time()
    
    current_time = time.time()
    elapsed = current_time - st.session_state.last_activity
    
    if elapsed > st.session_state.get('session_timeout', SESSION_TIMEOUT):
        st.session_state.user = None
        st.session_state.row_index = None
        st.warning("Session timed out due to inactivity. Please login again.")
        st.rerun()
    
    st.session_state.last_activity = current_time

# ====================
# CONFIGURATION
# ====================
def load_config() -> Optional[AppConfig]:
    """Load configuration from secrets and environment"""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
        
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        
        avatar_dir = Path("avatars")
        avatar_dir.mkdir(exist_ok=True)
        
        return AppConfig(
            spreadsheet_id=st.secrets["SPREADSHEET_ID"],
            email_address=st.secrets["EMAIL_ADDRESS"],
            email_password=st.secrets["EMAIL_PASSWORD"],
            client=client,
            avatar_dir=avatar_dir
        )
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        st.error("Failed to initialize application configuration. Please contact support.")
        return None

config = load_config()
if config is None:
    st.stop()

# ====================
# THEME MANAGEMENT
# ====================
def get_system_theme() -> ThemeMode:
    """Detect system theme preference using JavaScript evaluation"""
    try:
        is_dark = streamlit_js_eval(
            js_expressions='window.matchMedia("(prefers-color-scheme: dark)").matches', 
            want_output=True
        )
        return ThemeMode.DARK if is_dark else ThemeMode.LIGHT
    except:
        current_hour = datetime.datetime.now().hour
        return ThemeMode.DARK if current_hour < 6 or current_hour >= 18 else ThemeMode.LIGHT

def apply_theme(theme_mode: ThemeMode) -> Dict[str, Any]:
    """Apply the selected theme with responsive design"""
    effective_theme = theme_mode
    if theme_mode == ThemeMode.SYSTEM:
        effective_theme = get_system_theme()
    
    theme_colors = {
        ThemeMode.DARK: {
            "primary": "#1e1e1e",
            "secondary": "#2d2d2d",
            "text": "#f5f5f5",
            "card": "#2d2d2d",
            "button": "#333333",
            "button_text": "#ffffff",
            "border": "#444444",
            "plot_bg": "#1e1e1e",
            "paper_bg": "#1e1e1e",
            "font_color": "#f5f5f5",
            "success": "#4CAF50",
            "warning": "#FFC107",
            "error": "#F44336"
        },
        ThemeMode.LIGHT: {
            "primary": "#f6f9fc",
            "secondary": "#ffffff",
            "text": "#333333",
            "card": "#ffffff",
            "button": "linear-gradient(90deg, #007cf0, #00dfd8)",
            "button_text": "white",
            "border": "#e0e0e0",
            "plot_bg": "#ffffff",
            "paper_bg": "#ffffff",
            "font_color": "#333333",
            "success": "#2e7d32",
            "warning": "#ed6c02",
            "error": "#d32f2f"
        }
    }.get(effective_theme, {})
    
    theme_css = f"""
    <style>
        :root {{
            --primary-bg: {theme_colors["primary"]};
            --secondary-bg: {theme_colors["secondary"]};
            --text-color: {theme_colors["text"]};
            --card-bg: {theme_colors["card"]};
            --button-bg: {theme_colors["button"]};
            --button-text: {theme_colors["button_text"]};
            --border-color: {theme_colors["border"]};
            --success-color: {theme_colors["success"]};
            --warning-color: {theme_colors["warning"]};
            --error-color: {theme_colors["error"]};
        }}
        
        html, body, .main {{
            background-color: var(--primary-bg);
            color: var(--text-color);
        }}
        
        .stApp {{
            background-color: var(--primary-bg);
        }}
        
        .metric-card {{
            background-color: var(--card-bg);
            padding: 1.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid var(--border-color);
        }}
        
        .stButton>button {{
            background: var(--button-bg);
            color: var(--button-text);
            border-radius: 0.5rem;
            padding: 0.5rem 1rem;
            border: none;
            transition: all 0.3s ease;
        }}
        
        .stButton>button:hover {{
            opacity: 0.9;
            transform: scale(1.02);
        }}
        
        .stTextInput>div>div>input, 
        .stTextArea>div>div>textarea,
        .stSelectbox>div>div>select {{
            background-color: var(--secondary-bg);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }}
        
        .stDataFrame {{
            background-color: var(--secondary-bg);
        }}
        
        .stAlert {{
            background-color: var(--secondary-bg);
            border: 1px solid var(--border-color);
        }}
        
        .success-message {{
            color: var(--success-color);
        }}
        
        .warning-message {{
            color: var(--warning-color);
        }}
        
        .error-message {{
            color: var(--error-color);
        }}
        
        @media (max-width: 768px) {{
            .metric-card {{
                padding: 1rem;
                margin-bottom: 0.5rem;
            }}
            
            .stButton>button {{
                padding: 0.4rem 0.8rem;
                font-size: 0.9rem;
            }}
            
            .column {{
                padding: 0.5rem !important;
            }}
        }}
    </style>
    """
    
    plotly_template = {
        'layout': {
            'plot_bgcolor': theme_colors["plot_bg"],
            'paper_bgcolor': theme_colors["paper_bg"],
            'font': {'color': theme_colors["font_color"]}
        }
    }
    
    st.markdown(theme_css, unsafe_allow_html=True)
    return plotly_template

# ====================
# UTILITY FUNCTIONS
# ====================
def format_duration(minutes: float) -> str:
    """Convert minutes to HH:MM format"""
    try:
        hrs = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hrs:02}:{mins:02}"
    except (TypeError, ValueError):
        return "00:00"

def time_str_to_minutes(time_str: str) -> int:
    """Convert time string (HH:MM) to minutes"""
    if not time_str:
        return 0
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0

def evaluate_status(break_duration: str, work_duration: str) -> str:
    """Evaluate employee status based on break and work time"""
    break_min = time_str_to_minutes(break_duration)
    work_min = time_str_to_minutes(work_duration)
    
    if work_min >= STANDARD_WORK_HOURS and break_min <= MAX_BREAK_MINUTES:
        return EmployeeStatus.COMPLETED.value
    elif break_min > MAX_BREAK_MINUTES:
        return EmployeeStatus.OVER_BREAK.value
    return EmployeeStatus.INCOMPLETE.value

def calculate_overtime(login_time: datetime.datetime, 
                      logout_time: datetime.datetime, 
                      break_mins: int) -> float:
    """Calculate overtime hours"""
    total_mins = (logout_time - login_time).total_seconds() / 60
    worked_mins = total_mins - break_mins
    overtime = max(0, worked_mins - STANDARD_WORK_HOURS)
    return round(overtime / 60, 2)  # Convert to hours with 2 decimal places

@retry(max_retries=3, delay=1)
def export_to_csv(sheet) -> Optional[str]:
    """Export sheet data to CSV file with retry logic"""
    try:
        data = sheet.get_all_values()
        filename = f"Daily_Logs_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)
        return filename
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        st.error("Failed to export data. Please try again.")
        return None

@retry(max_retries=3, delay=1)
def send_email_with_csv(to_email: str, file_path: str) -> bool:
    """Send email with CSV attachment with retry logic"""
    try:
        if not os.path.exists(file_path):
            st.error("File not found for email attachment")
            return False

        msg = EmailMessage()
        msg['Subject'] = 'Daily Employee Report'
        msg['From'] = config.email_address
        msg['To'] = to_email
        msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

        with open(file_path, 'rb') as f:
            file_data = f.read()
            msg.add_attachment(
                file_data, 
                maintype="application", 
                subtype="octet-stream", 
                filename=os.path.basename(file_path)
            )

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(config.email_address, config.email_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email failed: {str(e)}")
        st.error("Failed to send email. Please check email settings.")
        return False

def get_current_datetime_str() -> str:
    """Get current datetime as formatted string"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def validate_email(email: str) -> bool:
    """Simple email validation"""
    return "@" in email and "." in email.split("@")[-1]

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
@retry(max_retries=3, delay=1)
def connect_to_google_sheets() -> Tuple[Any, Any]:
    """Connect to Google Sheets with retry logic"""
    try:
        spreadsheet = config.client.open_by_key(config.spreadsheet_id)
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        sheet_name = f"Daily Logs {today}"

        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(
                title=sheet_name, 
                rows="100", 
                cols="10"
            )
            sheet.append_row([
                "Employee Name", "Login Time", "Logout Time", 
                "Break Start", "Break End", "Break Duration", 
                "Total Work Time", "Status", "Overtime"
            ])

        try:
            users_sheet = spreadsheet.worksheet("Registered Employees")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(
                title="Registered Employees", 
                rows="100", 
                cols="3"  # Added column for hashed password
            )
            users_sheet.append_row(["Username", "Hashed Password", "Last Login"])

        return users_sheet, sheet
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {str(e)}")
        st.error("Failed to connect to Google Sheets. Please try again later.")
        return None, None

def get_employee_record(sheet, row_index: int) -> EmployeeRecord:
    """Get employee record from sheet row with error handling"""
    try:
        row = sheet.row_values(row_index)
        return EmployeeRecord(
            name=row[0] if len(row) > 0 else "",
            login_time=row[1] if len(row) > 1 else None,
            logout_time=row[2] if len(row) > 2 else None,
            break_start=row[3] if len(row) > 3 else None,
            break_end=row[4] if len(row) > 4 else None,
            break_duration=row[5] if len(row) > 5 else None,
            work_time=row[6] if len(row) > 6 else None,
            status=row[7] if len(row) > 7 else None,
            overtime=row[8] if len(row) > 8 else None
        )
    except Exception as e:
        logger.error(f"Error getting employee record: {str(e)}")
        return EmployeeRecord(name="")

# ====================
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
    """Initialize session state variables"""
    default_values = {
        'user': None,
        'row_index': None,
        'avatar_uploaded': False,
        'theme': ThemeMode.SYSTEM,
        'plotly_template': None,
        'last_activity': time.time(),
        'session_timeout': SESSION_TIMEOUT
    }
    
    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value
    
    if st.session_state.plotly_template is None:
        st.session_state.plotly_template = apply_theme(st.session_state.theme)

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme"""
    try:
        st.set_page_config(
            page_title="🌟 PixsEdit Employee Tracker", 
            layout="wide",
            page_icon="🕒",
            initial_sidebar_state="expanded"
        )
        
        # Apply theme if not already set
        if 'theme' not in st.session_state:
            st.session_state.theme = ThemeMode.SYSTEM
            st.session_state.plotly_template = apply_theme(st.session_state.theme)
        
    except Exception as e:
        logger.error(f"Page setup error: {str(e)}")
        st.error("Failed to initialize page configuration.")

# ====================
# AUTHENTICATION
# ====================
def handle_login(username: str, password: str):
    """Process login attempt with enhanced security"""
    if not username or not password:
        st.error("Username and password are required")
        return
        
    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return
        
    try:
        users = sheet1.get_all_values()[1:]  # Skip header
        user_dict = {u[0]: (u[1], u[2] if len(u) > 2 else None) for u in users if len(u) >= 2}
        
        if username not in user_dict:
            st.error("Invalid credentials.")
            return
            
        stored_hash, last_login = user_dict[username]
        input_hash = hash_password(password)
        
        if stored_hash != input_hash:
            st.error("Invalid credentials.")
            return
            
        # Update last login time
        try:
            user_row = None
            for i, row in enumerate(sheet1.get_all_values(), start=1):
                if row and row[0] == username:
                    user_row = i
                    break
            
            if user_row:
                sheet1.update_cell(user_row, 3, get_current_datetime_str())
        except Exception as e:
            logger.warning(f"Couldn't update last login time: {str(e)}")
        
        st.session_state.user = username
        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        rows = sheet2.get_all_values()
        st.session_state.row_index = None
        for i, row in enumerate(rows[1:], start=2):  # Skip header
            if row and row[0] == username:
                st.session_state.row_index = i
                break

        if username != "admin" and st.session_state.row_index is None:
            sheet2.append_row([username, get_current_datetime_str()] + [""]*7)
            st.session_state.row_index = len(sheet2.get_all_values())
        
        st.rerun()
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        st.error("Authentication failed. Please try again.")

def handle_registration(username: str, password: str, confirm_password: str):
    """Process new user registration with validation"""
    if not username or not password:
        st.error("Username and password are required")
        return
        
    if password != confirm_password:
        st.error("Passwords do not match")
        return
        
    if len(password) < 8:
        st.error("Password must be at least 8 characters")
        return
        
    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return
        
    try:
        users = sheet1.get_all_values()[1:]  # Skip header
        existing_users = {u[0] for u in users if u}
        
        if username in existing_users:
            st.error("Username already exists.")
            return
            
        hashed_password = hash_password(password)
        sheet1.append_row([username, hashed_password, get_current_datetime_str()])
        st.success("Registration successful! Please login.")
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        st.error("Registration failed. Please try again.")

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components with session timeout check"""
    check_session_timeout()
    
    with st.sidebar:
        try:
            st.title("PixsEdit Tracker")
            st.caption(f"🌓 Current theme: {st.session_state.theme.name.capitalize()}")
            
            render_theme_selector()
            render_avatar_section()
            render_login_section()
        except Exception as e:
            logger.error(f"Sidebar error: {str(e)}")
            st.error("Failed to render sidebar components.")

def render_theme_selector():
    """Render theme selection dropdown"""
    try:
        theme_options = [t.name.capitalize() for t in ThemeMode]
        current_theme = st.session_state.theme.name.capitalize()
        
        selected_theme = st.selectbox(
            "Theme",
            theme_options,
            index=theme_options.index(current_theme) if current_theme in theme_options else 0
        )
        
        if selected_theme.lower() != st.session_state.theme.name.lower():
            st.session_state.theme = ThemeMode[selected_theme.upper()]
            st.session_state.plotly_template = apply_theme(st.session_state.theme)
            st.rerun()
    except Exception as e:
        logger.error(f"Theme selector error: {str(e)}")

def render_avatar_section():
    """Handle avatar upload and display with validation"""
    try:
        if st.session_state.user:
            avatar_path = config.avatar_dir / f"{st.session_state.user}.png"
            if avatar_path.exists():
                st.image(str(avatar_path), width=100, caption=f"Welcome {st.session_state.user}")
            
            new_avatar = st.file_uploader("Update Avatar", type=["jpg", "jpeg", "png"], 
                                         accept_multiple_files=False)
            if new_avatar:
                if new_avatar.size > 2 * 1024 * 1024:  # 2MB limit
                    st.error("Avatar size must be less than 2MB")
                    return
                
                with open(avatar_path, "wb") as f:
                    f.write(new_avatar.read())
                st.success("Avatar updated!")
                st.session_state.avatar_uploaded = True
                st.rerun()
    except Exception as e:
        logger.error(f"Avatar error: {str(e)}")
        st.error("Failed to process avatar.")

def render_login_section():
    """Handle login/logout functionality"""
    try:
        st.markdown("---")
        if st.session_state.user:
            if st.button("🚪 Logout", key="logout_button"):
                st.session_state.user = None
                st.session_state.row_index = None
                st.rerun()
        else:
            with st.form("auth_form"):
                st.markdown("### Login / Register")
                username = st.text_input("👤 Username", key="auth_username")
                password = st.text_input("🔒 Password", type="password", key="auth_password")
                
                if st.form_submit_button("Login"):
                    handle_login(username, password)
                
                # Registration section
                with st.expander("New User Registration"):
                    reg_username = st.text_input("👤 Choose Username", key="reg_username")
                    reg_password = st.text_input("🔒 Choose Password", type="password", key="reg_password")
                    confirm_password = st.text_input("🔒 Confirm Password", type="password", key="confirm_password")
                    
                    if st.button("Register", key="register_button"):
                        handle_registration(reg_username, reg_password, confirm_password)
    except Exception as e:
        logger.error(f"Login section error: {str(e)}")
        st.error("Authentication service unavailable. Please try again later.")

# ====================
# ADMIN DASHBOARD
# ====================
def render_admin_dashboard():
    """Render the admin dashboard with tabs"""
    try:
        st.title("📊 Admin Dashboard")
        
        sheet1, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        try:
            data = sheet2.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.warning(f"Failed to load sheet data: {str(e)}")
            df = pd.DataFrame()
        
        tab1, tab2, tab3 = st.tabs(["Overview", "Employee Management", "Reporting"])
        
        with tab1:
            render_admin_metrics(sheet1, df)
            render_employee_directory(df)
        
        with tab2:
            render_employee_management(sheet1)
        
        with tab3:
            render_admin_analytics(df)
            render_reporting_tools(sheet2)
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        st.error("Failed to load admin dashboard. Please try again.")

def render_admin_metrics(sheet1, df: pd.DataFrame):
    """Render admin metrics cards with enhanced visuals"""
    try:
        st.subheader("📈 Employee Overview")
        cols = st.columns(4)
        
        try:
            total_employees = len(sheet1.get_all_values()) - 1  # Subtract header
        except:
            total_employees = 0
        
        active_today = len(df) if not df.empty else 0
        on_break = len(df[df['Break Start'].notna() & df['Break End'].isna()]) if not df.empty else 0
        completed = len(df[df['Status'] == EmployeeStatus.COMPLETED.value]) if not df.empty and 'Status' in df.columns else 0
        
        metrics = [
            ("Total Employees", total_employees, "#4e79a7"),
            ("Active Today", active_today, "#f28e2b"),
            ("On Break", on_break, "#e15759"),
            ("Completed", completed, "#59a14f")
        ]
        
        for col, (title, value, color) in zip(cols, metrics):
            with col:
                st.markdown(f"""
                <div class="metric-card" style="border-left: 4px solid {color}">
                    <h3 style="color: {color}">{title}</h3>
                    <h1>{value}</h1>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}")
        st.error("Failed to load metrics.")

def render_employee_directory(df: pd.DataFrame):
    """Render employee directory table with sorting"""
    try:
        st.subheader("👥 Employee Directory")
        if not df.empty:
            # Add filtering options
            col1, col2 = st.columns(2)
            with col1:
                status_filter = st.multiselect(
                    "Filter by Status",
                    options=df['Status'].unique() if 'Status' in df.columns else [],
                    default=df['Status'].unique() if 'Status' in df.columns else []
                )
            
            with col2:
                sort_by = st.selectbox(
                    "Sort by",
                    options=["Login Time", "Work Time", "Status"],
                    index=0
                )
            
            # Apply filters
            if status_filter and 'Status' in df.columns:
                df = df[df['Status'].isin(status_filter)]
            
            # Apply sorting
            if sort_by == "Login Time" and 'Login Time' in df.columns:
                df = df.sort_values(by='Login Time', ascending=False)
            elif sort_by == "Work Time" and 'Total Work Time' in df.columns:
                df['Work Minutes'] = df['Total Work Time'].apply(time_str_to_minutes)
                df = df.sort_values(by='Work Minutes', ascending=False)
            elif sort_by == "Status" and 'Status' in df.columns:
                df = df.sort_values(by='Status')
            
            st.dataframe(df, use_container_width=True, height=600)
        else:
            st.warning("No employee data available")
    except Exception as e:
        logger.error(f"Directory error: {str(e)}")
        st.error("Failed to load employee directory.")

def render_employee_management(sheet):
    """Render employee management tools"""
    try:
        st.subheader("🛠 Employee Management")
        
        # Add new employee
        with st.expander("➕ Add New Employee"):
            with st.form("add_employee_form"):
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                
                if st.form_submit_button("Add Employee"):
                    if not new_username or not new_password:
                        st.error("Username and password are required")
                    else:
                        hashed_password = hash_password(new_password)
                        sheet.append_row([new_username, hashed_password, get_current_datetime_str()])
                        st.success(f"Employee {new_username} added successfully!")
                        st.rerun()
        
        # Remove employee
        with st.expander("➖ Remove Employee"):
            try:
                employees = sheet.get_all_values()[1:]  # Skip header
                employee_names = [e[0] for e in employees if e]
                
                if employee_names:
                    to_remove = st.selectbox("Select employee to remove", employee_names)
                    
                    if st.button("Confirm Removal"):
                        for i, row in enumerate(sheet.get_all_values(), start=1):
                            if row and row[0] == to_remove:
                                sheet.delete_rows(i)
                                st.success(f"Employee {to_remove} removed successfully!")
                                st.rerun()
                                break
                else:
                    st.info("No employees to remove")
            except Exception as e:
                logger.error(f"Employee removal error: {str(e)}")
                st.error("Failed to remove employee")
    except Exception as e:
        logger.error(f"Employee management error: {str(e)}")
        st.error("Failed to load employee management tools.")

def render_admin_analytics(df: pd.DataFrame):
    """Render admin analytics charts with caching"""
    try:
        st.subheader("📊 Analytics")
        
        if df.empty or 'Status' not in df.columns:
            st.warning("No data available for analytics")
            return
            
        tab1, tab2, tab3 = st.tabs(["Work Duration", "Status Distribution", "Overtime Analysis"])
        
        with tab1:
            render_work_duration_chart(df)
        
        with tab2:
            render_status_distribution_chart(df)
                
        with tab3:
            render_overtime_analysis(df)
                
    except Exception as e:
        logger.error(f"Analytics error: {str(e)}")
        st.error("Failed to load analytics.")

@st.cache_data(ttl=300)
def render_work_duration_chart(df: pd.DataFrame):
    """Render work duration chart with caching"""
    try:
        if not df.empty and 'Total Work Time' in df.columns:
            df['Work Minutes'] = df['Total Work Time'].apply(time_str_to_minutes)
            
            # Add target line
            target_line = pd.DataFrame({
                'Employee Name': df['Employee Name'],
                'Target': [STANDARD_WORK_HOURS] * len(df)
            })
            
            fig = px.bar(
                df,
                x="Employee Name", 
                y="Work Minutes", 
                title="Work Duration vs Target", 
                color="Status",
                height=500,
                template=st.session_state.plotly_template,
                labels={"Work Minutes": "Work Duration (minutes)"}
            )
            
            # Add target line
            fig.add_scatter(
                x=target_line['Employee Name'],
                y=target_line['Target'],
                mode='lines',
                line=dict(color='red', dash='dash'),
                name='Target Hours'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Work duration data not available")
    except Exception as e:
        logger.error(f"Work duration chart error: {str(e)}")
        st.error("Failed to create work duration chart.")

@st.cache_data(ttl=300)
def render_status_distribution_chart(df: pd.DataFrame):
    """Render status distribution chart with caching"""
    try:
        if 'Status' in df.columns:
            status_counts = df["Status"].value_counts().reset_index()
            if not status_counts.empty:
                # Add color mapping based on status
                color_map = {
                    EmployeeStatus.COMPLETED.value: "#59a14f",
                    EmployeeStatus.OVER_BREAK.value: "#e15759",
                    EmployeeStatus.INCOMPLETE.value: "#edc948"
                }
                
                status_counts['Color'] = status_counts['index'].map(color_map)
                
                pie_fig = px.pie(
                    status_counts,
                    names="index", 
                    values="Status", 
                    title="Work Completion Status",
                    height=500,
                    template=st.session_state.plotly_template,
                    color="index",
                    color_discrete_map=color_map
                )
                st.plotly_chart(pie_fig, use_container_width=True)
            else:
                st.warning("No status data available for pie chart")
    except Exception as e:
        logger.error(f"Status distribution chart error: {str(e)}")
        st.error("Failed to create status distribution chart.")

@st.cache_data(ttl=300)
def render_overtime_analysis(df: pd.DataFrame):
    """Render overtime analysis with caching"""
    try:
        if not df.empty and 'Overtime' in df.columns:
            # Extract numeric values from overtime strings
            df['Overtime Hours'] = df['Overtime'].str.extract(r'(\d+\.?\d*)').astype(float)
            
            # Calculate average overtime
            avg_overtime = df['Overtime Hours'].mean()
            
            overtime_fig = px.bar(
                df,
                x="Employee Name",
                y="Overtime Hours",
                title=f"Overtime Hours (Average: {avg_overtime:.2f} hours)",
                color="Overtime Hours",
                color_continuous_scale="Viridis",
                height=500,
                template=st.session_state.plotly_template
            )
            
            # Add average line
            overtime_fig.add_hline(
                y=avg_overtime,
                line_dash="dot",
                annotation_text=f"Average: {avg_overtime:.2f} hours",
                annotation_position="bottom right"
            )
            
            st.plotly_chart(overtime_fig, use_container_width=True)
        else:
            st.warning("No overtime data available")
    except Exception as e:
        logger.error(f"Overtime analysis error: {str(e)}")
        st.error("Failed to create overtime analysis chart.")

def render_reporting_tools(sheet):
    """Render reporting tools section with validation"""
    try:
        st.subheader("📤 Reports")
        
        with st.expander("📊 Generate Report"):
            email_col, btn_col = st.columns([3, 1])
            with email_col:
                email_to = st.text_input("Send report to email:", key="report_email")
            
            with btn_col:
                st.write("")  # Spacer
                st.write("")  # Spacer
                if st.button("✉️ Email Report"):
                    if not email_to or not validate_email(email_to):
                        st.warning("Please enter a valid email address")
                    else:
                        with st.spinner("Generating and sending report..."):
                            csv_file = export_to_csv(sheet)
                            if csv_file and send_email_with_csv(email_to, csv_file):
                                st.success("Report emailed successfully!")
                            else:
                                st.error("Failed to send report")
            
            if st.button("📥 Export as CSV"):
                with st.spinner("Exporting data..."):
                    csv_file = export_to_csv(sheet)
                    if csv_file:
                        st.success(f"Exported: {csv_file}")
                        with open(csv_file, "rb") as f:
                            st.download_button(
                                label="Download CSV",
                                data=f,
                                file_name=csv_file,
                                mime="text/csv"
                            )
    except Exception as e:
        logger.error(f"Reporting tools error: {str(e)}")
        st.error("Failed to load reporting tools.")

# ====================
# EMPLOYEE DASHBOARD
# ====================
def render_employee_dashboard():
    """Render the employee dashboard with tabs"""
    try:
        st.title(f"👋 Welcome, {st.session_state.user}")
        
        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        employee = get_employee_record(sheet2, st.session_state.row_index)
        
        tab1, tab2 = st.tabs(["Dashboard", "History"])
        
        with tab1:
            render_employee_metrics(employee)
            render_time_tracking_controls(sheet2, employee)
            render_daily_summary(employee)
        
        with tab2:
            show_break_history(sheet2)
            show_productivity_tips(employee)
        
    except Exception as e:
        logger.error(f"Employee dashboard error: {str(e)}")
        st.error("Failed to load employee dashboard. Please try again.")

def render_employee_metrics(employee: EmployeeRecord):
    """Render employee metrics cards with status indicators"""
    try:
        cols = st.columns(3)
        
        # Determine status color
        status_color = {
            EmployeeStatus.COMPLETED.value: "success",
            EmployeeStatus.OVER_BREAK.value: "error",
            EmployeeStatus.INCOMPLETE.value: "warning"
        }.get(employee.status, "info")
        
        metrics = [
            ("Login Time", employee.login_time or "Not logged in", "#4e79a7"),
            ("Break Duration", employee.break_duration or "00:00", "#e15759"),
            ("Work Time", employee.work_time or "00:00", "#59a14f")
        ]
        
        for col, (title, value, color) in zip(cols, metrics):
            with col:
                st.markdown(f"""
                <div class="metric-card" style="border-left: 4px solid {color}">
                    <h3>{title}</h3>
                    <h2>{value}</h2>
                </div>
                """, unsafe_allow_html=True)
        
        # Status indicator
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid var(--{status_color}-color)">
            <h3>Status</h3>
            <h2>{employee.status or "Not available"}</h2>
        </div>
        """, unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Employee metrics error: {str(e)}")
        st.error("Failed to load employee metrics.")

def render_time_tracking_controls(sheet, employee: EmployeeRecord):
    """Render time tracking buttons with state management"""
    try:
        st.subheader("⏱ Time Tracking")
        cols = st.columns(3)

        with cols[0]:  # Start Break button
            start_disabled = bool(employee.break_start and not employee.break_end)
            if st.button("☕ Start Break", disabled=start_disabled,
                        help="Start your break time"):
                if start_disabled:
                    st.warning("Break already in progress!")
                elif employee.break_start and employee.break_end:
                    st.warning("You've already taken a break today.")
                else:
                    current_time = get_current_datetime_str()
                    sheet.update_cell(st.session_state.row_index, 4, current_time)
                    st.success(f"Break started at {current_time}")
                    st.rerun()

        with cols[1]:  # End Break button
            end_disabled = not employee.break_start or bool(employee.break_end)
            if st.button("🔙 End Break", disabled=end_disabled,
                        help="End your break time"):
                if end_disabled:
                    st.warning("No active break to end!")
                else:
                    try:
                        break_start = datetime.datetime.strptime(employee.break_start, "%Y-%m-%d %H:%M:%S")
                        break_end = datetime.datetime.now()
                        duration = (break_end - break_start).total_seconds() / 60
                        formatted_duration = format_duration(duration)

                        # Update break end and duration in the sheet
                        sheet.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                        sheet.update_cell(st.session_state.row_index, 6, formatted_duration)

                        # Alert if break exceeds allowed limit
                        if duration > MAX_BREAK_MINUTES:
                            st.warning(f"⚠️ Break exceeded 50 minutes! You took {formatted_duration}.")

                        st.success(f"Break ended. Duration: {formatted_duration}")
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Break end failed: {str(e)}")
                        st.error("Failed to end break. Please try again.")

        with cols[2]:  # Logout button
            if st.button("🔒 Logout", type="primary"):
                handle_logout(sheet, employee)

    except Exception as e:
        logger.error(f"Time tracking error: {str(e)}")
        st.error("Failed to load time tracking controls.")

def handle_logout(sheet, employee: EmployeeRecord):
    """Handle logout process with comprehensive validation"""
    try:
        if not employee.login_time:
            st.error("No login time recorded")
            return
            
        login_time = datetime.datetime.strptime(employee.login_time, "%Y-%m-%d %H:%M:%S")
        logout_time = datetime.datetime.now()
        
        # Prevent future-dated logout
        if logout_time < login_time:
            st.error("Logout time cannot be before login time")
            return
            
        # Update logout time
        sheet.update_cell(st.session_state.row_index, 3, logout_time.strftime("%Y-%m-%d %H:%M:%S"))

        # Calculate break duration if break was taken
        break_mins = 0
        if employee.break_start:
            if not employee.break_end:
                # Auto-end break if user forgot
                sheet.update_cell(st.session_state.row_index, 5, logout_time.strftime("%Y-%m-%d %H:%M:%S"))
                break_end = logout_time
            else:
                break_end = datetime.datetime.strptime(employee.break_end, "%Y-%m-%d %H:%M:%S")
            
            break_start = datetime.datetime.strptime(employee.break_start, "%Y-%m-%d %H:%M:%S")
            break_mins = (break_end - break_start).total_seconds() / 60
            formatted_break = format_duration(break_mins)
            sheet.update_cell(st.session_state.row_index, 6, formatted_break)

        # Calculate total work time (minus break time)
        total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
        total_str = format_duration(total_mins)
        
        # Update work time
        sheet.update_cell(st.session_state.row_index, 7, total_str)
        
        # Evaluate and update status
        status = evaluate_status(format_duration(break_mins), total_str)
        sheet.update_cell(st.session_state.row_index, 8, status)

        # Calculate and store overtime
        overtime = calculate_overtime(login_time, logout_time, break_mins)
        sheet.update_cell(st.session_state.row_index, 9, f"{overtime} hours")

        st.success(f"Logged out successfully. Worked: {total_str}")
        st.session_state.user = None
        st.session_state.row_index = None
        st.rerun()
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        st.error("Failed to complete logout. Please try again.")

def render_daily_summary(employee: EmployeeRecord):
    """Show summary of today's work with visual indicators"""
    try:
        if employee.work_time:
            st.subheader("📝 Today's Summary")
            
            # Create columns for metrics
            cols = st.columns(3)
            
            # Work Time
            with cols[0]:
                work_min = time_str_to_minutes(employee.work_time)
                work_percent = min(100, (work_min / STANDARD_WORK_HOURS) * 100)
                st.metric("Work Time", employee.work_time)
                st.progress(int(work_percent))
            
            # Break Time
            with cols[1]:
                break_min = time_str_to_minutes(employee.break_duration or "00:00")
                break_percent = min(100, (break_min / MAX_BREAK_MINUTES) * 100)
                st.metric("Break Time", employee.break_duration or "00:00")
                st.progress(int(break_percent))
            
            # Overtime
            with cols[2]:
                overtime = float(employee.overtime.split()[0]) if employee.overtime else 0.0
                st.metric("Overtime", employee.overtime or "0 hours")
                
                # Visual indicator for overtime
                if overtime > 0:
                    st.warning(f"⚠️ {overtime} hours overtime")
                else:
                    st.success("No overtime")
    except Exception as e:
        logger.error(f"Daily summary error: {str(e)}")
        st.error("Failed to load daily summary.")

@st.cache_data(ttl=300)
def show_break_history(sheet):
    """Display past break patterns with caching"""
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if not df.empty and 'Break Duration' in df.columns:
            st.subheader("⏳ Break History")
            
            # Convert break duration to minutes for analysis
            df['Break Minutes'] = df['Break Duration'].apply(time_str_to_minutes)
            
            # Add date column for x-axis
            df['Date'] = pd.to_datetime(df['Login Time']).dt.date
            
            # Calculate 7-day moving average
            df['7-Day Avg'] = df['Break Minutes'].rolling(window=7, min_periods=1).mean()
            
            fig = px.line(
                df, 
                x='Date',
                y=['Break Minutes', '7-Day Avg'],
                title="Your Break Patterns Over Time",
                template=st.session_state.plotly_template,
                labels={"value": "Break Duration (minutes)"}
            )
            
            # Add target line
            fig.add_hline(
                y=MAX_BREAK_MINUTES,
                line_dash="dot",
                annotation_text=f"Max Allowed: {MAX_BREAK_MINUTES} min",
                annotation_position="bottom right",
                line_color="red"
            )
            
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        logger.error(f"Break history error: {str(e)}")
        st.error("Failed to load break history.")

def show_productivity_tips(employee: EmployeeRecord):
    """Contextual productivity suggestions"""
    try:
        st.subheader("💡 Productivity Tips")
        
        if employee.break_duration:
            break_minutes = time_str_to_minutes(employee.break_duration)
            
            if break_minutes < 20:
                st.info("""
                **Tip:** Consider taking slightly longer breaks (20-30 minutes). 
                Short breaks may not be enough to recharge effectively.
                """)
            elif break_minutes > BREAK_WARNING_THRESHOLD:
                st.warning("""
                **Tip:** Long breaks can disrupt workflow. Try taking shorter, 
                more frequent breaks (5-10 minutes every hour).
                """)
            else:
                st.success("""
                **Tip:** Your break pattern looks good! Maintain this balance 
                between work and rest for optimal productivity.
                """)
        
        if employee.work_time:
            work_min = time_str_to_minutes(employee.work_time)
            if work_min > STANDARD_WORK_HOURS + 60:  # More than 1 hour overtime
                st.warning("""
                **Tip:** Regular overtime can lead to burnout. Consider discussing 
                workload with your manager if this is a frequent occurrence.
                """)
    except Exception as e:
        logger.error(f"Productivity tips error: {str(e)}")
        st.error("Failed to load productivity tips.")

# ====================
# LANDING PAGE
# ====================
def render_landing_page():
    """Render the landing page for non-logged in users"""
    try:
        st.title("🌟 PixsEdit Employee Tracker")
        st.subheader("Luxury Interface ✨ with Live Dashboard")
        
        st.markdown("""
        <div style="text-align: center; padding: 3rem 0;">
            <h2>Welcome to the Employee Tracker</h2>
            <p>Track your work hours, breaks, and productivity in one place</p>
            <p>Please login from the sidebar to access your dashboard</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Feature highlights
        st.markdown("---")
        st.subheader("✨ Key Features")
        
        features = [
            ("🕒", "Time Tracking", "Accurately track login, logout, and break times"),
            ("📊", "Productivity Analytics", "Visualize your work patterns and breaks"),
            ("📱", "Responsive Design", "Works on desktop and mobile devices"),
            ("🔒", "Secure Authentication", "Password-protected access to your data")
        ]
        
        cols = st.columns(4)
        for col, (icon, title, desc) in zip(cols, features):
            with col:
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem; border-radius: 0.5rem; 
                            background-color: var(--card-bg); border: 1px solid var(--border-color);">
                    <h1>{icon}</h1>
                    <h3>{title}</h3>
                    <p>{desc}</p>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Landing page error: {str(e)}")
        st.error("Failed to load landing page.")

# ====================
# MAIN CONTENT
# ====================
def render_main_content():
    """Render the appropriate content based on user state"""
    try:
        st.markdown("<div class='main'>", unsafe_allow_html=True)
        
        if st.session_state.user == "admin":
            render_admin_dashboard()
        elif st.session_state.user:
            render_employee_dashboard()
        else:
            render_landing_page()
            
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Content rendering error: {str(e)}")
        st.error("Failed to load application content.")

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point"""
    try:
        setup_page()
        init_session_state()
        render_sidebar()
        render_main_content()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        st.error("A critical error occurred. Please refresh the page.")

if __name__ == "__main__":
    main()
