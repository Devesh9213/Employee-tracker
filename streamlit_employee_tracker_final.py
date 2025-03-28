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
import pytz
from enum import Enum, auto
import logging
from collections import defaultdict
import tempfile
import base64
import hashlib
import time
from functools import wraps
import re

# ====================
# SETUP LOGGING
# ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====================
# CONSTANTS & ENUMS
# ====================
class TimeAction(Enum):
    LOGIN = auto()
    LOGOUT = auto()
    BREAK_START = auto()
    BREAK_END = auto()

STANDARD_WORK_HOURS = 8 * 60  # 8 hours in minutes
MAX_BREAK_MINUTES = 50
BREAK_WARNING_THRESHOLD = 60  # 1 hour in minutes
DEFAULT_TIMEZONE = "Asia/Kolkata"
CSV_HEADERS = [
    "Employee Name", "Login Time", "Logout Time", 
    "Break Start", "Break End", "Break Duration", 
    "Total Work Time", "Status", "Overtime"
]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW = 300  # 5 minutes in seconds
PASSWORD_MIN_LENGTH = 8

# ====================
# DECORATORS
# ====================
def retry(max_retries=3, delay=1, exceptions=(Exception,)):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries == max_retries:
                        logger.error(f"Max retries reached for {f.__name__}: {str(e)}")
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator

def rate_limit(key, limit, window):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time.time()
            if key not in st.session_state:
                st.session_state[key] = {'timestamps': []}
            
            timestamps = st.session_state[key]['timestamps']
            timestamps = [t for t in timestamps if now - t < window]
            
            if len(timestamps) >= limit:
                raise Exception("Rate limit exceeded")
            
            timestamps.append(now)
            st.session_state[key]['timestamps'] = timestamps
            return f(*args, **kwargs)
        return wrapper
    return decorator

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
    timezone: str = DEFAULT_TIMEZONE

# ====================
# CONFIGURATION
# ====================
def load_config() -> Optional[AppConfig]:
    """Load configuration from secrets and environment"""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        
        # Validate required secrets
        required_secrets = ["GOOGLE_CREDENTIALS", "EMAIL_ADDRESS", "EMAIL_PASSWORD"]
        for secret in required_secrets:
            if secret not in st.secrets:
                raise ValueError(f"Missing required secret: {secret}")
        
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        
        avatar_dir = Path("avatars")
        avatar_dir.mkdir(exist_ok=True, parents=True)
        
        return AppConfig(
            spreadsheet_id=st.secrets.get("SPREADSHEET_ID", "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"),
            email_address=st.secrets["EMAIL_ADDRESS"],
            email_password=st.secrets["EMAIL_PASSWORD"],
            client=client,
            avatar_dir=avatar_dir,
            timezone=st.secrets.get("TIMEZONE", DEFAULT_TIMEZONE)
        )
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in credentials: {str(e)}")
        st.error("Invalid Google credentials configuration.")
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}", exc_info=True)
        st.error("Failed to initialize application configuration. Please contact support.")
    return None

config = load_config()
if config is None:
    st.stop()

# ====================
# UTILITY FUNCTIONS
# ====================
def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = os.urandom(16)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()

def validate_password(password: str) -> bool:
    """Check password meets complexity requirements"""
    if len(password) < PASSWORD_MIN_LENGTH:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    return True

def get_current_datetime() -> datetime.datetime:
    """Get current datetime with timezone awareness"""
    tz = pytz.timezone(config.timezone)
    return datetime.datetime.now(tz)

def format_datetime(dt: Union[datetime.datetime, str]) -> str:
    """Format datetime object or string to consistent format"""
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            dt = pytz.timezone(config.timezone).localize(dt)
        except ValueError:
            return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(dt_str: str) -> Optional[datetime.datetime]:
    """Parse datetime string to timezone-aware datetime object"""
    try:
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return pytz.timezone(config.timezone).localize(dt)
    except (ValueError, TypeError):
        return None

def format_duration(minutes: float) -> str:
    """Convert minutes to HH:MM format"""
    try:
        hrs = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hrs:02}:{mins:02}"
    except (TypeError, ValueError):
        return "00:00"

def time_str_to_minutes(time_str: str) -> float:
    """Convert time string (HH:MM) to minutes"""
    if not time_str:
        return 0.0
    try:
        h, m = map(float, time_str.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0.0

@retry(max_retries=3, delay=1)
def calculate_time_difference(start: str, end: str) -> float:
    """Calculate time difference in minutes between two datetime strings"""
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    
    if not start_dt or not end_dt:
        return 0.0
        
    return (end_dt - start_dt).total_seconds() / 60

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
@retry(max_retries=3, delay=1)
def connect_to_google_sheets() -> Tuple[Any, Any]:
    """Connect to Google Sheets and get required worksheets"""
    try:
        spreadsheet = config.client.open_by_key(config.spreadsheet_id)
        today = get_current_datetime().strftime('%Y-%m-%d')
        sheet_name = f"Daily Logs {today}"

        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(
                title=sheet_name, 
                rows="100", 
                cols="10"
            )
            sheet.append_row(CSV_HEADERS)

        try:
            users_sheet = spreadsheet.worksheet("Registered Employees")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(
                title="Registered Employees", 
                rows="100", 
                cols="3"  # Added column for password hash
            )
            users_sheet.append_row(["Username", "PasswordHash", "Salt"])

        return users_sheet, sheet
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {str(e)}")
        st.error("Failed to connect to Google Sheets API. Please try again later.")
        raise
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {str(e)}")
        st.error("Failed to connect to Google Sheets. Please check your connection.")
        raise

# ====================
# AUTHENTICATION
# ====================
class AuthManager:
    """Handle user authentication and registration"""
    
    @staticmethod
    @rate_limit(key='login_attempts', limit=MAX_LOGIN_ATTEMPTS, window=LOGIN_ATTEMPT_WINDOW)
    def handle_login(username: str, password: str):
        """Process login attempt with rate limiting"""
        if not username or not password:
            st.error("Username and password are required")
            return
            
        sheet1, _ = connect_to_google_sheets()
        if sheet1 is None:
            return
            
        users = sheet1.get_all_values()[1:]  # Skip header
        user_dict = {u[0]: (u[1], u[2]) for u in users if len(u) >= 3}  # (hash, salt)
        
        if username not in user_dict:
            st.error("Invalid credentials.")
            return
            
        stored_hash, salt = user_dict[username]
        input_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        
        if input_hash != stored_hash:
            st.error("Invalid credentials.")
            return
            
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

    @staticmethod
    def handle_registration(username: str, password: str):
        """Process new user registration with password validation"""
        if not username or not password:
            st.error("Username and password are required")
            return
            
        if not validate_password(password):
            st.error(f"Password must be at least {PASSWORD_MIN_LENGTH} characters with uppercase, lowercase, and numbers")
            return
            
        sheet1, _ = connect_to_google_sheets()
        if sheet1 is None:
            return
            
        users = sheet1.get_all_values()[1:]  # Skip header
        existing_users = {u[0] for u in users if u}
        
        if username in existing_users:
            st.error("User already exists.")
            return
            
        # Generate salt and hash password
        salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        
        sheet1.append_row([username, password_hash, salt])
        st.success("Registration successful! Please login.")

# ====================
# MAIN APPLICATION
# ====================
def main():
    """Main application entry point"""
    try:
        # Initialize session state
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'row_index' not in st.session_state:
            st.session_state.row_index = None
        if 'theme' not in st.session_state:
            st.session_state.theme = "system"
        
        # Page configuration
        st.set_page_config(
            page_title="PixsEdit Employee Tracker", 
            layout="wide",
            page_icon="🕒",
            initial_sidebar_state="expanded"
        )
        
        # Sidebar components
        with st.sidebar:
            st.title("PixsEdit Tracker")
            
            if st.session_state.user:
                st.write(f"Welcome, {st.session_state.user}!")
                if st.button("Logout"):
                    st.session_state.user = None
                    st.session_state.row_index = None
                    st.rerun()
            else:
                st.subheader("Login")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.button("Login"):
                    AuthManager.handle_login(username, password)
                
                st.markdown("---")
                st.subheader("New User?")
                new_username = st.text_input("Choose Username", key="new_user")
                new_password = st.text_input("Choose Password", type="password", key="new_pass")
                
                if st.button("Register"):
                    AuthManager.handle_registration(new_username, new_password)
        
        # Main content
        if st.session_state.user == "admin":
            render_admin_dashboard()
        elif st.session_state.user:
            render_employee_dashboard()
        else:
            render_landing_page()
            
    except Exception as e:
        logger.error(f"Application error: {str(e)}", exc_info=True)
        st.error("A critical error occurred. Please refresh the page.")

def render_admin_dashboard():
    """Render the admin dashboard"""
    st.title("Admin Dashboard")
    
    try:
        users_sheet, daily_sheet = connect_to_google_sheets()
        if not users_sheet or not daily_sheet:
            st.error("Failed to connect to Google Sheets")
            return
            
        # Get all data
        users_data = users_sheet.get_all_records()
        daily_data = daily_sheet.get_all_records()
        
        # Create DataFrames
        users_df = pd.DataFrame(users_data)
        daily_df = pd.DataFrame(daily_data)
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Employees", len(users_df))
        with col2:
            st.metric("Active Today", len(daily_df))
        with col3:
            completed = len(daily_df[daily_df['Status'] == "✅ Complete"]) if 'Status' in daily_df.columns else 0
            st.metric("Completed Work", completed)
        
        # Display data
        st.subheader("Employee Data")
        st.dataframe(daily_df)
        
        # Analytics
        st.subheader("Analytics")
        if not daily_df.empty:
            tab1, tab2 = st.tabs(["Work Duration", "Status Distribution"])
            
            with tab1:
                if 'Total Work Time' in daily_df.columns:
                    daily_df['Work Minutes'] = daily_df['Total Work Time'].apply(time_str_to_minutes)
                    fig = px.bar(daily_df, x='Employee Name', y='Work Minutes', title="Work Duration")
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                if 'Status' in daily_df.columns:
                    fig = px.pie(daily_df, names='Status', title="Work Status Distribution")
                    st.plotly_chart(fig, use_container_width=True)
        
        # Export options
        st.subheader("Data Export")
        if st.button("Export to CSV"):
            csv_file = export_to_csv(daily_sheet)
            if csv_file:
                st.success("Data exported successfully!")
                with open(csv_file, "rb") as f:
                    st.download_button(
                        label="Download CSV",
                        data=f,
                        file_name="employee_data.csv",
                        mime="text/csv"
                    )
                os.unlink(csv_file)
                
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        st.error("Failed to load admin dashboard")

def render_employee_dashboard():
    """Render the employee dashboard"""
    try:
        _, sheet = connect_to_google_sheets()
        if not sheet:
            st.error("Failed to connect to Google Sheets")
            return
            
        # Get employee record
        if st.session_state.row_index is None:
            st.error("Employee record not found")
            return
            
        record = get_employee_record(sheet, st.session_state.row_index)
        if not record.name:
            st.error("Failed to load employee data")
            return
            
        st.title(f"{record.name}'s Dashboard")
        
        # Time tracking controls
        st.subheader("Time Tracking")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Start Break", disabled=bool(record.break_start and not record.break_end)):
                update_employee_record(sheet, st.session_state.row_index, TimeAction.BREAK_START)
                st.rerun()
        
        with col2:
            if st.button("End Break", disabled=not record.break_start or bool(record.break_end)):
                update_employee_record(sheet, st.session_state.row_index, TimeAction.BREAK_END)
                st.rerun()
        
        with col3:
            if st.button("Logout"):
                update_employee_record(sheet, st.session_state.row_index, TimeAction.LOGOUT)
                st.session_state.user = None
                st.session_state.row_index = None
                st.rerun()
        
        # Display current status
        st.subheader("Today's Summary")
        if record.login_time:
            cols = st.columns(3)
            with cols[0]:
                st.metric("Login Time", record.login_time.split()[1])
            with cols[1]:
                st.metric("Break Duration", record.break_duration or "00:00")
            with cols[2]:
                st.metric("Work Time", record.work_time or "00:00")
        
        # Show status
        if record.status:
            st.info(f"Status: {record.status}")
        
    except Exception as e:
        logger.error(f"Employee dashboard error: {str(e)}")
        st.error("Failed to load employee dashboard")

def render_landing_page():
    """Render the landing page"""
    st.title("Welcome to PixsEdit Employee Tracker")
    st.write("Please login from the sidebar to access your dashboard")

@retry(max_retries=3, delay=1)
def update_employee_record(sheet, row_index: int, action: TimeAction) -> bool:
    """Update employee record based on action type"""
    try:
        now = get_current_datetime_str()
        
        if action == TimeAction.LOGIN:
            sheet.update_cell(row_index, 2, now)  # Login Time (column B)
        elif action == TimeAction.LOGOUT:
            # Calculate all times before logging out
            record = get_employee_record(sheet, row_index)
            
            # Update logout time
            sheet.update_cell(row_index, 3, now)
            
            # Calculate break duration if needed
            break_mins = 0
            if record.break_start and not record.break_end:
                sheet.update_cell(row_index, 5, now)  # Break End
                break_mins = calculate_time_difference(record.break_start, now)
                sheet.update_cell(row_index, 6, format_duration(break_mins))  # Break Duration
            
            # Calculate total work time
            total_mins = calculate_time_difference(record.login_time, now) - break_mins
            sheet.update_cell(row_index, 7, format_duration(total_mins))  # Work Time
            
            # Set status
            status = evaluate_status(
                format_duration(break_mins) if break_mins > 0 else "00:00",
                format_duration(total_mins)
            )
            sheet.update_cell(row_index, 8, status)
            
            # Calculate overtime
            overtime = calculate_overtime(record.login_time, now, break_mins)
            sheet.update_cell(row_index, 9, f"{overtime} hours")
            
        elif action == TimeAction.BREAK_START:
            sheet.update_cell(row_index, 4, now)  # Break Start
        elif action == TimeAction.BREAK_END:
            sheet.update_cell(row_index, 5, now)  # Break End
            
            # Calculate break duration
            record = get_employee_record(sheet, row_index)
            if record.break_start:
                duration = calculate_time_difference(record.break_start, now)
                sheet.update_cell(row_index, 6, format_duration(duration))  # Break Duration
        
        return True
    except Exception as e:
        logger.error(f"Failed to update employee record: {str(e)}")
        st.error("Failed to update record. Please try again.")
        return False

@retry(max_retries=3, delay=1)
def export_to_csv(sheet) -> Optional[str]:
    """Export sheet data to CSV file"""
    try:
        data = sheet.get_all_values()
        if not data:
            logger.warning("No data available to export")
            return None
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(data)
            return f.name
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        st.error("Failed to export data. Please try again.")
        return None

if __name__ == "__main__":
    main()
