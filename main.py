import copy
from datetime import datetime, time, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google import genai
from notion_client import Client as NotionClient
import os
from pydantic import BaseModel
from PySide6 import QtCore, QtWidgets, QtGui
import re
import sys

import tzlocal

LIGHT_MODE_KEY = "light_mode"
GEMINI_KEY = "gemini_key"
GOOGLE_AUTH = "google_auth"
NOTION_TOKEN = "notion_token"

# "https://www.notion.so/Ultimate-Tasks-Manager-bfbf17347efa413c9ea5ec315b28145a?pvs=4"

# Qt decides where to store the settings based on the OS
settings = QtCore.QSettings("Yash", "AICalendar")

# Check if gemini key is stored, if so create a gemini client
if settings.value(GEMINI_KEY, "", type=str):
    gemini_client = genai.Client(api_key=settings.value(GEMINI_KEY, "", type=str))
else:
    gemini_client = None

# Check if notion key is stored, if so create a notion client
if settings.value(NOTION_TOKEN, "", type=str):
    notion_client = NotionClient(auth=settings.value(NOTION_TOKEN, "", type=str))
else:
    notion_client = None

work_hours = settings.value("work_hours", [[time(7, 0, 0).isoformat(), time(22, 0, 0).isoformat()]] * 7, type=list)

for hours in work_hours:
    hours[0] = time.fromisoformat(hours[0])
    hours[1] = time.fromisoformat(hours[1])

class Event(BaseModel):
    title: str
    start: str
    end: str

# Overwrites the default text formatting so that the text is not formatted when pasted
class PlainTextEdit(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

# Settings window class
class SettingsWindow(QtWidgets.QWidget):
    def __init__(self, main_widget):
        super().__init__()
        self.main_widget = main_widget
        self.setWindowTitle("Settings")
        self.resize(400, 300)
        
        # Load settings
        self.settings = settings
        light_mode = settings.value(LIGHT_MODE_KEY, True, type=bool)
        
        # Layout for settings window
        layout = QtWidgets.QVBoxLayout(self)

        self.mode_label = QtWidgets.QLabel("Select Theme:")
        layout.addWidget(self.mode_label)
        
        self.light_mode_radio = QtWidgets.QRadioButton("Light Mode")
        self.light_mode_radio.setChecked(light_mode)
        layout.addWidget(self.light_mode_radio)
        
        self.dark_mode_radio = QtWidgets.QRadioButton("Dark Mode")
        self.dark_mode_radio.setChecked(not light_mode)
        layout.addWidget(self.dark_mode_radio)
        
        self.gemini_key_input = PlainTextEdit(self)
        
        self.times = copy.deepcopy(work_hours)

        for i in range(len(self.times)):
            self.times[i][0] = self.times[i][0].strftime("%I:%M %p").lstrip("0")
            self.times[i][1] = self.times[i][1].strftime("%I:%M %p").lstrip("0")
            print(self.times[i][0])

        self.prev_time = copy.deepcopy(self.times)

        # Times for autocompletion
        times = [f"{h}:00 AM" for h in range(1, 12)] + ["12:00 PM"]
        times += [f"{h}:15 AM" for h in range(1, 12)] + ["12:15 PM"]
        times += [f"{h}:30 AM" for h in range(1, 12)] + ["12:30 PM"]
        times += [f"{h}:45 AM" for h in range(1, 12)] + ["12:45 PM"]

        times += [f"{h}:00 PM" for h in range(1, 12)]
        times += [f"{h}:15 PM" for h in range(1, 12)]
        times += [f"{h}:30 PM" for h in range(1, 12)]
        times += [f"{h}:45 PM" for h in range(1, 12)]

        self.completer = QtWidgets.QCompleter(times)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)

        self.grid_time_layout = QtWidgets.QGridLayout()

        self.grid_time_layout.addWidget(QtWidgets.QLabel("Day"), 0, 0)
        self.grid_time_layout.addWidget(QtWidgets.QLabel("Start Time"), 0, 1)
        self.grid_time_layout.addWidget(QtWidgets.QLabel("End Time"), 0, 2)

        self.days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        for i in range(len(self.times)):
            label = QtWidgets.QLabel(self.days[i])

            lower_bound_input = QtWidgets.QLineEdit()
            lower_bound_input.setText(self.times[i][0])
            lower_bound_input.setCompleter(self.completer)
            lower_bound_input.editingFinished.connect(lambda i=i: self.format_time(i, "lower"))

            upper_bound_input = QtWidgets.QLineEdit()
            upper_bound_input.setText(self.times[i][1])
            upper_bound_input.setCompleter(self.completer)
            upper_bound_input.editingFinished.connect(lambda i=i: self.format_time(i, "upper"))

            self.grid_time_layout.addWidget(label, i + 1, 0)
            self.grid_time_layout.addWidget(lower_bound_input, i + 1, 1)
            self.grid_time_layout.addWidget(upper_bound_input, i + 1, 2)

        layout.addLayout(self.grid_time_layout)

        self.gemini_label = QtWidgets.QLabel("Gemini API Key:")
        layout.addWidget(self.gemini_label)

        # Check if Gemini key is stored
        if settings.value(GEMINI_KEY, "", type=str):
            self.gemini_key_input.setPlainText(settings.value(GEMINI_KEY, "", type=str))
        elif settings.value(GEMINI_KEY, "", type=str) == "":
            self.gemini_key_input.setPlaceholderText("Enter Gemini key here...")
                        
        layout.addWidget(self.gemini_key_input)

        self.notion_label = QtWidgets.QLabel("Notion API Key:")
        layout.addWidget(self.notion_label)

        self.notion_token_input = PlainTextEdit(self)

        # Check if Notion token is stored
        if settings.value(NOTION_TOKEN, "", type=str):
            self.notion_token_input.setPlainText(settings.value(NOTION_TOKEN, "", type=str))
        elif settings.value(NOTION_TOKEN, "", type=str) == "":
            self.notion_token_input.setPlaceholderText("Enter Notion token here...")
                        
        layout.addWidget(self.notion_token_input)

        self.google_auth = QtWidgets.QPushButton("Select Google Auth File")
        self.google_auth.clicked.connect(self.select_google_auth)
        self.google_auth_label = QtWidgets.QLabel("No file Selected")

        layout.addWidget(self.google_auth_label)
        layout.addWidget(self.google_auth)

        self.google_auth_file = settings.value(GOOGLE_AUTH, "", type=str)
        
        if self.google_auth_file:
            self.google_auth_label.setText(f"Google Auth File: {self.google_auth_file}")
    
        # Save button
        save_button = QtWidgets.QPushButton("Save")
        save_button.clicked.connect(self.apply_settings)
        layout.addWidget(save_button)

        apply_initial_theme(self, light_mode)

    # Select Google Auth File
    def select_google_auth(self):
        """Open file dialog to select a .tex file."""
        file_filter = "Json file (*.json)"
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Google Auth File", "", file_filter)
        if file_path:
            self.google_auth_file = file_path
            self.google_auth_label.setText(f"Google Auth File: {file_path}")

    def format_time(self, i, bound):
        if bound == "lower":
            text_input = self.grid_time_layout.itemAtPosition(i + 1, 1).widget()
            previous_time = self.prev_time[i][0]
        else:
            text_input = self.grid_time_layout.itemAtPosition(i + 1, 2).widget()
            previous_time = self.prev_time[i][1]
        
        text = text_input.text().strip()

        # Handle "930" --> 9:30 AM
        if re.match(r"^\d{3, 4}", text):
            hour = int(text[:-2])
            minute = int(text[-2:])

            if minute >= 60:
                text_input.setText(previous_time)
                return
            if hour == 24 or hour == 0:
                formatted_time = f"12:{minute:02} AM"
            elif hour == 12: # Noon
                formatted_time = f"12:{minute:02} PM"
            elif hour > 12: # Convert 24-hour to 12-hour
                formatted_time = f"{hour - 12}:{minute:02} PM"
            else:
                formatted_time = f"{hour}:{minute:02} AM"

            text_input.setText(formatted_time)
            if bound == "lower":
                self.prev_time[i][0] = formatted_time
            else:
                self.prev_time[i][1] = formatted_time
            return
    
        # Handle cases like "9am", "14:30", "2:30 pm"
        match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
        if match:
            hour, minute, period = match.groups()
            hour, minute = int(hour), int(minute) if minute else 0

            if minute >= 60:
                text_input.setText(previous_time)
                return

            # Special Cases : 24 AM -> 12 PM, 00 AM -> 12 AM
            if hour == 24:
                hour = 12
                period = "PM"
            elif hour == 0:
                hour = 12
                period = "AM"
            
            # If no period provided, infer it
            if not period:
                if hour > 12:
                    period = "PM"
                    hour -= 12
                else:
                    period = "AM"
            
            formatted_time = f"{hour}:{minute:02} {period.upper()}"
            text_input.setText(formatted_time)
            
            if bound == "lower":
                self.prev_time[i][0] = formatted_time
            else:
                self.prev_time[i][1] = formatted_time
            return
        else:
            text_input.setText(previous_time)

    # Applies Settings
    def apply_settings(self):
        """Apply the selected settings."""
        times = []
        for i in range(len(self.days)):
            lower = time.strftime(self.grid_time_layout.itemAtPosition(i + 1, 1).widget().text(), "%I:%M %p")
            upper = time.strftime(self.grid_time_layout.itemAtPosition(i + 1, 2).widget().text(), "%I:%M %p")

            # Checks if the upper time is before the lower time
            if upper < lower:
                QtWidgets.QMessageBox.critical(self, "Error", "You cannot have the end time occur before the start time!", QtWidgets.QMessageBox.Ok)
                return

            times += [[lower.isoformat(), upper.isoformat()]]

        if self.light_mode_radio.isChecked():
            self.setStyleSheet("")  # Light mode (default)
            self.main_widget.setStyleSheet("")  # Light mode for main widget
            settings.setValue(LIGHT_MODE_KEY, True)  # Save preference
        elif self.dark_mode_radio.isChecked():
            dark_style = "background-color: #2e2e2e; color: white;"
            self.setStyleSheet(dark_style)  # Dark mode for settings window
            self.main_widget.setStyleSheet(dark_style)  # Dark mode for main widget
            settings.setValue(LIGHT_MODE_KEY, False)  # Save preference

        settings.setValue("work_hours", times)
        work_hours = times

        if self.gemini_key_input:
            settings.setValue(GEMINI_KEY, self.gemini_key_input.toPlainText())
            update_gemini_api_key()

        if self.notion_token_input:
            settings.setValue(NOTION_TOKEN, self.notion_token_input.toPlainText())
            notion_key()

        if self.google_auth_file:
            settings.setValue(GOOGLE_AUTH, self.google_auth_label.text().split(": ")[1])
        
        # Set Gemini API key
        update_gemini_api_key()

# Tray window class
class TrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Set the icon of the tray application to the calendar icon
        self.setIcon(QtGui.QIcon(resource_path("AICalendar.png")))
        
        # Create the menu
        menu = QtWidgets.QMenu()

        # Add "Open" option
        open_action = menu.addAction("Open")
        open_action.triggered.connect(self.show_window)

        # Add Regenerate Day option
        regenerate_day = menu.addAction("Regenerate Day")
        regenerate_day.triggered.connect(self.regenerate_day)

        # Add Regenerate Day option
        regenerate_3_days = menu.addAction("Regenerate 3 Days")
        regenerate_3_days.triggered.connect(self.regenerate_3_days)

        # Add Regenerate Day option
        regenerate_week = menu.addAction("Regenerate Week")
        regenerate_week.triggered.connect(self.regenerate_week)

        test = menu.addAction("Test")
        test.triggered.connect(self.test)

        # Add "Reset Settings" option
        resetSettings = menu.addAction("Reset Settings")
        resetSettings.triggered.connect(self.resetSettings)

        # Add "Exit" option
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_app)

        self.setContextMenu(menu)

        # Create the main window
        self.window = MainWindow()

    # Show the main window upon clicking "Open"
    def show_window(self):
        self.window.show()

    # Exit the application upon clicking "Exit"
    def exit_app(self):
        QtWidgets.QApplication.quit()
        
    # Regenerate the day
    def regenerate_day(self):
        print("Regenerating Day...")

    def regenerate_3_days(self):
        print("Regenerating 3 Days...")
    
    def regenerate_week(self):
        print("Regenerating Week...")
    
    def test(self):
        # schedule_tasks(generate_response(get_tasks(), get_free_times()))
        
        createAICalendar()

        for interval in get_free_times()[datetime.today().weekday()]:
            print(f"Start: {interval[0].isoformat()}, end: {interval[1].isoformat()}")
        
    def resetSettings(self):
        settings.clear()

# Main window class
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Load Settings
        self.settings = settings
        light_mode = settings.value(LIGHT_MODE_KEY, True, type=bool)
        
        # Add Settings button at the top-right corner
        self.settings_button = QtWidgets.QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        
        self.setWindowTitle("Tray App")
        self.setGeometry(100, 100, 300, 200)

        # Simple layout with a label and button
        layout = QtWidgets.QVBoxLayout()

        label = QtWidgets.QLabel("Manage Your Day")
        button = QtWidgets.QPushButton("Fetch and Schedule")
        button.clicked.connect(self.fetch_and_schedule)

        layout.addWidget(label)
        layout.addWidget(button)
        layout.addWidget(self.settings_button)

        container = QtWidgets.QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        apply_initial_theme(self, light_mode)

    # Open the settings window
    @QtCore.Slot()
    def open_settings(self):
        """Open a new settings window."""
        self.settings_window = SettingsWindow(self)  # Pass main widget to settings
        self.settings_window.show()

    # Retrieve tasks from the database and schedule them
    def fetch_and_schedule(self):
        print("Tasks fetched and scheduled!")

# Apply the initial theme based on the light mode preference, referenced by all windows
def apply_initial_theme(QWindow, light_mode):
    """Apply the initial theme based on the light mode preference."""
    if not light_mode:
        dark_style = "background-color: #2e2e2e; color: white;"
        QWindow.setStyleSheet(dark_style)  # Dark mode for settings window

# Update the API key for Gemini
def update_gemini_api_key() -> None:
    global gemini_client
    gemini_key = settings.value(GEMINI_KEY, "", type=str)
    if gemini_key:
        gemini_client = genai.Client(api_key=gemini_key)
    else:
        gemini_client = None

# Update the API key for Notion
def notion_key() -> None:
    notion_key = settings.value(GEMINI_KEY, "", type=str)
    if notion_key:
        notion_client = NotionClient(auth=settings.value(NOTION_TOKEN, "", type=str))
    else:
        notion_client = None

def resource_path(relative_path) -> str:
    """Get the absolute path to the resource, works for development and PyInstaller builds."""
    if getattr(sys, '_MEIPASS', None): # Check if running from PyInstaller
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

def get_tasks() -> list:
    # Get all tasks that are not done and are schedulable
    database_id = "6728f8a2330a4092860d6d358a4c33f3"

    my_page = notion_client.databases.query(
        **{
            "database_id": database_id,
            "filter": {
                "and": [
                    {
                        "property": "Status",
                        "status": {
                            "does_not_equal": "Done",
                        }
                    },
                    {
                        "property": "Schedulable",
                        "checkbox": {
                            "equals": True,
                        },
                    }
                ]
            }
        }
    )

    results = my_page["results"]

    # Extract the title and priority of each task
    tasks = []
    for i in range(len(results)):
        title = results[i]['properties']['Title']['title'][0]['plain_text']
        priority = results[i]['properties']['Priority']['select']
        
        # If the user has not set a priority, set it to 0
        if priority == None:
            priority = "0"
        else:
            priority = priority['name']
        
        # Append the task and its priority to the list
        tasks.append([title, priority])

    # Sort tasks by priority in descending order
    tasks.sort(key=lambda x: x[1], reverse=True)

    return tasks

def google_auth():
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    run = True
    while run == True:
        try:
            creds = None
            if os.path.exists("token.json"):
                creds = Credentials.from_authorized_user_file("token.json")
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:

                    print("string: " + settings.value(GOOGLE_AUTH, "", type=str))
                    flow = InstalledAppFlow.from_client_secrets_file(
                        settings.value(GOOGLE_AUTH, "", type=str), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            run = False
        except RefreshError as error:
            os.remove("token.json")
            print("Refresh error, token.json removed")
    return creds

# Currently just prints out the upcoming events in the next week and the calendars that are available
def get_free_times(days=1) -> list:
    days -= 1

    creds = google_auth()
    
    try:
        service = build("calendar", "v3", credentials=creds)

        now = datetime.now().astimezone().isoformat()
        
        timeMax = (datetime.today().replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days)).astimezone().isoformat()

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=timeMax,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        free_times = copy.deepcopy(work_hours)

        for i in range(len(free_times)):
            free_times[i] = [[free_times[i][0], free_times[i][1]]]
        
        # Going through each event and seeing if it within the interval, then if it is then break the interval down into 2 intervals
        for event in events:
            start = datetime.fromisoformat(event["start"].get("dateTime", event["start"].get("date")))
            end = datetime.fromisoformat(event["end"].get("dateTime", event["end"].get("date")))

            i = start.weekday()

            free_time = free_times[i]
            for (i, interval) in enumerate(free_time):
                # 1. Event ends before interval
                if end.time() <= interval[0]:
                    continue

                # 2. Event starts after interval
                elif start.time() >= interval[1]:
                    continue

                # 3. Event starts before interval and ends in the middle of the interval
                elif start.time() < interval[0] and end.time() <= interval[1]:
                    interval[1] = time(end.hour, end.minute, 0)
                    break
                
                # 4. Event starts in the middle of the interval and ends after the interval
                elif start.time() < interval[1] and end.time() >= interval[1]:
                    interval[0] = time(start.hour, start.minute, 0)
                    break
                
                # 5. Event starts in the middle of the interval and ends in the middle of the interval
                elif start.time() > interval[0] and end.time() < interval[1]:
                    new_interval = [time(end.hour, end.minute, 0), interval[1]]
                    interval[1] = time(start.hour, start.minute, 0)
                    free_time.insert(i + 1, new_interval)
                
                # 6. Event overlaps the entire interval
                else:
                    free_time.pop(i)
                

        return free_times
    except HttpError as error:
        print(f"HttpError error occurred: {error}")

def schedule_tasks(response):
    if response == None:
        return
    
    tasks_json = response
    print(response.text)
    
# takes in a list of lists containing the task and its priority and generates a response using Gemini
def generate_response(tasks, busy_times) -> Event:
    if busy_times == None or tasks == None:
        return
    
    task_list = ""
    for task in tasks:
        task_list += f"{task[0]}, Priority: {task[1]}\n"

    busy_time_list = ""
    for busy_time in busy_times:
        busy_time_list += f"dateTime start: {busy_time[0]}, dateTime end: {busy_time[1]}\n"

    day = datetime.now().day
    month = datetime.now().month
    year = datetime.now().year

    prompt = f"""You are a bot that takes information about any given task and its priority, 
    you will predict the time it will take to complete the task and list the start and end time in the a day.
    The current date is {month}/{day}/{year}.
    Here are your list of tasks to schedule:

    {task_list}

    Here are times the user is busy, you should avoid scheduling tasks during these times:

    {busy_time_list}
    """

    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[Event],
        },
    )
    return response

# Check if the user has an AI Tasks calendar and if not, create one
def createAICalendar():
    creds = google_auth()

    service = build("calendar", "v3", credentials=creds)

    AI_Tasks = False

    for calendar in service.calendarList().list().execute()['items']:
        if calendar['summary'] == "AI Tasks":
            AI_Tasks = True
    
    if AI_Tasks:
        print("AI Tasks already exists")
        return

    calendar = {
        "summary": "AI Tasks",
        "timeZone": tzlocal.get_localzone().key
    }

    service.calendars().insert(body=calendar).execute()

# Entry point for the application
if __name__ == "__main__":
    # Create the application
    app = QtWidgets.QApplication(sys.argv)
    
    # Set the icon of the application to the calendar icon
    icon = QtGui.QIcon(resource_path("AICalendar.png"))
    app.setWindowIcon(icon)
    
    # Create the tray application and the GUI can be accessed from the tray application
    tray_app = TrayApp()
    tray_app.setToolTip("AICalendar")
    tray_app.show()

    sys.exit(app.exec())
