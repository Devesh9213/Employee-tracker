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
import base64

# ====================
# CONFIGURATION
# ====================
class AppConfig:
    def __init__(self):
        self.SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        self.load_config()
        
    def load_config(self):
        try:
            creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
            self.creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.SCOPES)
            self.client = gspread.authorize(self.creds)
            self.SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
            self.EMAIL_ADDRESS = st.secrets["EMAIL_ADDRESS"]
            self.EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
            self.AVATAR_DIR = Path("avatars")
            self.AVATAR_DIR.mkdir(exist_ok=True)
        except Exception as e:
            st.error(f"Configuration error: {str(e)}")
            st.stop()

# ====================
# PAGE SETUP
# ====================
class PageSetup:
    def __init__(self):
        self.config = AppConfig()
        self.setup_page()
        
    def setup_page(self):
        st.set_page_config(
            page_title="PixsEdit Employee Tracker",
            layout="wide",
            page_icon="🕒",
            initial_sidebar_state="expanded"
        )
        self.apply_cream_theme()
        self.init_session_state()
        self.verify_persistent_login()
    
    def apply_cream_theme(self):
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
            
            /* (Keep all your existing CSS styles here) */
        </style>
        """, unsafe_allow_html=True)
    
    def init_session_state(self):
        if "user" not in st.session_state:
            st.session_state.user = None
        if "row_index" not in st.session_state:
            st.session_state.row_index = None
        if "persistent_login" not in st.session_state:
            st.session_state.persistent_login = False
        if "avatar_uploaded" not in st.session_state:
            st.session_state.avatar_uploaded = False
        if "last_action" not in st.session_state:
            st.session_state.last_action = None
        if "break_started" not in st.session_state:
            st.session_state.break_started = False
        if "break_ended" not in st.session_state:
            st.session_state.break_ended = False
        if "logout_confirmation" not in st.session_state:
            st.session_state.logout_confirmation = False
    
    def verify_persistent_login(self):
        if st.session_state.get('persistent_login') and st.session_state.user:
            try:
                sheet1, _ = GoogleSheetsIntegration(self.config).connect()
                if sheet1:
                    users = sheet1.get_all_values()[1:]
                    user_exists = any(user[0] == st.session_state.user for user in users if len(user) >= 2)
                    if not user_exists:
                        self.clear_session()
            except:
                self.clear_session()
    
    def clear_session(self):
        st.session_state.user = None
        st.session_state.persistent_login = False
        st.rerun()

# ====================
# UTILITY FUNCTIONS
# ====================
class Utils:
    @staticmethod
    def format_duration(minutes):
        try:
            hrs = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hrs:02d}:{mins:02d}"
        except:
            return "00:00"
    
    @staticmethod
    def evaluate_status(break_str, work_str):
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
                return "<span style='color: #5cb85c'>✅ Complete</span>"
            elif break_min > 50:
                return "<span style='color: #d9534f'>❌ Over Break</span>"
            else:
                return "<span style='color: #d9534f'>❌ Incomplete</span>"
        except:
            return ""
    
    @staticmethod
    def image_to_base64(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')

# ====================
# GOOGLE SHEETS INTEGRATION
# ====================
class GoogleSheetsIntegration:
    def __init__(self, config):
        self.config = config
    
    @st.cache_resource(ttl=300)
    def get_client(_self):
        return _self.config.client
    
    def connect(self):
        try:
            client = self.get_client()
            spreadsheet = client.open_by_key(self.config.SPREADSHEET_ID)
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
# AUTHENTICATION
# ====================
class Authentication:
    def __init__(self, config):
        self.config = config
        self.sheets = GoogleSheetsIntegration(config)
        self.utils = Utils()
    
    def handle_login(self, username, password):
        if not username or not password:
            st.error("Please enter both username and password")
            return

        sheet1, _ = self.sheets.connect()
        if sheet1 is None:
            return

        users = sheet1.get_all_values()[1:]
        user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

        if username not in user_dict or user_dict[username] != password:
            st.error("Invalid credentials. Please try again.")
        else:
            st.session_state.user = username
            st.session_state.persistent_login = True
            
            _, sheet2 = self.sheets.connect()
            if sheet2 is None:
                return

            rows = sheet2.get_all_values()
            st.session_state.row_index = None
            
            for i, row in enumerate(rows[1:]):
                if row and row[0] == username:
                    st.session_state.row_index = i + 2
                    break

            if username != "admin" and st.session_state.row_index is None:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet2.append_row([username, now, "", "", "", "", "", ""])
                st.session_state.row_index = len(sheet2.get_all_values())

            st.success(f"Welcome back, {username}!")
            time.sleep(1)
            st.rerun()
    
    def handle_logout(self):
        try:
            _, sheet2 = self.sheets.connect()
            if sheet2 and st.session_state.row_index:
                row = sheet2.row_values(st.session_state.row_index)
                if len(row) > 1 and row[1]:
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
                    total_str = Utils.format_duration(total_mins)
                    
                    sheet2.update_cell(st.session_state.row_index, 7, total_str)
                    status = Utils.evaluate_status(row[5] if len(row) > 5 else "", total_str)
                    sheet2.update_cell(st.session_state.row_index, 8, status)

        except Exception as e:
            st.error(f"Error saving logout data: {str(e)}")
        
        st.session_state.user = None
        st.session_state.row_index = None
        st.session_state.persistent_login = False
        st.session_state.break_started = False
        st.session_state.break_ended = False
        st.session_state.last_action = None
        st.session_state.logout_confirmation = False
        
        st.success("Logged out successfully!")
        time.sleep(1)
        st.rerun()

# ====================
# DASHBOARD COMPONENTS
# ====================
class DashboardComponents:
    def __init__(self, config):
        self.config = config
        self.sheets = GoogleSheetsIntegration(config)
        self.utils = Utils()
    
    def render_sidebar(self):
        with st.sidebar:
            st.markdown("""
            <div style="text-align: center; margin-bottom: 2rem;">
                <h1 style="color: #8b8b83; font-size: 1.8rem;">PixsEdit Tracker</h1>
                <p style="color: #a0a099; font-size: 0.9rem;">Elegant Time Management</p>
            </div>
            """, unsafe_allow_html=True)
            
            self.render_avatar_section()
            self.render_login_section()
    
    def render_avatar_section(self):
        if st.session_state.user:
            avatar_path = self.config.AVATAR_DIR / f"{st.session_state.user}.png"
            if avatar_path.exists():
                st.markdown(f"""
                <div class="avatar-container">
                    <img src="data:image/png;base64,{self.utils.image_to_base64(avatar_path)}" 
                         class="avatar-image" width="120" height="120" alt="User Avatar">
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-weight: 500; color: #333333;'>{st.session_state.user}</p>", 
                           unsafe_allow_html=True)

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
                temp_path = self.config.AVATAR_DIR / "temp_avatar.png"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_avatar.read())
                st.markdown(f"""
                <div class="avatar-container">
                    <img src="data:image/png;base64,{self.utils.image_to_base64(temp_path)}" 
                         class="avatar-image" width="100" height="100" alt="Preview Avatar">
                </div>
                """, unsafe_allow_html=True)
    
    def render_login_section(self):
        st.markdown("---")
        auth = Authentication(self.config)
        
        if st.session_state.user:
            if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
                st.session_state.logout_confirmation = True
                
            if st.session_state.get('logout_confirmation'):
                st.warning("Are you sure you want to logout?")
                col1, col2 = st.columns(2)
                
                if col1.button("✅ Yes, Logout", use_container_width=True, key="confirm_logout"):
                    auth.handle_logout()
                
                if col2.button("❌ Cancel", use_container_width=True, key="cancel_logout"):
                    st.session_state.logout_confirmation = False
                    st.rerun()
        else:
            st.markdown("### 🔐 Authentication")
            username = st.text_input("👤 Username", placeholder="Enter your username", key="username_input")
            password = st.text_input("🔒 Password", type="password", placeholder="Enter your password", key="password_input")

            col1, col2 = st.columns(2)
            if col1.button("Login", use_container_width=True, key="login_btn"):
                auth.handle_login(username, password)
            if col2.button("Register", use_container_width=True, key="register_btn"):
                self.handle_registration(username, password)
    
    def handle_registration(self, username, password):
        if not username or not password:
            st.error("Please enter both username and password")
            return

        sheet1, _ = self.sheets.connect()
        if sheet1 is None:
            return

        users = sheet1.get_all_values()[1:]
        user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

        if username in user_dict:
            st.error("Username already exists. Please choose another.")
        else:
            sheet1.append_row([username, password])
            st.success("Registration successful! You can now login.")
            time.sleep(1.5)
            st.rerun()

# ====================
# MAIN APPLICATION
# ====================
class PixsEditTracker:
    def __init__(self):
        self.config = AppConfig()
        self.page_setup = PageSetup()
        self.components = DashboardComponents(self.config)
        self.utils = Utils()
        self.sheets = GoogleSheetsIntegration(self.config)
    
    def run(self):
        try:
            self.components.render_sidebar()
            self.render_main_content()
        except Exception as e:
            st.error(f"Application error: {str(e)}")
    
    def render_main_content(self):
        if st.session_state.get('persistent_login') and st.session_state.user:
            if st.session_state.user == "admin":
                self.render_admin_dashboard()
            else:
                self.render_employee_dashboard()
        else:
            self.render_landing_page()
    
    def render_admin_dashboard(self):
        st.title("📊 Admin Dashboard")
        sheet1, sheet2 = self.sheets.connect()
        if sheet2 is None:
            return

        try:
            data = sheet2.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
            
            df['Current Status'] = df.apply(
                lambda row: "🟢 Working" if pd.isna(row['Break Start']) 
                else "🟡 On Break" if pd.isna(row['Break End']) 
                else "🟢 Working",
                axis=1
            )
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            df = pd.DataFrame()

        self.render_admin_metrics(sheet1, df)
        self.render_employee_directory(df)
        self.render_admin_analytics(df)
        self.render_reporting_tools(sheet2)
    
    # (Include all your other rendering methods here)
    
    def render_landing_page(self):
        st.markdown("""
        <div class="landing-header">
            <h1>🌟 PixsEdit Employee Tracker</h1>
            <p>An elegant solution for tracking work hours, breaks, and productivity</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="feature-card">
                <h3>⏱️ Time Tracking</h3>
                <p>Track work hours and breaks with simple controls</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="feature-card">
                <h3>📊 Analytics</h3>
                <p>Beautiful visualizations of work patterns</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="feature-card">
                <h3>🔒 Secure</h3>
                <p>Your data is securely stored</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; margin-top: 2rem;">
            <p>Please login from the sidebar to access your dashboard</p>
        </div>
        """, unsafe_allow_html=True)

# ====================
# RUN APPLICATION
# ====================
if __name__ == "__main__":
    app = PixsEditTracker()
    app.run()
