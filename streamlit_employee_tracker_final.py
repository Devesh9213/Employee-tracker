import os
from streamlit.components.v1 import html
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

# ====================
# CONFIGURATION
# ====================
def load_config() -> Optional[Dict[str, Any]]:
    """Load and validate application configuration from Streamlit secrets.
    
    Returns:
        Dictionary containing configuration if successful, None otherwise.
    """
    try:
        # Validate secrets exist
        if not all(key in st.secrets for key in ["GOOGLE_CREDENTIALS", *CONFIG_KEYS]):
            st.error("Missing required configuration in secrets.toml")
            return None

        # Load Google credentials
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
    except json.JSONDecodeError as e:
        st.error(f"Invalid Google credentials JSON: {str(e)}")
    except Exception as e:
        st.error(f"Configuration error: {str(e)}")
    return None

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme."""
def setup_page():
    """Configure page settings and theme."""
    st.set_page_config(
        page_title=" PixsEdit Employee Tracker",
        layout="wide",
        page_icon="",
        initial_sidebar_state="expanded"
    )
    
    # Inject custom CSS to prevent auto-hiding of sidebar
    st.markdown("""
    <style>
        [data-testid="stSidebar"][aria-expanded="true"]{
            min-width: 300px;
            max-width: 300px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    current_hour = datetime.datetime.now().hour
    auto_dark = current_hour < 6 or current_hour >= 18
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=auto_dark, key="dark_mode_toggle")

    if dark_mode:
        apply_dark_theme()
    else:
        apply_light_theme()

def apply_dark_theme():
    """Apply dark theme styling."""
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
        
        .stTextInput>div>div>input {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
        }
        
        .stDataFrame {
            background-color: var(--secondary-background-color);
        }
    </style>
    """, unsafe_allow_html=True)

def apply_light_theme():
    """Apply light theme styling."""
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
    if "user" not in st.session_state:
        st.session_state.user = None
    if "row_index" not in st.session_state:
        st.session_state.row_index = None
    if "persistent_login" not in st.session_state:
        st.session_state.persistent_login = False

def persist_session():
    html_string = """
    <script>
    const storeState = (key, value) => {
        localStorage.setItem(key, value);
    }

    if (typeof window !== 'undefined') {
        if (%s) {
            storeState('persistent_login', 'true');
            storeState('username', '%s');
        } else {
            storeState('persistent_login', 'false');
            localStorage.removeItem('username');
        }
    }
    </script>
    """ % ("true" if st.session_state.get("persistent_login", False) else "false",
           st.session_state.get("user", ""))

    html(html_string, height=0, width=0)

def check_persistent_session():
    js_code = """
    <script>
    const persistentLogin = localStorage.getItem('persistent_login') === 'true';
    const username = localStorage.getItem('username');
    if (persistentLogin && username) {
        const streamlitDoc = window.parent.document;
        const input = streamlitDoc.querySelector('input[data-testid="stTextInput"]');
        if (input) {
            input.value = username;
            const event = new Event('input', { bubbles: true });
            input.dispatchEvent(event);
        }
    }
    </script>
    """
html(js_code,height=0)

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components."""
    with st.sidebar:
        st.title("PixsEdit Tracker")
        st.caption("🌓 Auto theme applied based on time of day")

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
            value=st.session_state.get("persistent_login", False),
            key="persistent_login_checkbox"
        )
        persist_session()
        
        if st.button("🚪 Logout", key="logout_button"):
            st.session_state.user = None
            st.session_state.row_index = None
            st.session_state.break_started = False
            st.session_state.break_ended = False
            st.session_state.last_action = None
            st.session_state.persistent_login = False
            persist_session()
            st.rerun()
    else:
        st.markdown("### Login")
        username = st.text_input("👤 Username", key="username_input")
        password = st.text_input("🔒 Password", type="password", key="password_input")

        col1, col2 = st.columns(2)
        if col1.button("Login", key="login_button"):
            handle_login(username, password)
        if col2.button("Register", key="register_button"):
            handle_registration(username, password)

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
        st.session_state.persistent_login = st.session_state.get("persistent_login", False)
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
# MAIN CONTENT AREAS
# ====================
def render_main_content():
    """Render the appropriate content based on user state."""
    st.markdown("<div class='main'>", unsafe_allow_html=True)

    if st.session_state.user == "admin":
        render_admin_dashboard()
    elif st.session_state.user:
        render_employee_dashboard()
    else:
        render_landing_page()

    st.markdown("</div>", unsafe_allow_html=True)

def render_admin_dashboard():
    """Render the admin dashboard."""
    st.title("📊 Admin Dashboard")
    sheet1, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return

    try:
        data = sheet2.get_all_records()
        df = pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        df = pd.DataFrame()

    render_admin_metrics(sheet1, df)
    render_employee_directory(df)
    render_admin_analytics(df)
    render_reporting_tools(sheet2)

def render_admin_metrics(sheet1, df):
    """Render admin metrics cards."""
    st.subheader("📈 Employee Overview")
    col1, col2, col3, col4 = st.columns(4)

    try:
        total_employees = len(sheet1.get_all_values()) - 1
    except:
        total_employees = 0

    active_today = len(df) if not df.empty else 0
    on_break = len(df[df["Break Start"].notna() & df["Break End"].isna()]) if not df.empty else 0
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
                <h3>On Break</h3>
                <h1>{on_break}</h1>
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

def render_employee_directory(df):
    """Render employee directory table."""
    st.subheader("👥 Employee Directory")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=400)
    else:
        st.warning("No employee data available")

def render_admin_analytics(df):
    """Render admin analytics charts."""
    st.subheader("📊 Analytics")

    if df.empty or "Status" not in df.columns:
        st.warning("No data available for analytics")
        return

    tab1, tab2 = st.tabs(["Work Duration", "Status Distribution"])

    with tab1:
        if not df.empty and "Total Work Time" in df.columns:
            try:
                # Convert work time to minutes for plotting
                df['Work Minutes'] = df['Total Work Time'].apply(
                    lambda x: int(x.split(':')[0]) * 60 + int(x.split(':')[1]) if x and ':' in x else 0
                )
                
                bar_fig = px.bar(
                    df,
                    x="Employee Name",
                    y="Work Minutes",
                    title="Work Duration per Employee (Minutes)",
                    color="Status",
                    height=400,
                )
                bar_fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#333333' if not st.session_state.get("dark_mode", False) else '#f5f5f5')
                )
                st.plotly_chart(bar_fig, use_container_width=True)
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
                )
                pie_fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#333333' if not st.session_state.get("dark_mode", False) else '#f5f5f5')
                )
                st.plotly_chart(pie_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to create status distribution chart: {str(e)}")

def render_reporting_tools(sheet2):
    """Render reporting tools section."""
    st.subheader("📤 Reports")

    email_col, btn_col = st.columns([3, 1])
    with email_col:
        email_to = st.text_input("Send report to email:", key="report_email")

    with btn_col:
        st.write("")
        st.write("")
        if st.button("✉️ Email Report", key="email_report_button"):
            if not email_to or "@" not in email_to:
                st.warning("Please enter a valid email address")
            else:
                with st.spinner("Generating and sending report..."):
                    csv_file = export_to_csv(sheet2)
                    if csv_file and send_email_with_csv(email_to, csv_file):
                        st.success("Report emailed successfully!")
                    else:
                        st.error("Failed to send report")

    if st.button("📥 Export as CSV", key="export_csv_button"):
        with st.spinner("Exporting data..."):
            csv_file = export_to_csv(sheet2)
            if csv_file:
                st.success(f"Exported: {csv_file}")
                with open(csv_file, "rb") as f:
                    st.download_button(
                        label="Download CSV",
                        data=f,
                        file_name=csv_file,
                        mime="text/csv",
                        key="download_csv_button"
                    )

def render_employee_dashboard():
    """Render the employee dashboard."""
    st.title(f"👋 Welcome, {st.session_state.user}")

    _, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return

    try:
        row = sheet2.row_values(st.session_state.row_index)
    except Exception as e:
        st.error(f"Error loading your data: {str(e)}")
        row = []

    render_employee_metrics(row)
    render_time_tracking_controls(sheet2, row)

def render_employee_metrics(row):
    """Render employee metrics cards."""
    col1, col2, col3 = st.columns(3)

    with col1:
        login_time = row[1] if len(row) > 1 else "Not logged in"
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Login Time</h3>
                <h2>{login_time}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        break_duration = row[5] if len(row) > 5 else "00:00"
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Break Duration</h3>
                <h2>{break_duration}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        work_time = row[6] if len(row) > 6 else "00:00"
        st.markdown(
            f"""
            <div class="metric-card">
                <h3>Work Time</h3>
                <h2>{work_time}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

def render_time_tracking_controls(sheet2, row):
    """Render time tracking buttons with proper state management."""
    st.subheader("⏱ Time Tracking")
    action_col1, action_col2, action_col3 = st.columns(3)

    with action_col1:
        if st.button("☕ Start Break", key="start_break_button"):
            if st.session_state.row_index is None:
                st.error("No valid row index found")
                return

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                # Show loading spinner
                with st.spinner("Starting break..."):
                    # Update the sheet
                    sheet2.update_cell(st.session_state.row_index, 4, now)
                    
                    # Update session state
                    st.session_state.break_started = True
                    st.session_state.last_action = "break_start"
                    
                    # Small delay to ensure update completes
                    time.sleep(1.5)
                    
                    # Show success message
                    st.success(f"Break started at {now}")
                    
                    # Force a rerun to update the display
                    st.rerun()
                
            except Exception as e:
                st.error(f"Failed to start break: {str(e)}")
                st.session_state.break_started = False

    with action_col2:
        if st.button("🔙 End Break", key="end_break_button"):
            if len(row) <= 4 or not row[3]:
                st.error("No break started")
                return

            try:
                break_start = datetime.datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
                break_end = datetime.datetime.now()
                duration = (break_end - break_start).total_seconds() / 60
                
                # Show loading spinner
                with st.spinner("Ending break..."):
                    # Update both break end and duration
                    sheet2.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                    sheet2.update_cell(st.session_state.row_index, 6, format_duration(duration))
                    
                    # Update session state
                    st.session_state.break_started = False
                    st.session_state.break_ended = True
                    st.session_state.last_action = "break_end"
                    
                    # Small delay before rerun
                    time.sleep(1.5)
                    
                    # Show success message
                    st.success(f"Break ended. Duration: {format_duration(duration)}")
                    
                    # Force rerun
                    st.rerun()
                
            except Exception as e:
                st.error(f"Error ending break: {str(e)}")
                st.session_state.break_ended = False

    with action_col3:
        if st.button("🔒 Logout", key="logout_button_main"):
            if len(row) <= 1 or not row[1]:
                st.error("No login time recorded")
                return

            try:
                login_time = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                logout_time = datetime.datetime.now()
                
                # Show loading spinner
                with st.spinner("Processing logout..."):
                    # Update logout time (column 3)
                    sheet2.update_cell(st.session_state.row_index, 3, logout_time.strftime("%Y-%m-%d %H:%M:%S"))

                    # Calculate break duration
                    break_mins = 0
                    if len(row) > 5 and row[5]:
                        try:
                            h, m = map(int, row[5].split(":"))
                            break_mins = h * 60 + m
                        except:
                            break_mins = 0

                    # Calculate total work time
                    total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
                    total_str = format_duration(total_mins)
                    
                    # Update work time and status
                    sheet2.update_cell(st.session_state.row_index, 7, total_str)
                    status = evaluate_status(row[5] if len(row) > 5 else "", total_str)
                    sheet2.update_cell(st.session_state.row_index, 8, status)

                    # Clear session state
                    st.session_state.user = None
                    st.session_state.row_index = None
                    st.session_state.break_started = False
                    st.session_state.break_ended = False
                    st.session_state.last_action = None
                    st.session_state.persistent_login = False
                    persist_session()
                    
                    # Small delay
                    time.sleep(1.5)
                    
                    # Show success message
                    st.success(f"Logged out. Worked: {total_str}")
                    
                    # Force rerun
                    st.rerun()
                
            except Exception as e:
                st.error(f"Logout error: {str(e)}")

    # Display status message based on last action
    if st.session_state.get('last_action') == "break_start":
        st.info("Break is currently active")
    elif st.session_state.get('last_action') == "break_end":
        st.info("Break completed")

def render_landing_page():
    """Render the landing page for non-logged in users."""
    st.title("🌟 PixsEdit Employee Tracker")
    st.subheader("Luxury Interface ✨ with Live Dashboard")

    st.markdown(
        """
        <div style="text-align: center; padding: 3rem 0;">
            <h2>Welcome to the Employee Tracker</h2>
            <p>Please login from the sidebar to access your dashboard</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    try:
        init_session_state()
        check_persistent_session()

        if st.session_state.user:
            st.write(f"Welcome back, {st.session_state.user}!")
            if st.button("Logout"):
                st.session_state.user = None
                st.session_state.row_index = None
                st.session_state.persistent_login = False
                persist_session()
                st.experimental_rerun()
        else:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            keep_logged_in = st.checkbox("Keep me logged in")

            if st.button("Login"):
                if username == "admin" and password == "admin":
                    st.session_state.user = username
                    st.session_state.persistent_login = keep_logged_in
                    persist_session()
                    st.experimental_rerun()
                else:
                    st.error("Invalid credentials")
    except Exception as e:
        st.error(f"App error: {e}")

if __name__ == "__main__":
    main()
