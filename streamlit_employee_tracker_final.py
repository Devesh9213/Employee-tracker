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

# ====================
# ENUMS & CONSTANTS
# ====================
class ThemeMode(Enum):
    LIGHT = auto()
    DARK = auto()
    SYSTEM = auto()

class BreakState(Enum):
    NO_BREAK = auto()
    BREAK_IN_PROGRESS = auto()
    BREAK_COMPLETED = auto()

class UserRole(Enum):
    EMPLOYEE = auto()
    ADMIN = auto()

# Column indices (1-based)
COLUMNS = {
    'EMPLOYEE_NAME': 1,
    'LOGIN_TIME': 2,
    'LOGOUT_TIME': 3,
    'BREAK_START': 4,
    'BREAK_END': 5,
    'BREAK_DURATION': 6,
    'WORK_TIME': 7,
    'STATUS': 8,
    'OVERTIME': 9
}

STANDARD_WORK_HOURS = 8 * 60  # 8 hours in minutes
MAX_BREAK_MINUTES = 50
BREAK_WARNING_THRESHOLD = 60  # 1 hour in minutes

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
    registered_users_sheet_name: str = "Registered Employees"

# ====================
# UTILITY FUNCTIONS
# ====================
def format_duration(minutes: Union[float, int]) -> str:
    """Convert minutes to HH:MM format"""
    try:
        hrs = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hrs:02}:{mins:02}"
    except (TypeError, ValueError):
        return "00:00"

def time_str_to_minutes(time_str: str) -> int:
    """Convert time string (HH:MM) to minutes"""
    if not time_str or time_str == "00:00":
        return 0
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0

def get_current_datetime_str() -> str:
    """Get current datetime as formatted string"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_break_state(employee: EmployeeRecord) -> BreakState:
    """Determine the current break state"""
    if not employee.break_start:
        return BreakState.NO_BREAK
    if employee.break_start and not employee.break_end:
        return BreakState.BREAK_IN_PROGRESS
    return BreakState.BREAK_COMPLETED

def validate_email(email: str) -> bool:
    """Basic email validation"""
    return "@" in email and "." in email.split("@")[-1]

# ====================
# CONFIGURATION
# ====================
def load_config() -> Optional[AppConfig]:
    """Load configuration from secrets and environment"""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        
        avatar_dir = Path("avatars")
        avatar_dir.mkdir(exist_ok=True)
        
        return AppConfig(
            spreadsheet_id="1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes",
            email_address=st.secrets["EMAIL_ADDRESS"],
            email_password=st.secrets["EMAIL_PASSWORD"],
            client=client,
            avatar_dir=avatar_dir
        )
    except Exception as e:
        st.error(f"Configuration error: {str(e)}")
        return None

# ====================
# THEME MANAGEMENT
# ====================
def get_system_theme() -> ThemeMode:
    """Detect system theme preference"""
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
            "font_color": "#f5f5f5"
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
            "font_color": "#333333"
        }
    }.get(theme_mode, {})
    
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
        }}
        
        /* Rest of your CSS styles */
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
# GOOGLE SHEETS INTEGRATION
# ====================
class GoogleSheetsManager:
    def __init__(self, config: AppConfig):
        self.config = config
    
    def connect(self) -> Tuple[Any, Any]:
        """Connect to Google Sheets and get required worksheets"""
        try:
            spreadsheet = self.config.client.open_by_key(self.config.spreadsheet_id)
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            sheet_name = f"Daily Logs {today}"

            try:
                sheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                sheet = spreadsheet.add_worksheet(
                    title=sheet_name, 
                    rows="100", 
                    cols="20"
                )
                headers = [
                    "Employee Name", "Login Time", "Logout Time", 
                    "Break Start", "Break End", "Break Duration", 
                    "Total Work Time", "Status", "Overtime"
                ]
                sheet.append_row(headers)

            users_sheet = spreadsheet.worksheet(self.config.registered_users_sheet_name)
            return users_sheet, sheet
        except Exception as e:
            st.error(f"Google Sheets connection failed: {str(e)}")
            return None, None
    
    def get_employee_record(self, sheet, row_index: int) -> EmployeeRecord:
        """Get employee record from sheet row with error handling"""
        try:
            row = sheet.row_values(row_index)
            # Ensure we have enough columns by padding with empty strings
            row += [""] * (COLUMNS['OVERTIME'] - len(row))
            
            return EmployeeRecord(
                name=row[COLUMNS['EMPLOYEE_NAME']-1],
                login_time=row[COLUMNS['LOGIN_TIME']-1] or None,
                logout_time=row[COLUMNS['LOGOUT_TIME']-1] or None,
                break_start=row[COLUMNS['BREAK_START']-1] or None,
                break_end=row[COLUMNS['BREAK_END']-1] or None,
                break_duration=row[COLUMNS['BREAK_DURATION']-1] or None,
                work_time=row[COLUMNS['WORK_TIME']-1] or None,
                status=row[COLUMNS['STATUS']-1] or None,
                overtime=row[COLUMNS['OVERTIME']-1] or None
            )
        except Exception as e:
            st.error(f"Error fetching employee record: {str(e)}")
            return EmployeeRecord(name="Error")

# ====================
# TIME TRACKING FUNCTIONS
# ====================
class TimeTracker:
    def __init__(self, sheet_manager: GoogleSheetsManager):
        self.sheet_manager = sheet_manager
    
    def evaluate_status(self, break_duration: str, work_duration: str) -> str:
        """Evaluate employee status based on break and work time"""
        break_min = time_str_to_minutes(break_duration)
        work_min = time_str_to_minutes(work_duration)
        
        if work_min >= STANDARD_WORK_HOURS and break_min <= MAX_BREAK_MINUTES:
            return "✅ Complete"
        elif break_min > MAX_BREAK_MINUTES:
            return "❌ Over Break"
        return "❌ Incomplete"

    def calculate_overtime(self, login_time: datetime.datetime, 
                         logout_time: datetime.datetime, 
                         break_mins: int) -> float:
        """Calculate overtime hours"""
        total_mins = (logout_time - login_time).total_seconds() / 60
        worked_mins = total_mins - break_mins
        overtime = max(0, worked_mins - STANDARD_WORK_HOURS)
        return round(overtime / 60, 2)  # Convert to hours with 2 decimal places

    def handle_start_break(self, sheet, row_index: int) -> None:
        """Handle break start action"""
        sheet.update_cell(row_index, COLUMNS['BREAK_START'], get_current_datetime_str())
        st.success(f"Break started at {get_current_datetime_str()}")
        st.rerun()

    def handle_end_break(self, sheet, row_index: int, break_start: str) -> None:
        """Handle break end action"""
        break_end = datetime.datetime.now()
        duration = (break_end - datetime.datetime.strptime(break_start, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
        
        sheet.update_cell(row_index, COLUMNS['BREAK_END'], break_end.strftime("%Y-%m-%d %H:%M:%S"))
        sheet.update_cell(row_index, COLUMNS['BREAK_DURATION'], format_duration(duration))
        
        if duration > BREAK_WARNING_THRESHOLD:
            st.warning("Long break detected! Consider shorter breaks for productivity")
        
        st.success(f"Break ended. Duration: {format_duration(duration)}")
        st.rerun()

    def handle_logout(self, sheet, employee: EmployeeRecord, row_index: int) -> None:
        """Handle logout process"""
        login_time = datetime.datetime.strptime(employee.login_time, "%Y-%m-%d %H:%M:%S")
        logout_time = datetime.datetime.now()
        
        # Update logout time
        sheet.update_cell(row_index, COLUMNS['LOGOUT_TIME'], logout_time.strftime("%Y-%m-%d %H:%M:%S"))

        # Calculate break duration if break was taken
        break_mins = time_str_to_minutes(employee.break_duration) if employee.break_duration else 0

        # Calculate total work time
        total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
        total_str = format_duration(total_mins)
        
        # Update work time and status
        sheet.update_cell(row_index, COLUMNS['WORK_TIME'], total_str)
        status = self.evaluate_status(employee.break_duration or "", total_str)
        sheet.update_cell(row_index, COLUMNS['STATUS'], status)

        # Calculate and store overtime
        overtime = self.calculate_overtime(login_time, logout_time, break_mins)
        sheet.update_cell(row_index, COLUMNS['OVERTIME'], f"{overtime} hours")

        st.success(f"Logged out. Worked: {total_str}")
        st.session_state.user = None
        st.session_state.row_index = None
        st.rerun()

# ====================
# MAIN APPLICATION CLASS
# ====================
class EmployeeTrackerApp:
    def __init__(self):
        self.config = load_config()
        if self.config is None:
            st.stop()
        
        self.sheet_manager = GoogleSheetsManager(self.config)
        self.time_tracker = TimeTracker(self.sheet_manager)
        self.init_session_state()
        self.setup_page()
        
    def init_session_state(self):
        """Initialize session state variables"""
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'row_index' not in st.session_state:
            st.session_state.row_index = None
        if 'avatar_uploaded' not in st.session_state:
            st.session_state.avatar_uploaded = False
        if 'theme' not in st.session_state:
            st.session_state.theme = get_system_theme()
        if 'plotly_template' not in st.session_state:
            st.session_state.plotly_template = apply_theme(st.session_state.theme)

    def setup_page(self):
        """Configure page settings and theme"""
        st.set_page_config(
            page_title="🌟 PixsEdit Employee Tracker", 
            layout="wide",
            page_icon="🕒"
        )
        
        with st.sidebar:
            self.render_sidebar()
    
    def render_sidebar(self):
        """Render sidebar components"""
        st.title("PixsEdit Tracker")
        self.render_theme_selector()
        self.render_avatar_section()
        self.render_login_section()

    def render_theme_selector(self):
        """Render theme selection dropdown"""
        theme_options = [t.name.capitalize() for t in ThemeMode]
        current_theme = st.session_state.theme.name.capitalize()
        selected_theme = st.selectbox(
            "Theme",
            theme_options,
            index=theme_options.index(current_theme)
        )
        
        if selected_theme.lower() != st.session_state.theme.name.lower():
            st.session_state.theme = ThemeMode[selected_theme.upper()]
            st.session_state.plotly_template = apply_theme(st.session_state.theme)
            st.rerun()

    def render_avatar_section(self):
        """Handle avatar upload and display"""
        try:
            if st.session_state.user:
                avatar_path = self.config.avatar_dir / f"{st.session_state.user}.png"
                if avatar_path.exists():
                    st.image(str(avatar_path), width=100, caption=f"Welcome {st.session_state.user}")
                
                new_avatar = st.file_uploader("Update Avatar", type=["jpg", "jpeg", "png"])
                if new_avatar:
                    with open(avatar_path, "wb") as f:
                        f.write(new_avatar.read())
                    st.success("Avatar updated!")
                    st.session_state.avatar_uploaded = True
            else:
                uploaded_avatar = st.file_uploader("Upload Avatar (optional)", type=["jpg", "jpeg", "png"])
                if uploaded_avatar:
                    temp_path = self.config.avatar_dir / "temp_avatar.png"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_avatar.read())
                    st.image(str(temp_path), width=100, caption="Preview")
        except Exception as e:
            st.error(f"Avatar error: {str(e)}")

    def render_login_section(self):
        """Handle login/logout functionality"""
        try:
            st.markdown("---")
            if st.session_state.user:
                if st.button("🚪 Logout"):
                    st.session_state.user = None
                    st.session_state.row_index = None
                    st.rerun()
            else:
                st.markdown("### Login")
                username = st.text_input("👤 Username")
                password = st.text_input("🔒 Password", type="password")
                
                col1, col2 = st.columns(2)
                if col1.button("Login"):
                    self.handle_login(username, password)
                
                if col2.button("Register"):
                    self.handle_registration(username, password)
        except Exception as e:
            st.error(f"Login error: {str(e)}")

    def handle_login(self, username: str, password: str):
        """Process login attempt"""
        if not username or not password:
            st.error("Username and password are required")
            return
            
        users_sheet, _ = self.sheet_manager.connect()
        if users_sheet is None:
            return
            
        users = users_sheet.get_all_values()[1:]  # Skip header
        user_dict = {u[0]: u[1] for u in users if len(u) >= 2}
        
        if username not in user_dict or user_dict[username] != password:
            st.error("Invalid credentials.")
        else:
            st.session_state.user = username
            _, daily_sheet = self.sheet_manager.connect()
            if daily_sheet is None:
                return
                
            rows = daily_sheet.get_all_values()
            st.session_state.row_index = None
            for i, row in enumerate(rows[1:], start=2):  # Skip header
                if row and row[0] == username:
                    st.session_state.row_index = i
                    break

            if username != "admin" and st.session_state.row_index is None:
                daily_sheet.append_row([username, get_current_datetime_str()] + [""]*7)
                st.session_state.row_index = len(daily_sheet.get_all_values())
            
            st.rerun()

    def handle_registration(self, username: str, password: str):
        """Process new user registration"""
        if not username or not password:
            st.error("Username and password are required")
            return
            
        users_sheet, _ = self.sheet_manager.connect()
        if users_sheet is None:
            return
            
        users = users_sheet.get_all_values()[1:]  # Skip header
        user_dict = {u[0]: u[1] for u in users if len(u) >= 2}
        
        if username in user_dict:
            st.error("User already exists.")
        else:
            users_sheet.append_row([username, password])
            st.success("Registration successful! Please login.")

    def render_time_tracking_controls(self, sheet, employee: EmployeeRecord):
        """Render time tracking buttons with fixed break functionality"""
        try:
            st.subheader("⏱ Time Tracking")
            cols = st.columns(3)
            
            # Debug information - can be removed in production
            st.write(f"Debug - Current break state: {get_break_state(employee).name}")
            
            with cols[0]:  # Start Break button
                if st.button("☕ Start Break"):
                    if get_break_state(employee) == BreakState.BREAK_IN_PROGRESS:
                        st.warning("Break already in progress!")
                        return
                    if get_break_state(employee) == BreakState.BREAK_COMPLETED:
                        st.warning("Please end your current break before starting a new one")
                        return
                        
                    sheet.update_cell(st.session_state.row_index, COLUMNS['BREAK_START'], get_current_datetime_str())
                    st.success(f"Break started at {get_current_datetime_str()}")
                    st.rerun()
            
            with cols[1]:  # End Break button
                if st.button("🔙 End Break"):
                    if get_break_state(employee) == BreakState.NO_BREAK:
                        st.error("No break to end!")
                        return
                    if get_break_state(employee) == BreakState.BREAK_COMPLETED:
                        st.error("Break already ended!")
                        return
                        
                    self.time_tracker.handle_end_break(sheet, st.session_state.row_index, employee.break_start)
            
            with cols[2]:  # Logout button
                if st.button("🔒 Logout"):
                    self.time_tracker.handle_logout(sheet, employee, st.session_state.row_index)
                    
        except Exception as e:
            st.error(f"Time tracking error: {str(e)}")

    def run(self):
        """Main application entry point"""
        try:
            self.render_main_content()
        except Exception as e:
            st.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    app = EmployeeTrackerApp()
    app.run()
