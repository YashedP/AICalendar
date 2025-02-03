import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from notion_client import Client as NotionClient
from openai import OpenAI
import os
from pydantic import BaseModel
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6 import QtCore, QtWidgets, QtGui
import sys

LIGHT_MODE_KEY = "light_mode"   
CHATGPT_KEY = "chatgpt_key"
GOOGLE_AUTH = "google_auth"
NOTION_TOKEN = "notion_token"

# "https://www.notion.so/Ultimate-Tasks-Manager-bfbf17347efa413c9ea5ec315b28145a?pvs=4"

settings = QtCore.QSettings("Yash", "AICalendar")

chatgpt_client = OpenAI(api_key=settings.value(CHATGPT_KEY, "", type=str))

notion_key = settings.value(NOTION_TOKEN, "", type=str)
if notion_key:
    notion_client = NotionClient(auth=notion_key)
else:
    notion_client = None

#TODO: Create an event and have it be returned from ChatGPT and then posted into google calendar
class Event(BaseModel):
    title: str
    date: str
    time: str
    description: str

class PlainTextEdit(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

class SettingsWindow(QtWidgets.QWidget):
    def __init__(self, main_widget):
        super().__init__()
        self.main_widget = main_widget
        self.setWindowTitle("Settings")
        self.resize(400, 300)
        
        self.settings = settings
        light_mode = settings.value(LIGHT_MODE_KEY, True, type=bool)
        
        layout = QtWidgets.QVBoxLayout(self)

        mode_label = QtWidgets.QLabel("Select Theme:")
        layout.addWidget(mode_label)
        
        # Layout for settings window
        self.light_mode_radio = QtWidgets.QRadioButton("Light Mode")
        self.light_mode_radio.setChecked(light_mode)
        layout.addWidget(self.light_mode_radio)
        
        self.dark_mode_radio = QtWidgets.QRadioButton("Dark Mode")
        self.dark_mode_radio.setChecked(not light_mode)
        layout.addWidget(self.dark_mode_radio)
        
        self.chatgpt_key_input = PlainTextEdit(self)
        
        # Check if ChatGPT key is stored
        if settings.value(CHATGPT_KEY, "", type=str):
            self.chatgpt_key_input.setPlainText(settings.value(CHATGPT_KEY, "", type=str))
        elif settings.value(CHATGPT_KEY, "", type=str) == "":
            self.chatgpt_key_input.setPlaceholderText("Enter ChatGPT key here...")
                        
        layout.addWidget(self.chatgpt_key_input)

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
        
        if self.chatgpt_key_input:
            settings.setValue(CHATGPT_KEY, self.chatgpt_key_input.toPlainText())
            update_api_key()

        if self.notion_token_input:
            settings.setValue(NOTION_TOKEN, self.notion_token_input.toPlainText())
            notion_key()

        if self.google_auth_file:
            settings.setValue(GOOGLE_AUTH, self.google_auth_label.text().split(": ")[1])
        
        # Set OpenAI API key
        update_api_key()
        
    def select_google_auth(self):
        """Open file dialog to select a .tex file."""
        file_filter = "Json file (*.json)"
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Google Auth File", "", file_filter)
        if file_path:
            self.google_auth_file = file_path
            self.google_auth_label.setText(f"Google Auth File: {file_path}")

# Main application class
class TrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setIcon(QtGui.QIcon(resource_path("AICalendar.png")))
        # Create the menu
        menu = QtWidgets.QMenu()

        # Add "Open" option
        open_action = menu.addAction("Open")
        open_action.triggered.connect(self.show_window)

        regenerate_day = menu.addAction("Regenerate Day")
        regenerate_day.triggered.connect(self.regenerate_day)

        # Add "Exit" option
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_app)

        self.setContextMenu(menu)

        # Create the main window
        self.window = MainWindow()

    def show_window(self):
        self.window.show()

    def exit_app(self):
        QtWidgets.QApplication.quit()
        
    def regenerate_day(self):
        print("Regenerating Day...")

# Main window class
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        #Load Settings
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

    @QtCore.Slot()
    def open_settings(self):
        """Open a new settings window."""
        self.settings_window = SettingsWindow(self)  # Pass main widget to settings
        self.settings_window.show()

    def fetch_and_schedule(self):
        print("Tasks fetched and scheduled!")
        
    def closeEvent(self, event):
        event.ignore()
        self.hide()

def apply_initial_theme(QWindow, light_mode):
    """Apply the initial theme based on the light mode preference."""
    if not light_mode:
        dark_style = "background-color: #2e2e2e; color: white;"
        QWindow.setStyleSheet(dark_style)  # Dark mode for settings window

def update_api_key():
    chatgpt_client.api_key = settings.value(CHATGPT_KEY, "", type=str)

def notion_key():
    notion_client = NotionClient(auth=settings.value(NOTION_TOKEN, "", type=str))

def resource_path(relative_path):
    """Get the absolute path to the resource, works for development and PyInstaller builds."""
    if getattr(sys, '_MEIPASS', None):  # Check if running from PyInstaller
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

def notion():
    my_page = notion_client.databases.query(
        **{
            "database_id": "6728f8a2330a4092860d6d358a4c33f3",
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

    tasks = []
    for i in range(len(results)):
        title = results[i]['properties']['Title']['title'][0]['plain_text']
        priority = results[i]['properties']['Priority']['select']
        if priority == None:
            priority = "0"
        else:
            priority = priority['name']
            
        tasks.append([title, priority])

    # Sort tasks by priority in descending order
    tasks.sort(key=lambda x: x[1], reverse=True)

    print(tasks)

def google_calendar():
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
        
        for v in service.calendarList().list().execute()['items']:
            print(f"{v['summary']}")

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
    

# Entry point for the application
if __name__ == "__main__":
    notion()
    google_calendar()

    app = QtWidgets.QApplication(sys.argv)
    icon = QtGui.QIcon(resource_path("AICalendar.png"))
    app.setWindowIcon(icon)
    
    tray_app = TrayApp()
    tray_app.setToolTip("AICalendar")
    tray_app.show()

    sys.exit(app.exec())
