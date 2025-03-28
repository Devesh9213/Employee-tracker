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
    """Load configuration from secrets and environment."""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)

        return {
            "SPREADSHEET_ID": "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes",
            "EMAIL_ADDRESS": st.secrets["EMAIL_ADDRESS"],
            "EMAIL_PASSWORD": st.secrets["EMAIL_PASSWORD"],
            "client": client,
            "AVATAR_DIR": Path("avatars"),
        }
    except Exception as e:
        st.error(f"Configuration error: {str(e)}")
        return None

config = load_config()
if config is None:
    st.stop()

AVATAR_DIR = config["AVATAR_DIR"]
AVATAR_DIR.mkdir(exist_ok=True)

# ====================
# PAGE SETUP
# ====================
def setup_page():
    """Configure page settings and theme."""
    try:
        st.set_page_config(
            page_title="🌟 PixsEdit Employee Tracker",
            layout="wide",
            page_icon="🕒",
        )
        current_hour = datetime.datetime.now().hour
        auto_dark = current_hour < 6 or current_hour >= 18
        dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=auto_dark)

        if dark_mode:
            apply_dark_theme()
        else:
            apply_light_theme()
    except Exception as e:
        st.error(f"Page setup error: {str(e)}")

def apply_dark_theme():
    """Apply dark theme styling."""
    st.markdown(
        """
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
            .stAlert {
                border-radius: 0.5rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

def apply_light_theme():
    """Apply light theme styling."""
    st.markdown(
        """
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
            .stAlert {
                border-radius: 0.5rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ====================
# UTILITY FUNCTIONS
# ====================
def format_duration(minutes):
    """Convert minutes to HH:MM format."""
    try:
        hrs = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hrs:02}:{mins:02}"
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
        with open(filename, "w", newline="") as f:
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
        msg["Subject"] = "Daily Employee Report"
        msg["From"] = config["EMAIL_ADDRESS"]
        msg["To"] = to_email
        msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

        with open(file_path, "rb") as f:
            file_data = f.read()
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="octet-stream",
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
def connect_to_google_sheets():
    """Connect to Google Sheets and get required worksheets."""
    try:
        spreadsheet = config["client"].open_by_key(config["SPREADSHEET_ID"])
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        sheet_name = f"Daily Logs {today}"

        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="10")
            sheet.append_row(
                [
                    "Employee Name",
                    "Login Time",
                    "Logout Time",
                    "Break Start",
                    "Break End",
                    "Break Duration",
                    "Total Work Time",
                    "Status",
                ]
            )

        try:
            users_sheet = spreadsheet.worksheet("Registered Employees")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(title="Registered Employees", rows="100", cols="2")
            users_sheet.append_row(["Username", "Password"])

        return users_sheet, sheet
    except Exception as e:
        st.error(f"Google Sheets connection failed: {str(e)}")
        return None, None

# ====================
# SESSION STATE MANAGEMENT
# ====================
def init_session_state():
    """Initialize session state variables."""
    if "user" not in st.session_state:
        st.session_state.user = None
    if "row_index" not in st.session_state:
        st.session_state.row_index = None
    if "avatar_uploaded" not in st.session_state:
        st.session_state.avatar_uploaded = False

# ====================
# SIDEBAR COMPONENTS
# ====================
def render_sidebar():
    """Render the sidebar components."""
    with st.sidebar:
        try:
            st.title("PixsEdit Tracker")
            st.caption("🌓 Auto theme applied based on time of day")

            render_avatar_section()
            render_login_section()
        except Exception as e:
            st.error(f"Sidebar error: {str(e)}")

def render_avatar_section():
    """Handle avatar upload and display."""
    try:
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
    except Exception as e:
        st.error(f"Avatar error: {str(e)}")

def render_login_section():
    """Handle login/logout functionality."""
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

def handle_login(username, password):
    """Process login attempt."""
    try:
        if not username or not password:
            st.error("Username and password are required")
            return

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
            st.session_state.row_index = next(
                (i + 2 for i, row in enumerate(rows[1:]) if row and row[0] == username),
                None,
            )

            if username != "admin" and st.session_state.row_index is None:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet2.append_row([username, now, "", "", "", "", "", ""])
                st.session_state.row_index = len(sheet2.get_all_values())

            st.rerun()
    except Exception as e:
        st.error(f"Login processing error: {str(e)}")

def handle_registration(username, password):
    """Process new user registration."""
    try:
        if not username or not password:
            st.error("Username and password are required")
            return

        sheet1, _ = connect_to_google_sheets()
        if sheet1 is None:
            return

        users = sheet1.get_all_values()[1:]
        user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

        if username in user_dict:
            st.error("User already exists.")
        else:
            sheet1.append_row([username, password])
            st.success("Registration successful! Please login.")
    except Exception as e:
        st.error(f"Registration error: {str(e)}")

# ====================
# MAIN CONTENT AREAS
# ====================
def render_main_content():
    """Render the appropriate content based on user state."""
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

def render_admin_dashboard():
    """Render the admin dashboard."""
    try:
        st.title("📊 Admin Dashboard")

        sheet1, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return

        try:
            data = sheet2.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
        except:
            df = pd.DataFrame()

        render_admin_metrics(sheet1, df)
        render_employee_directory(df)
        render_admin_analytics(df)
        render_reporting_tools(sheet2)
    except Exception as e:
        st.error(f"Admin dashboard error: {str(e)}")

def render_admin_metrics(sheet1, df):
    """Render admin metrics cards."""
    try:
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
    except Exception as e:
        st.error(f"Metrics error: {str(e)}")

def render_employee_directory(df):
    """Render employee directory table."""
    try:
        st.subheader("👥 Employee Directory")
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No employee data available")
    except Exception as e:
        st.error(f"Directory error: {str(e)}")

def render_admin_analytics(df):
    """Render admin analytics charts with proper error handling."""
    try:
        st.subheader("📊 Analytics")

        if df.empty or "Status" not in df.columns:
            st.warning("No data available for analytics")
            return

        tab1, tab2 = st.tabs(["Work Duration", "Status Distribution"])

        with tab1:
            try:
                if not df.empty and "Total Work Time" in df.columns:
                    bar_fig = px.bar(
                        df,
                        x="Employee Name",
                        y="Total Work Time",
                        title="Work Duration per Employee",
                        color="Status",
                        height=400,
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
                    )
                    st.plotly_chart(pie_fig, use_container_width=True)
                else:
                    st.warning("No status data available for pie chart")
            except Exception as e:
                st.error(f"Failed to create status distribution chart: {str(e)}")
    except Exception as e:
        st.error(f"Analytics error: {str(e)}")

def render_reporting_tools(sheet2):
    """Render reporting tools section."""
    try:
        st.subheader("📤 Reports")

        email_col, btn_col = st.columns([3, 1])
        with email_col:
            email_to = st.text_input("Send report to email:", key="report_email")

        with btn_col:
            st.write("")
            st.write("")
            if st.button("✉️ Email Report"):
                if not email_to or "@" not in email_to:
                    st.warning("Please enter a valid email address")
                else:
                    with st.spinner("Generating and sending report..."):
                        csv_file = export_to_csv(sheet2)
                        if csv_file and send_email_with_csv(email_to, csv_file):
                            st.success("Report emailed successfully!")
                        else:
                            st.error("Failed to send report")

        if st.button("📥 Export as CSV"):
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
                        )
    except Exception as e:
        st.error(f"Reporting tools error: {str(e)}")

def render_employee_dashboard():
    """Render the employee dashboard."""
    try:
        st.title(f"👋 Welcome, {st.session_state.user}")

        _, sheet2 = connect_to_google_sheets()
        if sheet2 is None:
            return

        try:
            row = sheet2.row_values(st.session_state.row_index)
        except:
            row = []

        render_employee_metrics(row)
        render_time_tracking_controls(sheet2, row)
    except Exception as e:
        st.error(f"Employee dashboard error: {str(e)}")

def render_employee_metrics(row):
    """Render employee metrics cards."""
    try:
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
    except Exception as e:
        st.error(f"Employee metrics error: {str(e)}")

def render_time_tracking_controls(sheet2, row):
    """Render time tracking buttons."""
    try:
        st.subheader("⏱ Time Tracking")
        action_col1, action_col2, action_col3 = st.columns(3)

        with action_col1:
            if st.button("☕ Start Break"):
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet2.update_cell(st.session_state.row_index, 4, now)
                st.success(f"Break started at {now}")
                st.rerun()

        with action_col2:
            if st.button("🔙 End Break"):
                if len(row) <= 3 or not row[3]:
                    st.error("No break started.")
                else:
                    try:
                        break_start = datetime.datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
                        break_end = datetime.datetime.now()
                        duration = (break_end - break_start).total_seconds() / 60
                        sheet2.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                        sheet2.update_cell(st.session_state.row_index, 6, format_duration(duration))
                        st.success(f"Break ended. Duration: {format_duration(duration)}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error ending break: {str(e)}")

        with action_col3:
            if st.button("🔒 Logout"):
                try:
                    if len(row) <= 1 or not row[1]:
                        st.error("No login time recorded")
                        return

                    login_time = datetime.datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                    logout_time = datetime.datetime.now()
                    sheet2.update_cell(st.session_state.row_index, 3, logout_time.strftime("%Y-%m-%d %H:%M:%S"))

                    break_mins = 0
                    if len(row) > 5 and row[5]:
                        try:
                            h, m = map(int, row[5].split(":"))
                            break_mins = h * 60 + m
                        except:
                            break_mins = 0

                    total_mins = (logout_time - login_time).total_seconds() / 60 - break_mins
                    total_str = format_duration(total_mins)
                    sheet2.update_cell(st.session_state.row_index, 7, total_str)

                    status = evaluate_status(row[5] if len(row) > 5 else "", total_str)
                    sheet2.update_cell(st.session_state.row_index, 8, status)

                    st.success(f"Logged out. Worked: {total_str}")
                    st.session_state.user = None
                    st.session_state.row_index = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Logout error: {str(e)}")
    except Exception as e:
        st.error(f"Time tracking error: {str(e)}")

def render_landing_page():
    """Render the landing page for non-logged in users."""
    try:
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
    except Exception as e:
        st.error(f"Landing page error: {str(e)}")

# ====================
# MAIN APP EXECUTION
# ====================
def main():
    """Main application entry point."""
    try:
        setup_page()
        init_session_state()
        render_sidebar()
        render_main_content()
    except Exception as e:
        st.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    main()
