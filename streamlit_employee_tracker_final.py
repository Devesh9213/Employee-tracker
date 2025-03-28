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
from typing import Optional, Dict, Tuple, List, Any
import logging
from functools import wraps

# ====================
# CONSTANTS & CONFIG
# ====================
DEFAULT_SHEET_NAME = "Daily Logs"
REGISTERED_EMPLOYEES_SHEET = "Registered Employees"
MAX_BREAK_MINUTES = 50
MIN_WORK_MINUTES = 540  # 9 hours
AVATAR_TYPES = ["jpg", "jpeg", "png"]
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# ====================
# LOGGING SETUP
# ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====================
# DECORATORS
# ====================
def handle_errors(func):
    """Decorator to handle errors gracefully and log them"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            st.error(f"An error occurred in {func.__name__}. Please try again.")
            return None
    return wrapper

# ====================
# CONFIGURATION
# ====================
@handle_errors
def load_config() -> Optional[Dict[str, Any]]:
    """Load configuration from secrets and environment"""
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        if "GOOGLE_CREDENTIALS" not in st.secrets:
            raise ValueError("Google credentials not found in secrets")
            
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        
        return {
            "SPREADSHEET_ID": st.secrets.get("SPREADSHEET_ID", "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"),
            "EMAIL_ADDRESS": st.secrets.get("EMAIL_ADDRESS"),
            "EMAIL_PASSWORD": st.secrets.get("EMAIL_PASSWORD"),
            "SMTP_SERVER": st.secrets.get("SMTP_SERVER", "smtp.gmail.com"),
            "SMTP_PORT": st.secrets.get("SMTP_PORT", 465),
            "client": client,
            "AVATAR_DIR": Path("avatars")
        }
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}", exc_info=True)
        st.error("Failed to load configuration. Please check your settings.")
        return None

config = load_config()
if config is None:
    st.stop()

AVATAR_DIR = config["AVATAR_DIR"]
AVATAR_DIR.mkdir(exist_ok=True, parents=True)

# ====================
# UTILITY FUNCTIONS
# ====================
@handle_errors
def format_duration(minutes: float) -> str:
    """Convert minutes to HH:MM format"""
    if pd.isna(minutes) or minutes < 0:
        return "00:00"
    
    hrs = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hrs:02d}:{mins:02d}"

@handle_errors
def parse_duration(duration_str: str) -> float:
    """Convert HH:MM format to minutes"""
    if not duration_str or duration_str == "00:00":
        return 0.0
    
    try:
        h, m = map(int, duration_str.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0.0

@handle_errors
def evaluate_status(break_minutes: float, work_minutes: float) -> str:
    """Evaluate employee status based on break and work time"""
    if work_minutes >= MIN_WORK_MINUTES and break_minutes <= MAX_BREAK_MINUTES:
        return "✅ Complete"
    elif break_minutes > MAX_BREAK_MINUTES:
        return "❌ Over Break"
    elif work_minutes > 0:
        return "🟡 In Progress"
    else:
        return "❌ Not Started"

@handle_errors
def calculate_time_difference(start_time: str, end_time: str) -> float:
    """Calculate time difference in minutes between two timestamps"""
    if not start_time or not end_time:
        return 0.0
        
    try:
        start = datetime.datetime.strptime(start_time, TIME_FORMAT)
        end = datetime.datetime.strptime(end_time, TIME_FORMAT)
        return (end - start).total_seconds() / 60
    except ValueError:
        return 0.0

@handle_errors
def get_current_time() -> str:
    """Get current time in standard format"""
    return datetime.datetime.now().strftime(TIME_FORMAT)

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
@handle_errors
def connect_to_google_sheets() -> Tuple[Any, Any]:
    """Connect to Google Sheets and get required worksheets"""
    if not config:
        return None, None
        
    try:
        spreadsheet = config["client"].open_by_key(config["SPREADSHEET_ID"])
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        sheet_name = f"{DEFAULT_SHEET_NAME} {today}"

        # Get or create daily logs sheet
        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(
                title=sheet_name, 
                rows=100, 
                cols=10
            )
            headers = [
                "Employee Name", "Login Time", "Logout Time", 
                "Break Start", "Break End", "Break Duration", 
                "Total Work Time", "Status", "Last Update"
            ]
            sheet.append_row(headers)

        # Get registered employees sheet
        try:
            users_sheet = spreadsheet.worksheet(REGISTERED_EMPLOYEES_SHEET)
        except gspread.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(
                title=REGISTERED_EMPLOYEES_SHEET, 
                rows=100, 
                cols=3
            )
            users_sheet.append_row(["Username", "Password", "Registration Date"])

        return users_sheet, sheet
    except Exception as e:
        logger.error(f"Google Sheets connection failed: {str(e)}", exc_info=True)
        return None, None

@handle_errors
def get_employee_row(sheet: Any, username: str) -> Tuple[int, List[str]]:
    """Find employee row in the sheet and return index and row data"""
    if not sheet:
        return -1, []
        
    try:
        records = sheet.get_all_records()
        for i, record in enumerate(records, start=2):  # Rows start at 2 (1 is header)
            if record.get("Employee Name") == username:
                return i, list(record.values())
        return -1, []
    except Exception as e:
        logger.error(f"Error getting employee row: {str(e)}", exc_info=True)
        return -1, []

# ====================
# EMAIL FUNCTIONS
# ====================
@handle_errors
def export_to_csv(sheet: Any) -> Optional[str]:
    """Export sheet data to CSV file"""
    if not sheet:
        return None
        
    try:
        data = sheet.get_all_values()
        if not data:
            return None
            
        filename = f"Daily_Logs_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)
        return filename
    except Exception as e:
        logger.error(f"Export failed: {str(e)}", exc_info=True)
        return None

@handle_errors
def send_email_with_csv(to_email: str, file_path: str) -> bool:
    """Send email with CSV attachment"""
    if not config or not os.path.exists(file_path):
        return False

    try:
        msg = EmailMessage()
        msg['Subject'] = f'Daily Employee Report - {datetime.datetime.now().strftime("%Y-%m-%d")}'
        msg['From'] = config["EMAIL_ADDRESS"]
        msg['To'] = to_email
        msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

        with open(file_path, 'rb') as f:
            file_data = f.read()
            msg.add_attachment(
                file_data, 
                maintype="text", 
                subtype="csv", 
                filename=os.path.basename(file_path)
        )

        with smtplib.SMTP_SSL(
            config["SMTP_SERVER"], 
            config["SMTP_PORT"]
        ) as smtp:
            smtp.login(config["EMAIL_ADDRESS"], config["EMAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email failed: {str(e)}", exc_info=True)
        return False

# ====================
# USER MANAGEMENT
# ====================
@handle_errors
def authenticate_user(username: str, password: str) -> bool:
    """Authenticate user credentials"""
    if not username or not password:
        return False
        
    sheet, _ = connect_to_google_sheets()
    if not sheet:
        return False
        
    try:
        users = sheet.get_all_records()
        for user in users:
            if user.get("Username") == username and user.get("Password") == password:
                return True
        return False
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        return False

@handle_errors
def register_user(username: str, password: str) -> bool:
    """Register a new user"""
    if not username or not password:
        st.error("Username and password are required")
        return False
        
    sheet, _ = connect_to_google_sheets()
    if not sheet:
        return False
        
    try:
        users = sheet.get_all_records()
        if any(user.get("Username") == username for user in users):
            st.error("Username already exists")
            return False
            
        sheet.append_row([
            username, 
            password, 
            datetime.datetime.now().strftime("%Y-%m-%d")
        ])
        return True
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        return False

# ====================
# AVATAR MANAGEMENT
# ====================
@handle_errors
def save_avatar(username: str, uploaded_file) -> bool:
    """Save uploaded avatar for user"""
    if not username or not uploaded_file:
        return False
        
    try:
        avatar_path = AVATAR_DIR / f"{username}.png"
        with open(avatar_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        logger.error(f"Avatar save error: {str(e)}", exc_info=True)
        return False

@handle_errors
def get_avatar(username: str) -> Optional[str]:
    """Get avatar path for user if exists"""
    if not username:
        return None
        
    avatar_path = AVATAR_DIR / f"{username}.png"
    return str(avatar_path) if avatar_path.exists() else None

# ====================
# SESSION MANAGEMENT
# ====================
def init_session_state():
    """Initialize session state variables"""
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'row_index' not in st.session_state:
        st.session_state.row_index = -1
    if 'avatar_uploaded' not in st.session_state:
        st.session_state.avatar_uploaded = False
    if 'last_action' not in st.session_state:
        st.session_state.last_action = None

# ====================
# PAGE SETUP & THEMING
# ====================
def setup_page():
    """Configure page settings and theme"""
    st.set_page_config(
        page_title="🌟 PixsEdit Employee Tracker", 
        layout="wide",
        page_icon="🕒",
        initial_sidebar_state="expanded"
    )
    
    # Auto theme based on time of day
    current_hour = datetime.datetime.now().hour
    auto_dark = current_hour < 6 or current_hour >= 18
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=auto_dark)
    
    apply_theme(dark_mode)

def apply_theme(dark_mode: bool):
    """Apply theme styling based on mode"""
    theme = {
        "bg_color": "#1e1e1e" if dark_mode else "#f6f9fc",
        "text_color": "#f5f5f5" if dark_mode else "#333333",
        "card_bg": "#2d2d2d" if dark_mode else "#ffffff",
        "primary_color": "#00dfd8" if dark_mode else "#007cf0",
        "secondary_color": "#007cf0" if dark_mode else "#00dfd8"
    }
    
    st.markdown(f"""
    <style>
        .main {{
            background-color: {theme['bg_color']};
            color: {theme['text_color']};
            padding: 2rem;
            border-radius: 1rem;
        }}
        .stButton>button {{
            background: linear-gradient(90deg, {theme['primary_color']}, {theme['secondary_color']});
            color: white !important;
            border: none !important;
            border-radius: 0.5rem;
            padding: 0.5rem 1rem;
        }}
        .metric-card {{
            background-color: {theme['card_bg']};
            padding: 1.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .stAlert {{
            border-radius: 0.5rem;
        }}
        .stTextInput>div>div>input {{
            color: {theme['text_color']} !important;
        }}
    </style>
    """, unsafe_allow_html=True)

# ====================
# UI COMPONENTS
# ====================
def metric_card(title: str, value: str, icon: str = ""):
    """Create a styled metric card"""
    st.markdown(f"""
    <div class="metric-card">
        <h3>{icon} {title}</h3>
        <h2>{value}</h2>
    </div>
    """, unsafe_allow_html=True)

def employee_status_badge(status: str) -> str:
    """Return appropriate emoji for status"""
    status_emojis = {
        "✅ Complete": "✅",
        "❌ Over Break": "❌",
        "🟡 In Progress": "🟡",
        "❌ Not Started": "❌"
    }
    return status_emojis.get(status, "")

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components"""
    with st.sidebar:
        st.title("PixsEdit Tracker")
        st.caption("🌓 Auto theme applied based on time of day")
        
        render_avatar_section()
        render_login_section()

def render_avatar_section():
    """Handle avatar upload and display"""
    if st.session_state.user:
        avatar_path = get_avatar(st.session_state.user)
        if avatar_path:
            st.image(avatar_path, width=100, caption=f"Welcome {st.session_state.user}")
        
        new_avatar = st.file_uploader(
            "Update Avatar", 
            type=AVATAR_TYPES,
            accept_multiple_files=False,
            key="avatar_uploader"
        )
        if new_avatar and save_avatar(st.session_state.user, new_avatar):
            st.success("Avatar updated!")
            st.session_state.avatar_uploaded = True
            st.rerun()
    else:
        uploaded_avatar = st.file_uploader(
            "Upload Avatar (optional)", 
            type=AVATAR_TYPES,
            accept_multiple_files=False
        )
        if uploaded_avatar:
            st.image(uploaded_avatar, width=100, caption="Preview")

def render_login_section():
    """Handle login/logout functionality"""
    st.markdown("---")
    if st.session_state.user:
        if st.button("🚪 Logout", key="logout_button"):
            st.session_state.user = None
            st.session_state.row_index = -1
            st.rerun()
    else:
        st.markdown("### Login")
        username = st.text_input("👤 Username", key="login_username")
        password = st.text_input("🔒 Password", type="password", key="login_password")
        
        col1, col2 = st.columns(2)
        if col1.button("Login", key="login_button"):
            if authenticate_user(username, password):
                st.session_state.user = username
                _, sheet = connect_to_google_sheets()
                if sheet:
                    row_index, _ = get_employee_row(sheet, username)
                    st.session_state.row_index = row_index
                st.rerun()
            else:
                st.error("Invalid credentials")
        
        if col2.button("Register", key="register_button"):
            if register_user(username, password):
                st.success("Registration successful! Please login.")
            else:
                st.error("Registration failed")

# ====================
# ADMIN DASHBOARD
# ====================
def render_admin_dashboard():
    """Render the admin dashboard"""
    st.title("📊 Admin Dashboard")
    
    _, sheet = connect_to_google_sheets()
    if not sheet:
        return
        
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        logger.error(f"Error getting sheet data: {str(e)}", exc_info=True)
        df = pd.DataFrame()
    
    render_admin_metrics(df)
    render_employee_directory(df)
    render_admin_analytics(df)
    render_reporting_tools(sheet)

def render_admin_metrics(df: pd.DataFrame):
    """Render admin metrics cards"""
    st.subheader("📈 Employee Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        users_sheet, _ = connect_to_google_sheets()
        total_employees = len(users_sheet.get_all_records()) if users_sheet else 0
        metric_card("Total Employees", str(total_employees), "👥")
    
    with col2:
        active_today = len(df) if not df.empty else 0
        metric_card("Active Today", str(active_today), "🟢")
    
    with col3:
        on_break = len(df[df['Break Start'].notna() & df['Break End'].isna()]) if not df.empty else 0
        metric_card("On Break", str(on_break), "☕")
    
    with col4:
        completed = len(df[df['Status'] == "✅ Complete"]) if not df.empty and 'Status' in df.columns else 0
        metric_card("Completed", str(completed), "✅")

def render_employee_directory(df: pd.DataFrame):
    """Render employee directory table"""
    st.subheader("👥 Employee Directory")
    if not df.empty:
        # Format the dataframe for better display
        display_df = df.copy()
        if 'Status' in display_df.columns:
            display_df['Status'] = display_df['Status'].apply(
                lambda x: f"{employee_status_badge(x)} {x}"
            )
        st.dataframe(display_df, use_container_width=True, height=400)
    else:
        st.warning("No employee data available")

def render_admin_analytics(df: pd.DataFrame):
    """Render admin analytics charts"""
    st.subheader("📊 Analytics")
    
    if df.empty or 'Status' not in df.columns:
        st.warning("No data available for analytics")
        return
        
    tab1, tab2, tab3 = st.tabs(["Work Duration", "Status Distribution", "Break Analysis"])
    
    with tab1:
        if not df.empty and 'Total Work Time' in df.columns:
            try:
                # Convert work time to minutes for plotting
                df['Work Minutes'] = df['Total Work Time'].apply(parse_duration)
                fig = px.bar(
                    df.sort_values('Work Minutes', ascending=False),
                    x="Employee Name", 
                    y="Work Minutes", 
                    title="Work Duration per Employee", 
                    color="Status",
                    height=400,
                    labels={"Work Minutes": "Work Time (minutes)"}
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Failed to create work duration chart: {str(e)}")
    
    with tab2:
        try:
            status_counts = df["Status"].value_counts().reset_index()
            if not status_counts.empty:
                fig = px.pie(
                    status_counts,
                    names="index", 
                    values="Status", 
                    title="Work Completion Status",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to create status distribution chart: {str(e)}")
    
    with tab3:
        if not df.empty and 'Break Duration' in df.columns:
            try:
                # Convert break time to minutes for plotting
                df['Break Minutes'] = df['Break Duration'].apply(parse_duration)
                fig = px.bar(
                    df.sort_values('Break Minutes', ascending=False),
                    x="Employee Name", 
                    y="Break Minutes", 
                    title="Break Duration per Employee", 
                    color="Status",
                    height=400,
                    labels={"Break Minutes": "Break Time (minutes)"}
                )
                fig.add_hline(
                    y=MAX_BREAK_MINUTES, 
                    line_dash="dash", 
                    line_color="red",
                    annotation_text="Max Allowed Break"
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Failed to create break analysis chart: {str(e)}")

def render_reporting_tools(sheet: Any):
    """Render reporting tools section"""
    st.subheader("📤 Reports")
    
    # Email report section
    with st.expander("Email Report"):
        email_to = st.text_input(
            "Recipient Email:", 
            key="report_email",
            placeholder="admin@company.com"
        )
        
        if st.button("✉️ Send Email Report", key="email_report_button"):
            if not email_to or "@" not in email_to:
                st.warning("Please enter a valid email address")
            else:
                with st.spinner("Generating and sending report..."):
                    csv_file = export_to_csv(sheet)
                    if csv_file and send_email_with_csv(email_to, csv_file):
                        st.success("Report emailed successfully!")
                    else:
                        st.error("Failed to send report")
    
    # Export CSV section
    with st.expander("Export Data"):
        if st.button("📥 Export as CSV", key="export_csv_button"):
            with st.spinner("Exporting data..."):
                csv_file = export_to_csv(sheet)
                if csv_file:
                    st.success(f"Exported: {csv_file}")
                    with open(csv_file, "rb") as f:
                        st.download_button(
                            label="Download CSV",
                            data=f,
                            file_name=os.path.basename(csv_file),
                            mime="text/csv",
                            key="download_csv"
                        )

# ====================
# EMPLOYEE DASHBOARD
# ====================
def render_employee_dashboard():
    """Render the employee dashboard"""
    st.title(f"👋 Welcome, {st.session_state.user}")
    
    _, sheet = connect_to_google_sheets()
    if not sheet:
        return
        
    row_index, row_data = get_employee_row(sheet, st.session_state.user)
    if row_index == -1:
        st.error("Employee record not found")
        return
    
    render_employee_metrics(row_data)
    render_time_tracking_controls(sheet, row_index, row_data)

def render_employee_metrics(row_data: List[str]):
    """Render employee metrics cards"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        login_time = row_data[1] if len(row_data) > 1 else "Not logged in"
        metric_card("Login Time", login_time, "⏱️")
    
    with col2:
        break_duration = row_data[5] if len(row_data) > 5 else "00:00"
        metric_card("Break Duration", break_duration, "☕")
    
    with col3:
        work_time = row_data[6] if len(row_data) > 6 else "00:00"
        status = row_data[7] if len(row_data) > 7 else ""
        metric_card("Work Time", f"{work_time} {employee_status_badge(status)}", "🕒")

def render_time_tracking_controls(sheet: Any, row_index: int, row_data: List[str]):
    """Render time tracking buttons"""
    st.subheader("⏱ Time Tracking")
    
    # Show current status
    status = row_data[7] if len(row_data) > 7 else ""
    st.markdown(f"**Current Status:** {status}")
    
    # Action buttons
    action_col1, action_col2, action_col3 = st.columns(3)
    
    with action_col1:
        if st.button("☕ Start Break", key="start_break_button"):
            now = get_current_time()
            sheet.update_cell(row_index, 4, now)  # Break Start
            sheet.update_cell(row_index, 9, now)  # Last Update
            st.success(f"Break started at {now}")
            st.session_state.last_action = "break_start"
            st.rerun()
    
    with action_col2:
        if st.button("🔙 End Break", key="end_break_button"):
            if len(row_data) <= 3 or not row_data[3]:
                st.error("No break started.")
            else:
                now = get_current_time()
                break_duration = calculate_time_difference(row_data[3], now)
                sheet.update_cell(row_index, 5, now)  # Break End
                sheet.update_cell(row_index, 6, format_duration(break_duration))  # Break Duration
                sheet.update_cell(row_index, 9, now)  # Last Update
                st.success(f"Break ended. Duration: {format_duration(break_duration)}")
                st.session_state.last_action = "break_end"
                st.rerun()
    
    with action_col3:
        if st.button("🔒 Logout", key="logout_button"):
            if len(row_data) <= 1 or not row_data[1]:
                st.error("No login time recorded")
                return
                
            now = get_current_time()
            sheet.update_cell(row_index, 3, now)  # Logout Time
            
            # Calculate break time
            break_mins = parse_duration(row_data[5]) if len(row_data) > 5 and row_data[5] else 0
            
            # Calculate total work time
            total_mins = calculate_time_difference(row_data[1], now) - break_mins
            total_str = format_duration(total_mins)
            sheet.update_cell(row_index, 7, total_str)  # Total Work Time
            
            # Update status
            status = evaluate_status(break_mins, total_mins)
            sheet.update_cell(row_index, 8, status)  # Status
            sheet.update_cell(row_index, 9, now)  # Last Update
            
            st.success(f"Logged out. Worked: {total_str}")
            st.session_state.user = None
            st.session_state.row_index = -1
            st.session_state.last_action = "logout"
            st.rerun()

# ====================
# LANDING PAGE
# ====================
def render_landing_page():
    """Render the landing page for non-logged in users"""
    st.title("🌟 PixsEdit Employee Tracker")
    st.subheader("Luxury Interface ✨ with Live Dashboard")
    
    st.markdown("""
    <div style="text-align: center; padding: 3rem 0;">
        <h2>Welcome to the Employee Tracker</h2>
        <p>Please login from the sidebar to access your dashboard</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Features showcase
    with st.expander("✨ Key Features"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### ⏱ Time Tracking
            - Login/Logout recording
            - Break time monitoring
            - Real-time status updates
            """)
        
        with col2:
            st.markdown("""
            ### 📊 Analytics
            - Work duration visualization
            - Break time analysis
            - Status distribution
            """)
        
        with col3:
            st.markdown("""
            ### 📤 Reporting
            - Daily CSV exports
            - Email reports
            - Admin dashboard
            """)

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point"""
    try:
        setup_page()
        init_session_state()
        render_sidebar()
        
        if st.session_state.user == "admin":
            render_admin_dashboard()
        elif st.session_state.user:
            render_employee_dashboard()
        else:
            render_landing_page()
            
    except Exception as e:
        logger.error(f"Application error: {str(e)}", exc_info=True)
        st.error("A critical error occurred. Please try again later.")

if __name__ == "__main__":
    main()
