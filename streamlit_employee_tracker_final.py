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
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        
        avatar_dir = Path("avatars")
        avatar_dir.mkdir(exist_ok=True)
        
        return AppConfig(
            spreadsheet_id=st.secrets.get("SPREADSHEET_ID", "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"),
            email_address=st.secrets["EMAIL_ADDRESS"],
            email_password=st.secrets["EMAIL_PASSWORD"],
            client=client,
            avatar_dir=avatar_dir,
            timezone=st.secrets.get("TIMEZONE", DEFAULT_TIMEZONE)
        )
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        st.error("Failed to initialize application configuration. Please contact support.")
        return None

config = load_config()
if config is None:
    st.stop()

# ====================
# TIME UTILITIES
# ====================
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

def get_current_datetime_str() -> str:
    """Get current datetime as formatted string"""
    return format_datetime(get_current_datetime())

# ====================
# DURATION CALCULATIONS
# ====================
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

def calculate_time_difference(start: str, end: str) -> float:
    """Calculate time difference in minutes between two datetime strings"""
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    
    if not start_dt or not end_dt:
        return 0.0
        
    return (end_dt - start_dt).total_seconds() / 60

def evaluate_status(break_duration: str, work_duration: str) -> str:
    """Evaluate employee status based on break and work time"""
    break_min = time_str_to_minutes(break_duration)
    work_min = time_str_to_minutes(work_duration)
    
    if work_min >= STANDARD_WORK_HOURS and break_min <= MAX_BREAK_MINUTES:
        return "✅ Complete"
    elif break_min > MAX_BREAK_MINUTES:
        return "❌ Over Break"
    return "❌ Incomplete"

def calculate_overtime(login_time: str, logout_time: str, break_mins: float) -> float:
    """Calculate overtime hours"""
    total_mins = calculate_time_difference(login_time, logout_time)
    worked_mins = total_mins - break_mins
    overtime = max(0, worked_mins - STANDARD_WORK_HOURS)
    return round(overtime / 60, 2)  # Convert to hours with 2 decimal places

# ====================
# FILE OPERATIONS
# ====================
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

def get_csv_download_link(file_path: str) -> str:
    """Generate a download link for the CSV file"""
    with open(file_path, 'rb') as f:
        csv_data = f.read()
    b64 = base64.b64encode(csv_data).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{os.path.basename(file_path)}">Download CSV</a>'

# ====================
# EMAIL OPERATIONS
# ====================
def send_email_with_csv(to_email: str, file_path: str) -> bool:
    """Send email with CSV attachment"""
    try:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            st.error("Report file not found for email attachment")
            return False

        msg = EmailMessage()
        msg['Subject'] = f'Daily Employee Report - {datetime.datetime.now().strftime("%Y-%m-%d")}'
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
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {str(e)}")
        st.error("Failed to send email. Please check email configuration.")
        return False

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
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
                cols="2"
            )
            users_sheet.append_row(["Username", "Password"])

        return users_sheet, sheet
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {str(e)}")
        st.error("Failed to connect to Google Sheets. Please check your connection.")
        return None, None

def get_employee_record(sheet, row_index: int) -> EmployeeRecord:
    """Get employee record from sheet row"""
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
        logger.error(f"Failed to get employee record: {str(e)}")
        return EmployeeRecord(name="")

def update_employee_record(sheet, row_index: int, action: TimeAction) -> bool:
    """Update employee record based on action type"""
    try:
        now = get_current_datetime_str()
        
        if action == TimeAction.LOGIN:
            sheet.update_cell(row_index, 2, now)  # Login Time (column B)
        elif action == TimeAction.LOGOUT:
            sheet.update_cell(row_index, 3, now)  # Logout Time (column C)
        elif action == TimeAction.BREAK_START:
            sheet.update_cell(row_index, 4, now)  # Break Start (column D)
        elif action == TimeAction.BREAK_END:
            sheet.update_cell(row_index, 5, now)  # Break End (column E)
            
            # Calculate break duration
            record = get_employee_record(sheet, row_index)
            if record.break_start:
                duration = calculate_time_difference(record.break_start, now)
                sheet.update_cell(row_index, 6, format_duration(duration))  # Break Duration (column F)
        
        return True
    except Exception as e:
        logger.error(f"Failed to update employee record: {str(e)}")
        return False

# ====================
# THEME MANAGEMENT
# ====================
class ThemeManager:
    """Manage application theme settings"""
    @staticmethod
    def get_system_theme() -> str:
        """Detect system theme preference using JavaScript evaluation"""
        try:
            theme = streamlit_js_eval(
                js_expressions='window.matchMedia("(prefers-color-scheme: dark)").matches', 
                want_output=True
            )
            return "dark" if theme else "light"
        except:
            current_hour = get_current_datetime().hour
            return "dark" if current_hour < 6 or current_hour >= 18 else "light"

    @staticmethod
    def apply_theme(theme_mode: str) -> Dict[str, Any]:
        """Apply the selected theme with responsive design"""
        theme_colors = {
            "dark": {
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
            "light": {
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
# SESSION STATE MANAGEMENT
# ====================
class SessionStateManager:
    """Manage session state variables"""
    @staticmethod
    def init_session_state():
        """Initialize session state variables"""
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'row_index' not in st.session_state:
            st.session_state.row_index = None
        if 'avatar_uploaded' not in st.session_state:
            st.session_state.avatar_uploaded = False
        if 'theme' not in st.session_state:
            st.session_state.theme = ThemeManager.get_system_theme()
        if 'plotly_template' not in st.session_state:
            st.session_state.plotly_template = ThemeManager.apply_theme(st.session_state.theme)
        if 'last_action' not in st.session_state:
            st.session_state.last_action = None

    @staticmethod
    def clear_session():
        """Clear session state"""
        st.session_state.user = None
        st.session_state.row_index = None
        st.session_state.avatar_uploaded = False
        st.session_state.last_action = None

# ====================
# AUTHENTICATION
# ====================
class AuthManager:
    """Handle user authentication and registration"""
    @staticmethod
    def handle_login(username: str, password: str):
        """Process login attempt"""
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
        """Process new user registration"""
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
# AVATAR MANAGEMENT
# ====================
class AvatarManager:
    """Handle avatar upload and display"""
    @staticmethod
    def get_avatar_path(username: str) -> Path:
        """Get path to user's avatar"""
        return config.avatar_dir / f"{username}.png"

    @staticmethod
    def display_avatar(username: str):
        """Display user's avatar if exists"""
        avatar_path = AvatarManager.get_avatar_path(username)
        if avatar_path.exists():
            st.image(str(avatar_path), width=100, caption=f"Welcome {username}")

    @staticmethod
    def handle_avatar_upload(username: str):
        """Handle avatar upload for logged in user"""
        new_avatar = st.file_uploader("Update Avatar", type=["jpg", "jpeg", "png"])
        if new_avatar:
            avatar_path = AvatarManager.get_avatar_path(username)
            with open(avatar_path, "wb") as f:
                f.write(new_avatar.read())
            st.success("Avatar updated!")
            st.session_state.avatar_uploaded = True
            st.rerun()

    @staticmethod
    def handle_temp_avatar_upload():
        """Handle avatar upload for non-logged in users"""
        uploaded_avatar = st.file_uploader("Upload Avatar (optional)", type=["jpg", "jpeg", "png"])
        if uploaded_avatar:
            temp_path = config.avatar_dir / "temp_avatar.png"
            with open(temp_path, "wb") as f:
                f.write(uploaded_avatar.read())
            st.image(str(temp_path), width=100, caption="Preview")

# ====================
# PAGE COMPONENTS
# ====================
class PageComponents:
    """Reusable UI components"""
    @staticmethod
    def metric_card(title: str, value: str, help_text: str = None):
        """Create a styled metric card"""
        help_markdown = f"<br><small>{help_text}</small>" if help_text else ""
        st.markdown(f"""
        <div class="metric-card">
            <h3>{title}</h3>
            <h2>{value}</h2>
            {help_markdown}
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def time_tracking_button(label: str, action: TimeAction, disabled: bool = False):
        """Create a time tracking button with consistent styling"""
        icons = {
            TimeAction.LOGIN: "🔑",
            TimeAction.LOGOUT: "🚪",
            TimeAction.BREAK_START: "☕",
            TimeAction.BREAK_END: "🔙"
        }
        return st.button(f"{icons.get(action, '')} {label}", disabled=disabled)

# ====================
# ADMIN DASHBOARD
# ====================
class AdminDashboard:
    """Admin dashboard components"""
    @staticmethod
    def render():
        """Render the admin dashboard"""
        try:
            st.title("📊 Admin Dashboard")
            
            sheet1, sheet2 = connect_to_google_sheets()
            if sheet2 is None:
                return
                
            try:
                data = sheet2.get_all_records()
                df = pd.DataFrame(data) if data else pd.DataFrame()
            except Exception as e:
                logger.error(f"Failed to get sheet data: {str(e)}")
                df = pd.DataFrame()
            
            AdminDashboard.render_metrics(sheet1, df)
            AdminDashboard.render_employee_directory(df)
            AdminDashboard.render_analytics(df)
            AdminDashboard.render_reporting_tools(sheet2)
        except Exception as e:
            logger.error(f"Admin dashboard error: {str(e)}")
            st.error("Failed to load admin dashboard")

    @staticmethod
    def render_metrics(sheet1, df: pd.DataFrame):
        """Render admin metrics cards"""
        try:
            st.subheader("📈 Employee Overview")
            cols = st.columns(4)
            
            try:
                total_employees = len(sheet1.get_all_values()) - 1  # Subtract header
            except:
                total_employees = 0
            
            active_today = len(df) if not df.empty else 0
            on_break = len(df[df['Break Start'].notna() & df['Break End'].isna()]) if not df.empty else 0
            completed = len(df[df['Status'] == "✅ Complete"]) if not df.empty and 'Status' in df.columns else 0
            
            metrics = [
                ("Total Employees", str(total_employees), "Registered in system"),
                ("Active Today", str(active_today), "Logged in today"),
                ("On Break", str(on_break), "Currently on break"),
                ("Completed", str(completed), "Met work requirements")
            ]
            
            for col, (title, value, help_text) in zip(cols, metrics):
                with col:
                    PageComponents.metric_card(title, value, help_text)
        except Exception as e:
            logger.error(f"Metrics error: {str(e)}")
            st.error("Failed to load metrics")

    @staticmethod
    def render_employee_directory(df: pd.DataFrame):
        """Render employee directory table"""
        try:
            st.subheader("👥 Employee Directory")
            if not df.empty:
                st.dataframe(
                    df.sort_values(by="Employee Name", ascending=True),
                    use_container_width=True,
                    height=600
                )
            else:
                st.warning("No employee data available")
        except Exception as e:
            logger.error(f"Directory error: {str(e)}")
            st.error("Failed to load employee directory")

    @staticmethod
    def render_analytics(df: pd.DataFrame):
        """Render admin analytics charts"""
        try:
            st.subheader("📊 Analytics")
            
            if df.empty or 'Status' not in df.columns:
                st.warning("No data available for analytics")
                return
                
            tab1, tab2, tab3 = st.tabs(["Work Duration", "Status Distribution", "Overtime Analysis"])
            
            with tab1:
                AdminDashboard.render_work_duration_chart(df)
            
            with tab2:
                AdminDashboard.render_status_distribution_chart(df)
                
            with tab3:
                AdminDashboard.render_overtime_analysis(df)
                
        except Exception as e:
            logger.error(f"Analytics error: {str(e)}")
            st.error("Failed to load analytics")

    @staticmethod
    def render_work_duration_chart(df: pd.DataFrame):
        """Render work duration bar chart"""
        try:
            if not df.empty and 'Total Work Time' in df.columns:
                df['Work Minutes'] = df['Total Work Time'].apply(time_str_to_minutes)
                bar_fig = px.bar(
                    df,
                    x="Employee Name", 
                    y="Work Minutes", 
                    title="Work Duration per Employee", 
                    color="Status",
                    height=400,
                    template=st.session_state.plotly_template,
                    labels={"Work Minutes": "Work Duration (minutes)"}
                )
                bar_fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(bar_fig, use_container_width=True)
            else:
                st.warning("Work duration data not available")
        except Exception as e:
            logger.error(f"Work duration chart error: {str(e)}")
            st.error("Failed to create work duration chart")

    @staticmethod
    def render_status_distribution_chart(df: pd.DataFrame):
        """Render status distribution pie chart"""
        try:
            status_counts = df["Status"].value_counts().reset_index()
            if not status_counts.empty:
                pie_fig = px.pie(
                    status_counts,
                    names="index", 
                    values="Status", 
                    title="Work Completion Status",
                    height=400,
                    template=st.session_state.plotly_template
                )
                st.plotly_chart(pie_fig, use_container_width=True)
            else:
                st.warning("No status data available for pie chart")
        except Exception as e:
            logger.error(f"Status distribution chart error: {str(e)}")
            st.error("Failed to create status distribution chart")

    @staticmethod
    def render_overtime_analysis(df: pd.DataFrame):
        """Render overtime analysis chart"""
        try:
            if not df.empty and 'Overtime' in df.columns:
                # Extract numeric values from overtime strings
                df['Overtime Hours'] = df['Overtime'].str.extract(r'(\d+\.?\d*)').astype(float)
                overtime_fig = px.bar(
                    df,
                    x="Employee Name",
                    y="Overtime Hours",
                    title="Overtime Hours per Employee",
                    color="Overtime Hours",
                    height=400,
                    template=st.session_state.plotly_template
                )
                overtime_fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(overtime_fig, use_container_width=True)
            else:
                st.warning("No overtime data available")
        except Exception as e:
            logger.error(f"Overtime analysis error: {str(e)}")
            st.error("Failed to create overtime analysis chart")

    @staticmethod
    def render_reporting_tools(sheet):
        """Render reporting tools section"""
        try:
            st.subheader("📤 Reports")
            
            email_col, btn_col = st.columns([3, 1])
            with email_col:
                email_to = st.text_input("Send report to email:", key="report_email")
            
            with btn_col:
                st.write("")  # Spacer
                st.write("")  # Spacer
                if st.button("✉️ Email Report"):
                    if not email_to or "@" not in email_to:
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
                                file_name=os.path.basename(csv_file),
                                mime="text/csv"
                            )
                        try:
                            os.unlink(csv_file)
                        except:
                            pass
        except Exception as e:
            logger.error(f"Reporting tools error: {str(e)}")
            st.error("Failed to load reporting tools")

# ====================
# ====================
# ====================
# EMPLOYEE DASHBOARD - TIME TRACKING CONTROLS
# ====================
class EmployeeDashboard:
    @staticmethod
    def render_time_tracking_controls(sheet, employee: EmployeeRecord):
        """Render time tracking buttons with fixed break functionality"""
        try:
            st.subheader("⏱ Time Tracking")
            cols = st.columns(3)
            
            # Get current time for consistency
            current_time = get_current_datetime_str()
            
            with cols[0]:  # Start Break button
                break_disabled = bool(employee.break_start and not employee.break_end)
                if st.button("☕ Start Break", disabled=break_disabled,
                            help="Start your break period"):
                    if employee.break_start and not employee.break_end:
                        st.warning("Break already in progress!")
                    else:
                        try:
                            # Update break start time
                            sheet.update_cell(st.session_state.row_index, 4, current_time)
                            st.success(f"Break started at {current_time}")
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Failed to start break: {str(e)}")
                            st.error("Failed to record break start. Please try again.")
            
            with cols[1]:  # End Break button
                end_break_disabled = not employee.break_start or bool(employee.break_end)
                if st.button("🔙 End Break", disabled=end_break_disabled,
                           help="End your current break"):
                    if not employee.break_start:
                        st.error("No break to end!")
                    elif employee.break_end:
                        st.error("Break already ended!")
                    else:
                        try:
                            # Update break end time
                            sheet.update_cell(st.session_state.row_index, 5, current_time)
                            
                            # Calculate break duration
                            if employee.break_start:
                                duration = calculate_time_difference(
                                    employee.break_start, 
                                    current_time
                                )
                                sheet.update_cell(
                                    st.session_state.row_index, 
                                    6, 
                                    format_duration(duration)
                                )
                            
                            # Show warning for long breaks
                            if duration > BREAK_WARNING_THRESHOLD:
                                st.warning("Long break detected! Consider shorter breaks for productivity")
                            
                            st.success(f"Break ended. Duration: {format_duration(duration)}")
                            st.rerun()
                        except Exception as e:
                            logger.error(f"Failed to end break: {str(e)}")
                            st.error("Failed to record break end. Please try again.")
            
            with cols[2]:  # Logout button
                if st.button("🔒 Logout", help="Log out and record your work time"):
                    try:
                        EmployeeDashboard.handle_logout(sheet, employee)
                    except Exception as e:
                        logger.error(f"Logout failed: {str(e)}")
                        st.error("Failed to complete logout. Please try again.")
                        
        except Exception as e:
            logger.error(f"Time tracking controls error: {str(e)}")
            st.error("Failed to load time tracking controls. Please refresh the page.")

    @staticmethod
    def handle_logout(sheet, employee: EmployeeRecord):
        """Handle logout process with proper break time calculation"""
        try:
            current_time = get_current_datetime_str()
            
            if not employee.login_time:
                st.error("No login time recorded")
                return
                
            # Update logout time
            sheet.update_cell(st.session_state.row_index, 3, current_time)

            # Calculate break duration if break was taken
            break_mins = 0
            if employee.break_start and employee.break_end:
                break_mins = calculate_time_difference(
                    employee.break_start,
                    employee.break_end
                )
            elif employee.break_start:  # Break started but not ended
                break_mins = calculate_time_difference(
                    employee.break_start,
                    current_time
                )
                sheet.update_cell(st.session_state.row_index, 5, current_time)
                sheet.update_cell(
                    st.session_state.row_index, 
                    6, 
                    format_duration(break_mins)
                )

            # Calculate total work time (minus break time)
            total_mins = calculate_time_difference(
                employee.login_time, 
                current_time
            ) - break_mins
            total_str = format_duration(total_mins)
            
            # Update work time
            sheet.update_cell(st.session_state.row_index, 7, total_str)
            
            # Evaluate and update status
            status = evaluate_status(
                format_duration(break_mins) if break_mins > 0 else "00:00", 
                total_str
            )
            sheet.update_cell(st.session_state.row_index, 8, status)

            # Calculate and store overtime
            overtime = calculate_overtime(
                employee.login_time, 
                current_time, 
                break_mins
            )
            sheet.update_cell(st.session_state.row_index, 9, f"{overtime} hours")

            st.success(f"Logged out. Worked: {total_str}")
            SessionStateManager.clear_session()
            st.rerun()
            
        except Exception as e:
            logger.error(f"Logout processing error: {str(e)}")
            st.error("Failed to complete logout process")

    @staticmethod
    def render_daily_summary(employee: EmployeeRecord):
        """Show summary of today's work"""
        try:
            if employee.work_time:  # Work time exists
                st.subheader("📝 Today's Summary")
                cols = st.columns(3)
                with cols[0]:
                    PageComponents.metric_card("Work Time", employee.work_time)
                with cols[1]:
                    PageComponents.metric_card("Break Time", employee.break_duration or "00:00")
                with cols[2]:
                    PageComponents.metric_card("Overtime", employee.overtime or "0 hours")
        except Exception as e:
            logger.error(f"Daily summary error: {str(e)}")
            st.error("Failed to load daily summary")

    @staticmethod
    def show_break_history(sheet):
        """Display past break patterns"""
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            
            if not df.empty and 'Break Duration' in df.columns:
                st.subheader("⏳ Break History")
                # Convert break duration to minutes for analysis
                df['Break Minutes'] = df['Break Duration'].apply(time_str_to_minutes)
                
                fig = px.line(
                    df, 
                    x='Login Time', 
                    y='Break Minutes', 
                    title="Your Break Patterns Over Time",
                    template=st.session_state.plotly_template,
                    labels={"Break Minutes": "Break Duration (minutes)"}
                )
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            logger.error(f"Break history error: {str(e)}")
            st.error("Failed to load break history")

    @staticmethod
    def show_productivity_tips(employee: EmployeeRecord):
        """Contextual productivity suggestions"""
        try:
            if employee.break_duration:  # If break data exists
                break_minutes = time_str_to_minutes(employee.break_duration)
                if break_minutes < 30:
                    st.info("💡 Tip: Consider taking longer breaks for better productivity")
                elif break_minutes > BREAK_WARNING_THRESHOLD:
                    st.info("💡 Tip: Frequent shorter breaks are better than one long break")
        except Exception as e:
            logger.error(f"Productivity tips error: {str(e)}")

# ====================
# LANDING PAGE
# ====================
class LandingPage:
    """Landing page components"""
    @staticmethod
    def render():
        """Render the landing page for non-logged in users"""
        try:
            st.title("🌟 PixsEdit Employee Tracker")
            st.subheader("Luxury Interface ✨ with Live Dashboard")
            
            st.markdown("""
            <div style="text-align: center; padding: 3rem 0;">
                <h2>Welcome to the Employee Tracker</h2>
                <p>Please login from the sidebar to access your dashboard</p>
            </div>
            """, unsafe_allow_html=True)
        except Exception as e:
            logger.error(f"Landing page error: {str(e)}")
            st.error("Failed to load landing page")

# ====================
# SIDEBAR COMPONENTS
# ====================
class SidebarComponents:
    """Sidebar UI components"""
    @staticmethod
    def render():
        """Render the sidebar components"""
        with st.sidebar:
            try:
                st.title("PixsEdit Tracker")
                st.caption(f"🌓 Current theme: {st.session_state.theme.capitalize()}")
                
                SidebarComponents.render_avatar_section()
                SidebarComponents.render_login_section()
                SidebarComponents.render_theme_selector()
            except Exception as e:
                logger.error(f"Sidebar error: {str(e)}")
                st.error("Failed to load sidebar components")

    @staticmethod
    def render_avatar_section():
        """Handle avatar upload and display"""
        try:
            if st.session_state.user:
                AvatarManager.display_avatar(st.session_state.user)
                AvatarManager.handle_avatar_upload(st.session_state.user)
            else:
                AvatarManager.handle_temp_avatar_upload()
        except Exception as e:
            logger.error(f"Avatar error: {str(e)}")
            st.error("Failed to load avatar section")

    @staticmethod
    def render_login_section():
        """Handle login/logout functionality"""
        try:
            st.markdown("---")
            if st.session_state.user:
                if st.button("🚪 Logout"):
                    SessionStateManager.clear_session()
                    st.rerun()
            else:
                st.markdown("### Login")
                username = st.text_input("👤 Username")
                password = st.text_input("🔒 Password", type="password")
                
                col1, col2 = st.columns(2)
                if col1.button("Login"):
                    AuthManager.handle_login(username, password)
                
                if col2.button("Register"):
                    AuthManager.handle_registration(username, password)
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            st.error("Failed to load login section")

    @staticmethod
    def render_theme_selector():
        """Render theme selector dropdown"""
        try:
            st.markdown("---")
            theme_options = ["System", "Light", "Dark"]
            current_theme = st.session_state.theme.capitalize()
            selected_theme = st.selectbox(
                "Theme",
                theme_options,
                index=theme_options.index(current_theme) if current_theme in theme_options else 0,
                key="theme_selector"
            )
            
            if selected_theme.lower() != st.session_state.theme:
                st.session_state.theme = selected_theme.lower()
                st.session_state.plotly_template = ThemeManager.apply_theme(st.session_state.theme)
                st.rerun()
        except Exception as e:
            logger.error(f"Theme selector error: {str(e)}")

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
        
        SessionStateManager.init_session_state()
        
    except Exception as e:
        logger.error(f"Page setup error: {str(e)}")
        st.error("Failed to initialize page configuration")

# ====================
# MAIN CONTENT
# ====================
def render_main_content():
    """Render the appropriate content based on user state"""
    try:
        st.markdown("<div class='main'>", unsafe_allow_html=True)
        
        if st.session_state.user == "admin":
            AdminDashboard.render()
        elif st.session_state.user:
            EmployeeDashboard.render()
        else:
            LandingPage.render()
            
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Content rendering error: {str(e)}")
        st.error("Failed to load page content")

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point"""
    try:
        setup_page()
        SidebarComponents.render()
        render_main_content()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        st.error("A critical error occurred. Please refresh the page.")

if __name__ == "__main__":
    main()
