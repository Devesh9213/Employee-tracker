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
            return"<span style='color: #5cb85c'>✅ Complete</span>"
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
        const input = streamlitDoc.querySelector('input[data-testid=\"stTextInput\"]');
        if (input) {
            input.value = username;
            const event = new Event('input', { bubbles: true });
            input.dispatchEvent(event);
        }
    }
    </script>
    """
    html(js_code, height=0)

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
            st.markdown("""
            <div class="avatar-container">
                <img src="" class="avatar-image" width="120" height="120" alt="User Avatar">
            </div>
            """.replace('src=""', f'src="data:image/png;base64,{image_to_base64(avatar_path)}"'), unsafe_allow_html=True)
            st.markdown(f"<p style='text-align: center; font-weight: 500; color: #333333;'>{st.session_state.user}</p>", unsafe_allow_html=True)

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
            st.markdown("""
            <div class="avatar-container">
                <img src="" class="avatar-image" width="100" height="100" alt="Preview Avatar">
            </div>
            """.replace('src=""', f'src="data:image/png;base64,{image_to_base64(temp_path)}"'), unsafe_allow_html=True)

def image_to_base64(image_path):
    """Convert image to base64 for HTML display."""
    import base64
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

def render_login_section():
    """Handle login/logout functionality."""
    st.markdown("---")
    if st.session_state.user:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.user = None
            st.session_state.row_index = None
            st.session_state.break_started = False
            st.session_state.break_ended = False
            st.session_state.last_action = None
            st.success("Logged out successfully!")
            time.sleep(1)
            st.rerun()
    else:
        st.markdown("### 🔐 Authentication")
        username = st.text_input("👤 Username", placeholder="Enter your username")
        password = st.text_input("🔒 Password", type="password", placeholder="Enter your password")

        col1, col2 = st.columns(2)
        if col1.button("Login", use_container_width=True):
            handle_login(username, password)
        if col2.button("Register", use_container_width=True):
            handle_registration(username, password)

def handle_login(username, password):
    """Process login attempt."""
    if not username or not password:
        st.error("Please enter both username and password")
        return

    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return

    users = sheet1.get_all_values()[1:]  # Skip header
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

    if username not in user_dict or user_dict[username] != password:
        st.error("Invalid credentials. Please try again.")
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

        st.success(f"Welcome back, {username}!")
        time.sleep(1)
        st.rerun()

def handle_registration(username, password):
    """Process new user registration."""
    if not username or not password:
        st.error("Please enter both username and password")
        return

    sheet1, _ = connect_to_google_sheets()
    if sheet1 is None:
        return

    users = sheet1.get_all_values()[1:]  # Skip header
    user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

    if username in user_dict:
        st.error("Username already exists. Please choose another.")
    else:
        sheet1.append_row([username, password])
        st.success("Registration successful! You can now login.")
        time.sleep(1.5)
        st.rerun()

# ====================
# MAIN CONTENT AREAS
# ====================
def render_main_content():
    """Render the appropriate content based on user state."""
    if st.session_state.user == "admin":
        render_admin_dashboard()
    elif st.session_state.user:
        render_employee_dashboard()
    else:
        render_landing_page()

def render_admin_dashboard():
    """Render the admin dashboard with break status indicators."""
    st.title("📊 Admin Dashboard")
    sheet1, sheet2 = connect_to_google_sheets()
    if sheet2 is None:
        return

    try:
        data = sheet2.get_all_records()
        df = pd.DataFrame(data) if data else pd.DataFrame()
        
        # Add 'On Break' status column
        df['Current Status'] = df.apply(
            lambda row: "🟢 Working" if pd.isna(row['Break Start']) 
            else "🟡 On Break" if pd.isna(row['Break End']) 
            else "🟢 Working",
            axis=1
        )
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        df = pd.DataFrame()

    render_admin_metrics(sheet1, df)
    render_employee_directory(df)
    render_admin_analytics(df)
    render_reporting_tools(sheet2)

def render_employee_directory(df):
    """Render employee directory table with status indicators."""
    st.subheader("👥 Employee Directory")
    if not df.empty:
        # Format the DataFrame for better display
        display_df = df.copy()
        
        # Colorize status columns
        display_df['Current Status'] = display_df['Current Status'].apply(
            lambda x: f"<span style='color: #5cb85c'>{x}</span>" if "Working" in x 
            else f"<span style='color: #f0ad4e'>{x}</span>"
        )
        
        if 'Status' in display_df.columns:
            display_df['Status'] = display_df['Status'].apply(
                lambda x: f"<span style='color: #5cb85c'>{x}</span>" if 'Complete' in str(x) 
                else f"<span style='color: #d9534f'>{x}</span>"
            )
        
        st.write(display_df.to_html(escape=False), unsafe_allow_html=True)
    else:
        st.warning("No employee data available for today")

def render_admin_metrics(sheet1, df):
    """Render admin metrics cards with break status."""
    st.subheader("📈 Employee Overview")
    col1, col2, col3, col4 = st.columns(4)

    try:
        total_employees = len(sheet1.get_all_values()) - 1
    except:
        total_employees = 0

    active_today = len(df) if not df.empty else 0
    on_break = len(df[df['Current Status'] == "🟡 On Break"]) if not df.empty else 0
    completed = len(df[df['Status'] == "✅ Complete"]) if not df.empty and "Status" in df.columns else 0

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
        # Format the DataFrame for better display
        display_df = df.copy()
        if 'Status' in display_df.columns:
            display_df['Status'] = display_df['Status'].apply(lambda x: f"<span style='color: {'#5cb85c' if 'Complete' in str(x) else '#d9534f'}'>{x}</span>")
        
        st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.warning("No employee data available for today")

def render_admin_analytics(df):
    """Render admin analytics charts."""
    st.subheader("📊 Analytics")

    if df.empty or "Status" not in df.columns:
        st.warning("No data available for analytics")
        return

    tab1, tab2 = st.tabs(["Work Duration Analysis", "Status Distribution"])

    with tab1:
        if not df.empty and "Total Work Time" in df.columns:
            try:
                # Convert work time to minutes for plotting
                df['Work Minutes'] = df['Total Work Time'].apply(
                    lambda x: int(x.split(':')[0]) * 60 + int(x.split(':')[1]) if x else 0
                )
                
                bar_fig = px.bar(
                    df,
                    x="Employee Name",
                    y="Work Minutes",
                    title="Work Duration per Employee (Minutes)",
                    color="Status",
                    color_discrete_map={
                        "✅ Complete": "#5cb85c",
                        "❌ Incomplete": "#f0ad4e",
                        "❌ Over Break": "#d9534f"
                    },
                    height=400,
                    template="plotly_white"
                )
                bar_fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    xaxis_title="Employee",
                    yaxis_title="Work Duration (minutes)",
                    hovermode="x unified"
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
                    color="index",
                    color_discrete_map={
                        "✅ Complete": "#5cb85c",
                        "❌ Incomplete": "#f0ad4e",
                        "❌ Over Break": "#d9534f"
                    },
                    template="plotly_white"
                )
                pie_fig.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    marker=dict(line=dict(color='#ffffff', width=1))
                )
                pie_fig.update_layout(
                    uniformtext_minsize=12,
                    uniformtext_mode='hide',
                    showlegend=False
                )
                st.plotly_chart(pie_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to create status distribution chart: {str(e)}")

def render_reporting_tools(sheet2):
    """Render reporting tools section."""
    st.subheader("📤 Reporting Tools")

    with st.expander("Export Options", expanded=True):
        email_col, btn_col = st.columns([3, 1])
        with email_col:
            email_to = st.text_input("Email address to send report:", placeholder="manager@company.com", key="report_email")

        with btn_col:
            st.write("")
            st.write("")
            if st.button("✉️ Email Report", use_container_width=True):
                if not email_to or "@" not in email_to:
                    st.warning("Please enter a valid email address")
                else:
                    with st.spinner("Generating and sending report..."):
                        csv_file = export_to_csv(sheet2)
                        if csv_file and send_email_with_csv(email_to, csv_file):
                            st.success("Report emailed successfully!")
                        else:
                            st.error("Failed to send report")

        if st.button("📥 Export as CSV", use_container_width=True):
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
                            use_container_width=True
                        )

def render_employee_dashboard():
    """Render the employee dashboard."""
    st.title(f"👋 Welcome, {st.session_state.user}")
    st.markdown("---")

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
    
    # Status indicator
    if st.session_state.get('last_action') == "break_start":
        st.info("🟡 Break is currently active")
    elif st.session_state.get('last_action') == "break_end":
        st.success("🟢 Break completed")
    else:
        st.info("🔵 Ready to track your time")

    action_col1, action_col2, action_col3 = st.columns(3)

    with action_col1:
        if st.button("☕ Start Break", use_container_width=True):
            if st.session_state.row_index is None:
                st.error("No valid row index found")
                return

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                with st.spinner("Starting break..."):
                    sheet2.update_cell(st.session_state.row_index, 4, now)
                    st.session_state.break_started = True
                    st.session_state.last_action = "break_start"
                    time.sleep(1.5)
                    st.success(f"Break started at {now}")
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to start break: {str(e)}")
                st.session_state.break_started = False

    with action_col2:
        if st.button("🔙 End Break", use_container_width=True):
            if len(row) <= 4 or not row[3]:
                st.error("No break started")
                return

            try:
                break_start = datetime.datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
                break_end = datetime.datetime.now()
                duration = (break_end - break_start).total_seconds() / 60
                
                with st.spinner("Ending break..."):
                    sheet2.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                    sheet2.update_cell(st.session_state.row_index, 6, format_duration(duration))
                    st.session_state.break_started = False
                    st.session_state.break_ended = True
                    st.session_state.last_action = "break_end"
                    time.sleep(1.5)
                    st.success(f"Break ended. Duration: {format_duration(duration)}")
                    st.rerun()
            except Exception as e:
                st.error(f"Error ending break: {str(e)}")
                st.session_state.break_ended = False

    with action_col3:
        if st.button("🔒 Logout", use_container_width=True, key="logout_btn"):
            st.session_state.logout_confirmation = True
            
        if st.session_state.get('logout_confirmation'):
            st.warning("Are you sure you want to logout?")
            col1, col2 = st.columns(2)
            
            if col1.button("✅ Yes, Logout", use_container_width=True):
                try:
                    if len(row) <= 1 or not row[1]:
                        st.error("No login time recorded")
                        return

                    login_time = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    logout_time = datetime.datetime.now()
                    
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
                        st.session_state.logout_confirmation = False
                        
                        time.sleep(1.5)
                        st.success("Logged out successfully!")
                        time.sleep(1.5)
                        st.rerun()
                except Exception as e:
                    st.error(f"Logout error: {str(e)}")
            
            if col2.button("❌ Cancel", use_container_width=True):
                st.session_state.logout_confirmation = False
                st.rerun()

def render_landing_page():
    """Render the landing page for non-logged in users."""
    st.markdown("""
    <div class="landing-header">
        <h1> PixsEdit Employee Tracker</h1>
        <p>An elegant solution for tracking work hours, breaks, and productivity with beautiful visualizations</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div style="background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); height: 100%;">
            <h3 style="color: #8b8b83;">⏱️ Time Tracking</h3>
            <p style="color: #666;">Easily track your work hours, breaks, and productivity with simple controls.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); height: 100%;">
            <h3 style="color: #8b8b83;">📊 Analytics</h3>
            <p style="color: #666;">Beautiful visualizations help you understand work patterns and productivity.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); height: 100%;">
            <h3 style="color: #8b8b83;">🔒 Secure</h3>
            <p style="color: #666;">Your data is securely stored and only accessible to authorized users.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; margin-top: 2rem;">
        <p style="color: #8b8b83;">Please login from the sidebar to access your dashboard</p>
    </div>
    """, unsafe_allow_html=True)

# ====================
# Helper for live status styling
# ====================
def determine_current_status(row):
    now = datetime.datetime.now()
    if row["Logout Time"]:
        return "🔴 Logged Out"
    elif row["Break Start"] and not row["Break End"]:
        return "☕ On Break"
    else:
        return "🟢 Working"

def highlight_row(row):
    if row["Current Status"] == "☕ On Break":
        return ['background-color: #e6ffe6'] * len(row)
    elif row["Break Duration"]:
        try:
            h, m = map(int, row["Break Duration"].split(":"))
            total = h * 60 + m
            if total > 50:
                return ['background-color: #ffe6e6'] * len(row)
        except:
            pass
    return [''] * len(row)
# ====================
# MAIN APP EXECUTION
# ====================
def main():
    try:
        init_session_state()
        check_persistent_session()

        # Auto-refresh every 60 seconds
        st_autorefresh(interval=60000)

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

# ====================
# Helper for live status styling
# ====================
def determine_current_status(row):
    now = datetime.datetime.now()
    if row["Logout Time"]:
        return "🔴 Logged Out"
    elif row["Break Start"] and not row["Break End"]:
        return "☕ On Break"
    else:
        return "🟢 Working"

def highlight_row(row):
    if row["Current Status"] == "☕ On Break":
        return ['background-color: #e6ffe6'] * len(row)
    elif row["Break Duration"]:
        try:
            h, m = map(int, row["Break Duration"].split(":"))
            total = h * 60 + m
            if total > 50:
                return ['background-color: #ffe6e6'] * len(row)
        except:
            pass
    return [''] * len(row)

if __name__ == "__main__":
    main()
