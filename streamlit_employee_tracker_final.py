import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import tkinter as tk
from tkinter import messagebox, ttk

# Print current working directory for debugging
print("Current Working Directory:", os.getcwd())

# Google Sheets API setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")  # Ensure this file is in the same directory
SPREADSHEET_ID = "1Pn9bMdHwK1OOvoNtsc_i3kIeuFahQixaM4bYKhQkMes"  # Google Sheets Spreadsheet ID

# Authenticate and connect to Google Sheets
def connect_to_google_sheets():
    try:
        # Print the path to credentials.json for debugging
        print("Looking for credentials.json at:", CREDENTIALS_FILE)
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)

        today_date = datetime.datetime.now().strftime('%Y-%m-%d')
        daily_log_sheet = f"Daily Logs {today_date}"
        
        sheet_titles = [sheet.title for sheet in spreadsheet.worksheets()]
        if daily_log_sheet not in sheet_titles:
            spreadsheet.add_worksheet(title=daily_log_sheet, rows="200", cols="11")  # Added 11th column
            sheet2 = spreadsheet.worksheet(daily_log_sheet)
            # Updated column names for clarity
            sheet2.append_row([
                "Employee Name", 
                "Login Times", 
                "Logout Times", 
                "Overtime (hh:mm)", 
                "Break Start Time", 
                "Break End Time", 
                "Break Duration (hh:mm)", 
                "Total Break Time (hh:mm)",
                "Total Time Worked (hh:mm)",  # New column for total time worked
                "Incomplete Work"  # New column for incomplete work
            ])
            
            # Add a drop-down menu for Employee Names
            employee_names = get_employee_names(spreadsheet.worksheet("Registered Employees"))
            add_dropdown_menu(sheet2, employee_names)
        else:
            sheet2 = spreadsheet.worksheet(daily_log_sheet)

        return spreadsheet.worksheet("Registered Employees"), sheet2
    except Exception as e:
        messagebox.showerror("Error", f"Failed to connect to Google Sheets: {e}")
        exit()

# Rest of the code remains the same...
# Function to get employee names from the "Registered Employees" sheet
def get_employee_names(sheet):
    try:
        employees = sheet.get_all_values()
        return [row[0] for row in employees[1:]]  # Skip the header row
    except Exception as e:
        messagebox.showerror("Error", f"Failed to fetch employee names: {e}")
        return []

# Function to add a drop-down menu for Employee Names
def add_dropdown_menu(sheet, employee_names):
    try:
        # Define the range for the drop-down menu (e.g., column A starting from row 2)
        start_row = 2
        end_row = 100  # Adjust as needed
        range_start = f"A{start_row}"
        range_end = f"A{end_row}"
        
        # Create the data validation rule
        rule = {
            "condition": {
                "type": "ONE_OF_LIST",
                "values": [{"userEnteredValue": name} for name in employee_names]
            },
            "inputMessage": "Select an employee",
            "strict": True
        }
        
        # Apply the data validation rule to the range
        sheet.add_data_validation(range_start, range_end, rule)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to add drop-down menu: {e}")

# Function to display login screen
def show_login_screen(sheet1):
    root = tk.Tk()
    root.title("Employee Monitor - Login")
    root.geometry("400x300")
    root.configure(bg="#ffffff")
    root.resizable(False, False)
    
    frame = ttk.Frame(root, padding=20)
    frame.pack(expand=True, fill=tk.BOTH)
    
    ttk.Label(frame, text="Employee Login", font=("Arial", 14, "bold")).pack(pady=10)
    
    ttk.Label(frame, text="Enter Username:").pack(anchor="w")
    username_entry = ttk.Entry(frame)
    username_entry.pack(pady=5, fill=tk.X)
    
    ttk.Label(frame, text="Enter Password:").pack(anchor="w")
    password_entry = ttk.Entry(frame, show="*")
    password_entry.pack(pady=5, fill=tk.X)
    
    def login():
        employees = sheet1.get_all_values()
        registered_users = {row[0]: row[1] for row in employees[1:]}
        user_name = username_entry.get().strip()
        password = password_entry.get().strip()
        
        if user_name in registered_users and registered_users[user_name] == password:
            login_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Check if the employee already has a login entry for today
            records = sheet2.get_all_values()
            row_index = None
            for i, row in enumerate(records):
                if row[0] == user_name:
                    row_index = i + 1  # Rows are 1-indexed in Google Sheets
                    break

            if row_index:
                # Append the new login time to the existing list
                login_times = sheet2.cell(row_index, 2).value
                if login_times:
                    login_times = login_times.split(", ")  # Split existing times into a list
                    login_times.append(login_time)  # Append new login time
                    login_times = ", ".join(login_times)  # Join back into a string
                else:
                    login_times = login_time  # If no previous login times, start a new list
                sheet2.update_cell(row_index, 2, login_times)  # Update the Login Times column
            else:
                # Append a new row with the login time
                sheet2.append_row([user_name, login_time, "", "", "", "", "", "", "", ""])

            messagebox.showinfo("Welcome", f"Logged in as {user_name}")
            root.destroy()
            track_employee_time(sheet2, user_name)
        else:
            messagebox.showerror("Error", "Invalid credentials.")
    
    def register():
        user_name = username_entry.get().strip()
        password = password_entry.get().strip()
        
        if not user_name or not password:
            messagebox.showerror("Error", "Username and Password cannot be empty.")
            return
        
        employees = sheet1.get_all_values()
        registered_users = {row[0] for row in employees[1:]}
        
        if user_name in registered_users:
            messagebox.showerror("Error", "Username already exists. Choose a different one.")
        else:
            sheet1.append_row([user_name, password])
            messagebox.showinfo("Success", "Registration successful! You can now log in.")
    
    ttk.Button(frame, text="Login", command=login).pack(pady=10, fill=tk.X)
    ttk.Button(frame, text="Register", command=register).pack(pady=5, fill=tk.X)
    root.mainloop()

# Function to track login/logout and breaks
def track_employee_time(sheet2, user_name):
    root = tk.Tk()
    root.title("Employee Monitor - Tracking")
    root.geometry("500x400")
    root.configure(bg="#ffffff")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=20)
    frame.pack(expand=True, fill=tk.BOTH)

    ttk.Label(frame, text=f"Employee: {user_name}", font=("Arial", 14, "bold")).pack(pady=10)

    login_time = datetime.datetime.now()
    tracking = True
    break_time = 0
    break_active = False
    break_start_time = None
    break_window = None  

    timer_label = ttk.Label(frame, text="Time Worked: 0h 0m", font=("Arial", 12))
    timer_label.pack(pady=10)

    def format_time(total_minutes):
        """Convert minutes to HH:MM format"""
        hours = int(total_minutes // 60)
        mins = int(total_minutes % 60)
        return f"{hours:02d}:{mins:02d}"

    def update_timer():
        if tracking and not break_active:
            elapsed_time = datetime.datetime.now() - login_time
            timer_label.config(text=f"Time Worked: {str(elapsed_time).split('.')[0]}")
        root.after(1000, update_timer)
    update_timer()

    def start_break():
        nonlocal break_active, break_start_time, break_window
        if not break_active:
            break_active = True
            break_start_time = datetime.datetime.now()

            # Update the Google Sheet with the break start time
            try:
                # Find the row corresponding to the current employee
                records = sheet2.get_all_values()
                row_index = None
                for i, row in enumerate(records):
                    if row[0] == user_name:
                        row_index = i + 1  # Rows are 1-indexed in Google Sheets
                        break

                if row_index:
                    # Update the Break Start Time column
                    sheet2.update_cell(row_index, 5, break_start_time.strftime('%Y-%m-%d %H:%M:%S'))
                    messagebox.showinfo("Break", "Break started. Time is being recorded.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update Google Sheet: {e}")

            break_window = tk.Toplevel(root)
            break_window.title("Break Timer")
            break_window.geometry("300x150")
            break_window.configure(bg="lightyellow")

            ttk.Label(break_window, text="Break Timer", font=("Arial", 14, "bold")).pack(pady=10)
            break_timer_label = ttk.Label(break_window, text="Time Elapsed: 0s", font=("Arial", 12))
            break_timer_label.pack(pady=10)

            def update_break_timer():
                if break_active:
                    elapsed_break_time = datetime.datetime.now() - break_start_time
                    break_timer_label.config(text=f"Time Elapsed: {str(elapsed_break_time).split('.')[0]}")
                    break_window.after(1000, update_break_timer)

            update_break_timer()
            ttk.Button(break_window, text="End Break", command=end_break).pack(pady=10)

    def end_break():
        nonlocal break_active, break_time, break_start_time, break_window
        if break_active:
            break_active = False
            break_end_time = datetime.datetime.now()
            break_duration = round((break_end_time - break_start_time).total_seconds() / 60, 2)
            break_time += break_duration

            # Update the Google Sheet with the break end time, break duration, and total break time
            try:
                # Find the row corresponding to the current employee
                records = sheet2.get_all_values()
                row_index = None
                for i, row in enumerate(records):
                    if row[0] == user_name:
                        row_index = i + 1  # Rows are 1-indexed in Google Sheets
                        break

                if row_index:
                    # Update the Break End Time, Break Duration, and Total Break Time columns
                    sheet2.update_cell(row_index, 6, break_end_time.strftime('%Y-%m-%d %H:%M:%S'))  # Break End Time
                    sheet2.update_cell(row_index, 7, format_time(break_duration))                   # Break Duration
                    sheet2.update_cell(row_index, 8, format_time(break_time))                      # Total Break Time

                    # Color coding for break duration
                    if break_duration > 45:
                        sheet2.format(f"G{row_index}", {"backgroundColor": {"red": 1, "green": 0, "blue": 0}})  # Red
                    else:
                        sheet2.format(f"G{row_index}", {"backgroundColor": {"red": 0, "green": 1, "blue": 0}})  # Green

                    messagebox.showinfo("Break", f"Break ended. Total Break Time: {format_time(break_time)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update Google Sheet: {e}")

            if break_window:
                break_window.destroy()
                break_window = None

    def logout():
        nonlocal tracking
        tracking = False
        logout_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            # Find the row corresponding to the current employee
            records = sheet2.get_all_values()
            row_index = None
            for i, row in enumerate(records):
                if row[0] == user_name:
                    row_index = i + 1  # Rows are 1-indexed in Google Sheets
                    break

            if row_index:
                # Append the new logout time to the existing list
                logout_times = sheet2.cell(row_index, 3).value
                if logout_times:
                    logout_times = logout_times.split(", ")  # Split existing times into a list
                    logout_times.append(logout_time)  # Append new logout time
                    logout_times = ", ".join(logout_times)  # Join back into a string
                else:
                    logout_times = logout_time  # If no previous logout times, start a new list
                sheet2.update_cell(row_index, 3, logout_times)  # Update the Logout Times column

                # Calculate total time worked for the day
                login_times = sheet2.cell(row_index, 2).value
                if login_times:
                    login_times = login_times.split(", ")
                    logout_times = logout_times.split(", ")
                    total_time_worked = 0

                    for login_str, logout_str in zip(login_times, logout_times):
                        login_time = datetime.datetime.strptime(login_str, '%Y-%m-%d %H:%M:%S')
                        logout_time = datetime.datetime.strptime(logout_str, '%Y-%m-%d %H:%M:%S')
                        total_time_worked += (logout_time - login_time).total_seconds() / 60  # In minutes

                    total_time_worked -= break_time  # Subtract break time
                    sheet2.update_cell(row_index, 9, format_time(total_time_worked))  # Update Total Time Worked

                    # Color coding for logout time
                    if total_time_worked < 540:  # 9 hours = 540 minutes
                        sheet2.format(f"C{row_index}", {"backgroundColor": {"red": 1, "green": 0, "blue": 0}})  # Red
                        sheet2.update_cell(row_index, 10, "Incomplete Work")  # New column for incomplete work
                    else:
                        sheet2.format(f"C{row_index}", {"backgroundColor": {"red": 0, "green": 1, "blue": 0}})  # Green

                messagebox.showinfo("Logout", f"Logged out successfully! Total Time Worked: {format_time(total_time_worked)}")
                root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Error updating Google Sheet: {e}")

    ttk.Button(frame, text="Start Break", command=start_break).pack(pady=5, fill=tk.X)
    ttk.Button(frame, text="End Break", command=end_break).pack(pady=5, fill=tk.X)
    ttk.Button(frame, text="Logout", command=logout).pack(pady=10, fill=tk.X)
    root.mainloop()

if __name__ == "__main__":
    sheet1, sheet2 = connect_to_google_sheets()
