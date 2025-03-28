import os
import datetime
import csv
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.message import EmailMessage
import json

# === CONFIGURATION ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
client = gspread.authorize(creds)
SPREADSHEET_ID = "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"

EMAIL_ADDRESS = st.secrets["EMAIL_ADDRESS"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]

# === PAGE SETUP ===
st.set_page_config(page_title="🌟 PixsEdit Employee Tracker", layout="centered")
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
    </style>
""", unsafe_allow_html=True)

st.title("🕒 PixsEdit Employee Tracker")
st.subheader("Luxury Interface ✨ with Live Dashboard")

# === GOOGLE SHEETS ===
def connect_to_google_sheets():
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    sheet_name = f"Daily Logs {today}"

    if sheet_name not in [s.title for s in spreadsheet.worksheets()]:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="10")
        sheet.append_row(["Employee Name", "Login Time", "Logout Time", "Break Start", "Break End", "Break Duration", "Total Work Time", "Status"])
    else:
        sheet = spreadsheet.worksheet(sheet_name)

    users_sheet = spreadsheet.worksheet("Registered Employees")
    return users_sheet, sheet

sheet1, sheet2 = connect_to_google_sheets()

# === FUNCTIONS ===
def format_duration(minutes):
    hrs = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hrs:02}:{mins:02}"

def evaluate_status(break_str, work_str):
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
    data = sheet.get_all_values()
    filename = f"Daily Logs {datetime.datetime.now().strftime('%Y-%m-%d')}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(data)
    return filename

def send_email_with_csv(to_email, file_path):
    msg = EmailMessage()
    msg['Subject'] = 'Daily Employee Report'
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg.set_content("Attached is the daily employee report from PixsEdit Tracker.")

    with open(file_path, 'rb') as f:
        file_data = f.read()
        msg.add_attachment(file_data, maintype="application", subtype="octet-stream", filename=os.path.basename(file_path))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

# === AUTH UI ===
st.markdown("""<div class='main'>""", unsafe_allow_html=True)

username = st.text_input("👤 Username")
password = st.text_input("🔒 Password", type="password")
col1, col2 = st.columns(2)
login_btn = col1.button("🚪 Login")
register_btn = col2.button("➕ Register")

if 'user' not in st.session_state:
    st.session_state.user = None
if 'row_index' not in st.session_state:
    st.session_state.row_index = None

users = sheet1.get_all_values()[1:]
user_dict = {u[0]: u[1] for u in users if len(u) >= 2}

if register_btn:
    if username in user_dict:
        st.error("User already exists.")
    else:
        sheet1.append_row([username, password])
        st.success("Registration successful!")

if login_btn:
    if username not in user_dict or user_dict[username] != password:
        st.error("Invalid credentials.")
    else:
        st.session_state.user = username
        rows = sheet2.get_all_values()
        for i, row in enumerate(rows[1:], start=2):
            if row[0] == username:
                st.session_state.row_index = i
                break

        if username != "admin":
            if st.session_state.row_index is None:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet2.append_row([username, now, "", "", "", "", "", ""])
                st.session_state.row_index = len(sheet2.get_all_values())
                st.success(f"Logged in at {now}")
            else:
                st.info("Already logged in. Use logout when done.")

# === ADMIN DASHBOARD ===
if st.session_state.user == "admin":
    st.subheader("📊 Admin Dashboard")
    data = sheet2.get_all_values()
    headers = data[0] + ["Status"]
    table = []

    for i, row in enumerate(data[1:], start=2):
        while len(row) < 8:
            row.append("")
        status = evaluate_status(row[5], row[6])
        try:
            sheet2.update_cell(i, 8, status)
        except:
            pass
        row[7] = status
        table.append(row)

    st.dataframe([dict(zip(headers, row)) for row in table], use_container_width=True)

    st.markdown("### 📤 Export & Email Report")
    if st.button("📥 Export as CSV"):
        csv_file = export_to_csv(sheet2)
        st.success(f"Exported: {csv_file}")

    email_to = st.text_input("Send report to email:")
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

# === EMPLOYEE CONTROLS ===
elif st.session_state.user:
    st.subheader(f"Welcome, {st.session_state.user}")

    col1, col2 = st.columns(2)
    if col1.button("☕ Start Break"):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if st.session_state.row_index:
            sheet2.update_cell(st.session_state.row_index, 4, now)
            st.success(f"Break started at {now}")
        else:
            st.error("You must login first.")

    if col2.button("🔙 End Break"):
        if not st.session_state.row_index:
            st.error("Login first")
        else:
            row = sheet2.row_values(st.session_state.row_index)
            if not row[3]:
                st.error("No break started.")
            else:
                break_start = datetime.datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S")
                break_end = datetime.datetime.now()
                duration = (break_end - break_start).total_seconds() / 60
                sheet2.update_cell(st.session_state.row_index, 5, break_end.strftime("%Y-%m-%d %H:%M:%S"))
                sheet2.update_cell(st.session_state.row_index, 6, format_duration(duration))
                st.success(f"Break ended. Duration: {format_duration(duration)}")

    if st.button("🔒 Logout"):
        if st.session_state.row_index:
            row = sheet2.row_values(st.session_state.row_index)
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
        else:
            st.error("You must login first.")

st.markdown("""</div>""", unsafe_allow_html=True)
