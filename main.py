from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google import genai
from notion_client import Client as NotionClient
import os
from pydantic import BaseModel
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6 import QtCore, QtWidgets, QtGui
import sys

LIGHT_MODE_KEY = "light_mode"
GEMINI_KEY = "gemini_key"
GOOGLE_AUTH = "google_auth"
NOTION_TOKEN = "notion_token"

# "https://www.notion.so/Ultimate-Tasks-Manager-bfbf17347efa413c9ea5ec315b28145a?pvs=4"

# Qt decides where to store the settings based on the OS
settings = QtCore.QSettings("Yash", "AICalendar")

if settings.value(GEMINI_KEY, "", type=str):
    gemini_client = genai.Client(api_key=settings.value(GEMINI_KEY, "", type=str))
else:
    gemini_client = None

# Check if notion key is stored, if so create a notion client
if settings.value(NOTION_TOKEN, "", type=str):
    notion_client = NotionClient(auth=settings.value(NOTION_TOKEN, "", type=str))
else:
    notion_client = None

# class Event(BaseModel):
#     title: str
#     time_to_complete: str
#     time_start: str
#     time_end: str
#     day: int
#     month: int

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

        mode_label = QtWidgets.QLabel("Select Theme:")
        layout.addWidget(mode_label)
        
        self.light_mode_radio = QtWidgets.QRadioButton("Light Mode")
        self.light_mode_radio.setChecked(light_mode)
        layout.addWidget(self.light_mode_radio)
        
        self.dark_mode_radio = QtWidgets.QRadioButton("Dark Mode")
        self.dark_mode_radio.setChecked(not light_mode)
        layout.addWidget(self.dark_mode_radio)
        
        self.gemini_key_input = PlainTextEdit(self)
        
        # Check if Gemini key is stored
        if settings.value(GEMINI_KEY, "", type=str):
            self.gemini_key_input.setPlainText(settings.value(GEMINI_KEY, "", type=str))
        elif settings.value(GEMINI_KEY, "", type=str) == "":
            self.gemini_key_input.setPlaceholderText("Enter Gemini key here...")
                        
        layout.addWidget(self.gemini_key_input)

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

        layout.addWidget(self.google_auth)
        layout.addWidget(self.google_auth_label)

        self.google_auth_file = settings.value(GOOGLE_AUTH, "", type=str)
        
        if self.google_auth_file:
            self.google_auth_label.setText(f"Google Auth File: {self.google_auth_file}")
    

        # Save button
        save_button = QtWidgets.QPushButton("Save")
        save_button.clicked.connect(self.apply_settings)
        layout.addWidget(save_button)

        apply_initial_theme(self, light_mode)

    # Applies Settings
    def apply_settings(self):
        """Apply the selected settings."""
        if self.light_mode_radio.isChecked():
            self.setStyleSheet("")  # Light mode (default)
            self.main_widget.setStyleSheet("")  # Light mode for main widget
            settings.setValue(LIGHT_MODE_KEY, True)  # Save preference
        elif self.dark_mode_radio.isChecked():
            dark_style = "background-color: #2e2e2e; color: white;"
            self.setStyleSheet(dark_style)  # Dark mode for settings window
            self.main_widget.setStyleSheet(dark_style)  # Dark mode for main widget
            settings.setValue(LIGHT_MODE_KEY, False)  # Save preference
        
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
        
    # Select Google Auth File
    def select_google_auth(self):
        """Open file dialog to select a .tex file."""
        file_filter = "Json file (*.json)"
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Google Auth File", "", file_filter)
        if file_path:
            self.google_auth_file = file_path
            self.google_auth_label.setText(f"Google Auth File: {file_path}")

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
def update_gemini_api_key():
    gemini_key = settings.value(GEMINI_KEY, "", type=str)
    if gemini_key:
        gemini_client = genai.Client(api_key=gemini_key)
    else:
        gemini_client = None


# Update the API key for Notion
def notion_key():
    notion_key = settings.value(GEMINI_KEY, "", type=str)
    if notion_key:
        notion_client = NotionClient(auth=settings.value(NOTION_TOKEN, "", type=str))
    else:
        notion_client = None

def resource_path(relative_path):
    """Get the absolute path to the resource, works for development and PyInstaller builds."""
    if getattr(sys, '_MEIPASS', None):  # Check if running from PyInstaller
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

def get_tasks():
    # Get all tasks that are not done and are schedulable
    database_id = "6728f8a2330a4092860d6d358a4c33f3"

    my_page = notion_client.databases.query(
        **{
            "database_id": database_id,
            "filter": {
                "and": [
                    {
                        "property": "Done",
                        "checkbox": {
                            "equals": False,
                        },
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

    # print(tasks)
    return tasks

# currently just prints out the upcoming events in the next week and the calendars that are available
def get_busy_times():
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

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

    try:
        service = build("calendar", "v3", credentials=creds)
        
        now = datetime.now().isoformat() + "-05:00" #* EST
        # print(now)
        # print("Getting upcoming events in the next week")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=f"{year()}-{month()}-{day()+7}T23:59:59Z",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        busy_times = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            # print(start, end, event["summary"])

            busy_times.append([start, end])
        # print(busy_times)
        return busy_times


            #*prevoius formatting
            # start_obj = datetime.fromisoformat(start)
            # formatted_start = start_obj.strftime("%H%M")
            # # print(f"Formatted start: {formatted_start}")

            # end_obj = datetime.fromisoformat(end)
            # formatted_end = end_obj.strftime("%H%M")
            # # print(f"Formatted end: {formatted_end}")
            # busy_times.append([start_obj.month, start_obj.day, formatted_start, formatted_end])

        # for v in service.calendarList().list().execute()['items']:
        #     print(f"{v['summary']}")

        # Call the Calendar API
        # now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time

        # events_result = (
        #     service.events()
        #     .list(
        #         calendarId="primary",
        #         timeMin=now,
        #         maxResults=10,
        #         singleEvents=True,
        #         orderBy="startTime",
        #     )
        #     .execute()
        # )
        # events = events_result.get("items", [])

        # if not events:
        #     print("No upcoming events found.")

        # # Prints the start and name of the next 10 events
        # for event in events:
        #     start = event["start"].get("dateTime", event["start"].get("date"))
        #     print(start, event["summary"])
    except HttpError as error:
        print(f"An error occurred: {error}")

def schedule_tasks(response):
    tasks_json = response
    print(response.text)
    

# takes in a list of lists containing the task and its priority and generates a response using Gemini
def generate_response(tasks, busy_times):
    task_list = ""
    for task in tasks:
        task_list += f"{task[0]}, Priority: {task[1]}\n"

    busy_time_list = ""
    for busy_time in busy_times:
        busy_time_list += f"dateTime start: {busy_time[0]}, dateTime end: {busy_time[1]}\n"

    # print(busy_time_list)

    prompt = f"""You are a bot that takes information about any given task and its priority, 
    you will predict the time it will take to complete the task and list the start and end time in the a day.
    The current date is {month()}/{day()}/{year()}.
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

def day():
    return datetime.now().day

def month():
    return datetime.now().month

def year():
    return datetime.now().year

# Entry point for the application
if __name__ == "__main__":
    schedule_tasks(generate_response(get_tasks(), get_busy_times()))


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
