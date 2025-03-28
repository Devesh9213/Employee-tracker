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
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass

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

# ====================
# CONSTANTS
# ====================
STANDARD_WORK_HOURS = 8 * 60  # 8 hours in minutes
MAX_BREAK_MINUTES = 50
BREAK_WARNING_THRESHOLD = 60  # 1 hour in minutes

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

config = load_config()
if config is None:
    st.stop()

# ====================
# THEME MANAGEMENT
# ====================
def get_system_theme() -> str:
    """Detect system theme preference using JavaScript evaluation"""
    try:
        theme = streamlit_js_eval(
            js_expressions='window.matchMedia("(prefers-color-scheme: dark)").matches', 
            want_output=True
        )
        return "dark" if theme else "light"
    except:
        current_hour = datetime.datetime.now().hour
        return "dark" if current_hour < 6 or current_hour >= 18 else "light"

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
        return "✅ Complete"
    elif break_min > MAX_BREAK_MINUTES:
        return "❌ Over Break"
    return "❌ Incomplete"

def calculate_overtime(login_time: datetime.datetime, 
                      logout_time: datetime.datetime, 
                      break_mins: int) -> float:
    """Calculate overtime hours"""
    total_mins = (logout_time - login_time).total_seconds() / 60
    worked_mins = total_mins - break_mins
    overtime = max(0, worked_mins - STANDARD_WORK_HOURS)
    return round(overtime / 60, 2)  # Convert to hours with 2 decimal places

def export_to_csv(sheet) -> Optional[str]:
    """Export sheet data to CSV file"""
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

def send_email_with_csv(to_email: str, file_path: str) -> bool:
    """Send email with CSV attachment"""
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
        st.error(f"Email failed: {str(e)}")
        return False

def get_current_datetime_str() -> str:
    """Get current datetime as formatted string"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
def connect_to_google_sheets() -> Tuple[Any, Any]:
    """Connect to Google Sheets and get required worksheets"""
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
                cols="2"
            )
            users_sheet.append_row(["Username", "Password"])

        return users_sheet, sheet
    except Exception as e:
        st.error(f"Google Sheets connection failed: {str(e)}")
        return None, None

def get_employee_record(sheet, row_index: int) -> EmployeeRecord:
    """Get employee record from sheet row"""
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

# ====================
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
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

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme"""
    try:
        st.set_page_config(
            page_title="🌟 PixsEdit Employee Tracker", 
            layout="wide",
            page_icon="🕒"
        )
        
        if 'theme' not in st.session_state:
            st.session_state.theme = get_system_theme()
            st.session_state.plotly_template = apply_theme(st.session_state.theme)
        
        with st.sidebar:
            theme_options = ["System", "Light", "Dark"]
            current_theme = st.session_state.theme.capitalize()
            selected_theme = st.selectbox(
                "Theme",
                theme_options,
                index=theme_options.index(current_theme) if current_theme in theme_options else 0
            )
            
            if selected_theme.lower() != st.session_state.theme:
                st.session_state.theme = selected_theme.lower()
                st.session_state.plotly_template = apply_theme(st.session_state.theme)
                st.rerun()
            
    except Exception as e:
        st.error(f"Page setup error: {str(e)}")

# ====================
# AUTHENTICATION
# ====================
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
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components"""
    with st.sidebar:
        try:
            st.title("PixsEdit Tracker")
            st.caption(f"🌓 Current theme: {st.session_state.theme.capitalize()}")
            
            render_avatar_section()
            render_login_section()
        except Exception as e:
            st.error(f"Sidebar error: {str(e)}")

def render_avatar_section():
    """Handle avatar upload and display"""
    try:
        if st.session_state.user:
            avatar_path = config.avatar_dir / f"{st.session_state.user}.png"
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
                temp_path = config.avatar_dir / "temp_avatar.png"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_avatar.read())
                st.image(str(temp_path), width=100, caption="Preview")
    except Exception as e:
        st.error(f"Avatar error: {str(e)}")

def render_login_section():
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
                handle_login(username, password)
            
            if col2.button("Register"):
                handle_registration(username, password)
    except Exception as e:
        st.error(f"Login error: {str(e)}")

# ====================
# ADMIN DASHBOARD
# ====================
def render_admin_dashboard():
    """Render the admin dashboard"""
    try:
        st.title("📊 Admin Dashboard")
        
        sheet1, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        try:
            data = sheet2.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
        except Exception:
            df = pd.DataFrame()
        
        render_admin_metrics(sheet1, df)
        render_employee_directory(df)
        render_admin_analytics(df)
        render_reporting_tools(sheet2)
    except Exception as e:
        st.error(f"Admin dashboard error: {str(e)}")

def render_admin_metrics(sheet1, df: pd.DataFrame):
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
            ("Total Employees", total_employees),
            ("Active Today", active_today),
            ("On Break", on_break),
            ("Completed", completed)
        ]
        
        for col, (title, value) in zip(cols, metrics):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <h3>{title}</h3>
                    <h1>{value}</h1>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Metrics error: {str(e)}")

def render_employee_directory(df: pd.DataFrame):
    """Render employee directory table"""
    try:
        st.subheader("👥 Employee Directory")
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No employee data available")
    except Exception as e:
        st.error(f"Directory error: {str(e)}")

def render_admin_analytics(df: pd.DataFrame):
    """Render admin analytics charts"""
    try:
        st.subheader("📊 Analytics")
        
        if df.empty or 'Status' not in df.columns:
            st.warning("No data available for analytics")
            return
            
        tab1, tab2, tab3 = st.tabs(["Work Duration", "Status Distribution", "Overtime Analysis"])
        
        with tab1:
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
                    st.plotly_chart(bar_fig, use_container_width=True)
                else:
                    st.warning("Work duration data not available")
            except Exception as e:
                st.error(f"Failed to create work duration chart: {str(e)}")
        
        with tab2:
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
                st.error(f"Failed to create status distribution chart: {str(e)}")
                
        with tab3:
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
                    st.plotly_chart(overtime_fig, use_container_width=True)
                else:
                    st.warning("No overtime data available")
            except Exception as e:
                st.error(f"Failed to create overtime analysis chart: {str(e)}")
                
    except Exception as e:
        st.error(f"Analytics error: {str(e)}")

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
                            file_name=csv_file,
                            mime="text/csv"
                        )
    except Exception as e:
        st.error(f"Reporting tools error: {str(e)}")

# ====================
# EMPLOYEE DASHBOARD
# ====================
def render_employee_dashboard():
    """Render the employee dashboard"""
    try:
        st.title(f"👋 Welcome, {st.session_state.user}")
        
        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        employee = get_employee_record(sheet2, st.session_state.row_index)
        
        render_employee_metrics(employee)
        render_time_tracking_controls(sheet2, employee)
        render_daily_summary(employee)
        show_break_history(sheet2)
        show_productivity_tips(employee)
        
    except Exception as e:
        st.error(f"Employee dashboard error: {str(e)}")

def render_employee_metrics(employee: EmployeeRecord):
    """Render employee metrics cards"""
    try:
        cols = st.columns(3)
        
        metrics = [
            ("Login Time", employee.login_time or "Not logged in"),
            ("Break Duration", employee.break_duration or "00:00"),
            ("Work Time", employee.work_time or "00:00")
        ]
        
        for col, (title, value) in zip(cols, metrics):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <h3>{title}</h3>
                    <h2>{value}</h2>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Employee metrics error: {str(e)}")

def render_time_tracking_controls(sheet, employee: EmployeeRecord):
    """Render time tracking buttons with fixed break functionality"""
    try:
        st.subheader("⏱ Time Tracking")
        cols = st.columns(3)

              with cols[0]:  # Start Break button
            if st.button("☕ Start Break"):
                if employee.break_start and not employee.break_end:
                    st.warning("Break already in progress!")
                elif employee.break_start and employee.break_end:
                    st.warning("You've already taken a break today.")
                else:
                    current_time = get_current_datetime_str()
                    sheet.update_cell(st.session_state.row_index, 4, current_time)
                    st.success(f"Break started at {current_time}")
                    st.rerun()

        with cols[1]:  # End Break button
            if st.button("🔙 End Break"):
                if not employee.break_start:
                    st.warning("No break has been started.")
                elif employee.break_end:
                    st.warning("Break already ended!")
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
                        st.error(f"Break end failed: {str(e)}")

        with cols[2]:  # Logout button
            if st.button("🔒 Logout"):
                handle_logout(sheet, employee)

    except Exception as e:
        st.error(f"Time tracking error: {str(e)}")

def handle_logout(sheet, employee: EmployeeRecord):
    """Handle logout process with proper break time calculation"""
    try:
        if not employee.login_time:  # Check if login time exists
            st.error("No login time recorded")
            return
            
        login_time = datetime.datetime.strptime(employee.login_time, "%Y-%m-%d %H:%M:%S")
        logout_time = datetime.datetime.now()
        
        # Update logout time
        sheet.update_cell(st.session_state.row_index, 3, logout_time.strftime("%Y-%m-%d %H:%M:%S"))

        # Calculate break duration if break was taken
        break_mins = time_str_to_minutes(employee.break_duration) if employee.break_duration else 0

        # Calculate total work time (minus break time)
        total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
        total_str = format_duration(total_mins)
        
        # Update work time
        sheet.update_cell(st.session_state.row_index, 7, total_str)
        
        # Evaluate and update status
        status = evaluate_status(employee.break_duration or "", total_str)
        sheet.update_cell(st.session_state.row_index, 8, status)

        # Calculate and store overtime
        overtime = calculate_overtime(login_time, logout_time, break_mins)
        sheet.update_cell(st.session_state.row_index, 9, f"{overtime} hours")

        st.success(f"Logged out. Worked: {total_str}")
        st.session_state.user = None
        st.session_state.row_index = None
        st.rerun()
    except Exception as e:
        st.error(f"Logout error: {str(e)}")

def render_daily_summary(employee: EmployeeRecord):
    """Show summary of today's work"""
    try:
        if employee.work_time:  # Work time exists
            st.subheader("📝 Today's Summary")
            cols = st.columns(3)
            with cols[0]:
                st.metric("Work Time", employee.work_time)
            with cols[1]:
                st.metric("Break Time", employee.break_duration or "00:00")
            with cols[2]:
                st.metric("Overtime", employee.overtime or "0 hours")
    except Exception as e:
        st.error(f"Daily summary error: {str(e)}")

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
        st.error(f"Break history error: {str(e)}")

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
        st.error(f"Productivity tips error: {str(e)}")

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
            <p>Please login from the sidebar to access your dashboard</p>
        </div>
        """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Landing page error: {str(e)}")

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
        st.error(f"Content rendering error: {str(e)}")

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
        st.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    main()
improve this code
