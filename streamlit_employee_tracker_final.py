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

# ====================
# CONFIGURATION
# ====================
def load_config():
    """Load configuration from secrets and environment"""
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
    client = gspread.authorize(creds)
    
    return {
        "SPREADSHEET_ID": "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes",
        "EMAIL_ADDRESS": st.secrets["EMAIL_ADDRESS"],
        "EMAIL_PASSWORD": st.secrets["EMAIL_PASSWORD"],
        "client": client,
        "AVATAR_DIR": Path("avatars")
    }

config = load_config()
AVATAR_DIR = config["AVATAR_DIR"]
AVATAR_DIR.mkdir(exist_ok=True)

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme"""
    st.set_page_config(
        page_title="🌟 PixsEdit Employee Tracker", 
        layout="wide",
        page_icon="🕒"
    )
    
    # Auto theme based on time of day
    current_hour = datetime.datetime.now().hour
    auto_dark = current_hour < 6 or current_hour >= 18
    dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=auto_dark)
    
    if dark_mode:
        apply_dark_theme()
    else:
        apply_light_theme()

def apply_dark_theme():
    """Apply dark theme styling"""
    st.markdown("""
    <style>
        .main {
            background-color: #1e1e1e;
            color: #f5f5f5;
            padding: 2rem;
            border-radius: 1rem;
        }
        .stButton>button {
            background-color: #333333 !important;
            color: #ffffff !important;
        }
        .metric-card {
            background-color: #2d2d2d;
            padding: 1.5rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

def apply_light_theme():
    """Apply light theme styling"""
    st.markdown("""
    <style>
    .main {
        background-color: #f6f9fc;
        padding: 2rem;
        border-radius: 1rem;
        box-shadow: 0 0 20px rgba(0,0,0,0.1);
    }
    .stButton>button {
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        background: linear-gradient(90deg, #007cf0, #00dfd8);
        color: white;
        border: none;
    }
    .metric-card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# ====================
# UTILITY FUNCTIONS
# ====================
def format_duration(minutes):
    """Convert minutes to HH:MM format"""
    hrs = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hrs:02}:{mins:02}"

def evaluate_status(break_str, work_str):
    """Evaluate employee status based on break and work time"""
    def to_minutes(t):
        h, m = map(int, t.split(":"))
        return h * 60 + m
    
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
    """Export sheet data to CSV file"""
    data = sheet.get_all_values()
    filename = f"Daily Logs {datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(data)
    return filename

def send_email_with_csv(to_email, file_path):
    """Send email with CSV attachment"""
    msg = EmailMessage()
    msg['Subject'] = 'Daily Employee Report'
    msg['From'] = config["EMAIL_ADDRESS"]
    msg['To'] = to_email
    msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

    with open(file_path, 'rb') as f:
        file_data = f.read()
        msg.add_attachment(file_data, maintype="application", subtype="octet-stream", 
                         filename=os.path.basename(file_path))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(config["EMAIL_ADDRESS"], config["EMAIL_PASSWORD"])
        smtp.send_message(msg)

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
def connect_to_google_sheets():
    """Connect to Google Sheets and get required worksheets"""
    try:
        spreadsheet = config["client"].open_by_key(config["SPREADSHEET_ID"])
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        sheet_name = f"Daily Logs {today}"

        if sheet_name not in [s.title for s in spreadsheet.worksheets()]:
            sheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="10")
            sheet.append_row(["Employee Name", "Login Time", "Logout Time", 
                            "Break Start", "Break End", "Break Duration", 
                            "Total Work Time", "Status"])
        else:
            sheet = spreadsheet.worksheet(sheet_name)

        users_sheet = spreadsheet.worksheet("Registered Employees")
        return users_sheet, sheet
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None, None

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
        avatar_path = AVATAR_DIR / f"{st.session_state.user}.png"
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
            temp_name = "temp_avatar.png"
            temp_path = AVATAR_DIR / temp_name
            with open(temp_path, "wb") as f:
                f.write(uploaded_avatar.read())
            st.image(str(temp_path), width=100, caption="Preview")

def render_login_section():
    """Handle login/logout functionality"""
    st.markdown("---")
    if st.session_state.user:
        if st.button("🚪 Logout"):
            st.session_state.user = None
            st.session_state.row_index = None
    else:
        st.markdown("### Login")
        username = st.text_input("👤 Username")
        password = st.text_input("🔒 Password", type="password")
        
        col1, col2 = st.columns(2)
        if col1.button("Login"):
            handle_login(username, password)
        
        if col2.button("Register"):
            handle_registration(username, password)

def handle_login(username, password):
    """Process login attempt"""
    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return
        
    users = sheet1.get_all_values()[1:]
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}
    
    if username not in user_dict or user_dict[username] != password:
        st.error("Invalid credentials.")
    else:
        st.session_state.user = username
        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return
            
        rows = sheet2.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row[0] == username:
                st.session_state.row_index = i
                break

        if username != "admin" and st.session_state.row_index is None:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet2.append_row([username, now, "", "", "", "", "", ""])
            st.session_state.row_index = len(sheet2.get_all_values())

def handle_registration(username, password):
    """Process new user registration"""
    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return
        
    users = sheet1.get_all_values()[1:]
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}
    
    if username in user_dict:
        st.error("User already exists.")
    else:
        sheet1.append_row([username, password])
        st.success("Registration successful!")

# ====================
# MAIN CONTENT AREAS
# ====================
def render_main_content():
    """Render the appropriate content based on user state"""
    st.markdown("<div class='main'>", unsafe_allow_html=True)
    
    if st.session_state.user == "admin":
        render_admin_dashboard()
    elif st.session_state.user:
        render_employee_dashboard()
    else:
        render_landing_page()
        
    st.markdown("</div>", unsafe_allow_html=True)

def render_admin_dashboard():
    """Render the admin dashboard"""
    st.title("📊 Admin Dashboard")
    
    sheet1, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return
        
    data = sheet2.get_all_records()
    df = pd.DataFrame(data)
    
    render_admin_metrics(sheet1, df)
    render_employee_directory(df)
    render_admin_analytics(df)
    render_reporting_tools(sheet2)

def render_admin_metrics(sheet1, df):
    """Render admin metrics cards"""
    st.subheader("📈 Employee Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    total_employees = len(sheet1.get_all_values()) - 1
    active_today = len(df)
    on_break = len(df[df['Break Start'].notna() & df['Break End'].isna()])
    completed = len(df[df['Status'] == "✅ Complete"])
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Total Employees</h3>
            <h1>{total_employees}</h1>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Active Today</h3>
            <h1>{active_today}</h1>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>On Break</h3>
            <h1>{on_break}</h1>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Completed</h3>
            <h1>{completed}</h1>
        </div>
        """, unsafe_allow_html=True)

def render_employee_directory(df):
    """Render employee directory table"""
    st.subheader("👥 Employee Directory")
    st.dataframe(df, use_container_width=True)

def render_admin_analytics(df):
    """Render admin analytics charts"""
    st.subheader("📊 Analytics")
    tab1, tab2 = st.tabs(["Work Duration", "Status Distribution"])
    
    with tab1:
        if not df.empty:
            bar_fig = px.bar(
                df, 
                x="Employee Name", 
                y="Total Work Time", 
                title="Work Duration per Employee", 
                color="Status",
                height=400
            )
            st.plotly_chart(bar_fig, use_container_width=True)
    
    with tab2:
        if not df.empty:
            status_count = df["Status"].value_counts().reset_index()
            pie_fig = px.pie(
                status_count, 
                names="index", 
                values="Status", 
                title="Work Completion Status",
                height=400
            )
            st.plotly_chart(pie_fig, use_container_width=True)

def render_reporting_tools(sheet2):
    """Render reporting tools section"""
    st.subheader("📤 Reports")
    report_col1, report_col2 = st.columns([3, 1])
    
    with report_col1:
        email_to = st.text_input("Send report to email:")
    
    with report_col2:
        st.write("")  # Spacer
        st.write("")  # Spacer
        if st.button("✉️ Email Report"):
            if not email_to:
                st.warning("Enter a valid email.")
            else:
                try:
                    file_path = export_to_csv(sheet2)
                    send_email_with_csv(email_to, file_path)
                    st.success("Report emailed successfully.")
                except Exception as e:
                    st.error(f"Failed to send email: {e}")
    
    if st.button("📥 Export as CSV"):
        csv_file = export_to_csv(sheet2)
        st.success(f"Exported: {csv_file}")

def render_employee_dashboard():
    """Render the employee dashboard"""
    st.title(f"👋 Welcome, {st.session_state.user}")
    
    _, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return
        
    row = sheet2.row_values(st.session_state.row_index)
    
    render_employee_metrics(row)
    render_time_tracking_controls(sheet2, row)

def render_employee_metrics(row):
    """Render employee metrics cards"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        login_time = row[1] if len(row) > 1 else "Not logged in"
        st.markdown(f"""
        <div class="metric-card">
            <h3>Login Time</h3>
            <h2>{login_time}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        break_duration = row[5] if len(row) > 5 else "00:00"
        st.markdown(f"""
        <div class="metric-card">
            <h3>Break Duration</h3>
            <h2>{break_duration}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        work_time = row[6] if len(row) > 6 else "00:00"
        st.markdown(f"""
        <div class="metric-card">
            <h3>Work Time</h3>
            <h2>{work_time}</h2>
        </div>
        """, unsafe_allow_html=True)

def render_time_tracking_controls(sheet2, row):
    """Render time tracking buttons"""
    st.subheader("⏱ Time Tracking")
    action_col1, action_col2, action_col3 = st.columns(3)
    
    with action_col1:
        if st.button("☕ Start Break"):
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet2.update_cell(st.session_state.row_index, 4, now)
            st.success(f"Break started at {now}")
    
    with action_col2:
        if st.button("🔙 End Break"):
            if not row[3]:
                st.error("No break started.")
            else:
                break_start = datetime.datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
                break_end = datetime.datetime.now()
                duration = (break_end - break_start).total_seconds() / 60
                sheet2.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                sheet2.update_cell(st.session_state.row_index, 6, format_duration(duration))
                st.success(f"Break ended. Duration: {format_duration(duration)}")
    
    with action_col3:
        if st.button("🔒 Logout"):
            login_time = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            logout_time = datetime.datetime.now()
            sheet2.update_cell(st.session_state.row_index, 3, logout_time.strftime("%Y-%m-%d %H:%M:%S"))

            break_mins = 0
            if len(row) > 5 and row[5]:
                h, m = map(int, row[5].split(":"))
                break_mins = h * 60 + m

            total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
            total_str = format_duration(total_mins)
            sheet2.update_cell(st.session_state.row_index, 7, total_str)

            status = evaluate_status(row[5], total_str)
            sheet2.update_cell(st.session_state.row_index, 8, status)

            st.success(f"Logged out. Worked: {total_str}")
            st.session_state.user = None
            st.session_state.row_index = None

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

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point"""
    setup_page()
    init_session_state()
    render_sidebar()
    render_main_content()

if __name__ == "__main__":
    main()
