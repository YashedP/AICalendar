import copy
import re
from PySide6 import QtCore, QtWidgets
from datetime import datetime, time

import config
import utils

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
        
        light_mode = config.settings.value(config.LIGHT_MODE_KEY, True, type=bool)
        
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
        
        self.times = copy.deepcopy(config.work_hours)
        
        for i in range(len(self.times)):
            self.times[i][0] = self.times[i][0].strftime("%I:%M %p").lstrip("0")
            self.times[i][1] = self.times[i][1].strftime("%I:%M %p").lstrip("0")

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
        if config.settings.value(config.GEMINI_KEY, "", type=str):
            self.gemini_key_input.setPlainText(config.settings.value(config.GEMINI_KEY, "", type=str))
        elif config.settings.value(config.GEMINI_KEY, "", type=str) == "":
            self.gemini_key_input.setPlaceholderText("Enter Gemini key here...")
                        
        layout.addWidget(self.gemini_key_input)

        self.notion_label = QtWidgets.QLabel("Notion API Key:")
        layout.addWidget(self.notion_label)

        self.notion_token_input = PlainTextEdit(self)

        # Check if Notion token is stored
        if config.settings.value(config.NOTION_TOKEN, "", type=str):
            self.notion_token_input.setPlainText(config.settings.value(config.NOTION_TOKEN, "", type=str))
        elif config.settings.value(config.NOTION_TOKEN, "", type=str) == "":
            self.notion_token_input.setPlaceholderText("Enter Notion token here...")
                        
        layout.addWidget(self.notion_token_input)

        self.google_auth = QtWidgets.QPushButton("Select Google Auth File")
        self.google_auth.clicked.connect(self.select_google_auth)
        self.google_auth_label = QtWidgets.QLabel("No file Selected")

        layout.addWidget(self.google_auth_label)
        layout.addWidget(self.google_auth)

        self.google_auth_file = config.settings.value(config.GOOGLE_AUTH, "", type=str)
        
        if self.google_auth_file:
            self.google_auth_label.setText(f"Google Auth File: {self.google_auth_file}")
    
        # Save button
        save_button = QtWidgets.QPushButton("Save")
        save_button.clicked.connect(self.apply_settings)
        layout.addWidget(save_button)

        utils.apply_initial_theme(self, light_mode)

    # Select Google Auth File
    @QtCore.Slot()
    def select_google_auth(self):
        """Open file dialog to select a .tex file."""
        file_filter = "Json file (*.json)"
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Google Auth File", "", file_filter)
        if file_path:
            self.google_auth_file = file_path
            self.google_auth_label.setText(f"Google Auth File: {file_path}")

    @QtCore.Slot()
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
    @QtCore.Slot()
    def apply_settings(self):        
        """Apply the selected settings."""
        times = []
        for i in range(len(self.days)):
            lower = datetime.strptime(self.grid_time_layout.itemAtPosition(i + 1, 1).widget().text(), "%I:%M %p").time()
            upper = datetime.strptime(self.grid_time_layout.itemAtPosition(i + 1, 2).widget().text(), "%I:%M %p").time()

            # Checks if the upper time is before the lower time
            if upper < lower:
                QtWidgets.QMessageBox.critical(self, "Error", "You cannot have the end time occur before the start time!", QtWidgets.QMessageBox.Ok)
                return

            times += [[lower.isoformat(), upper.isoformat()]]

        if self.light_mode_radio.isChecked():
            self.setStyleSheet("")  # Light mode (default)
            self.main_widget.setStyleSheet("")  # Light mode for main widget
            config.settings.setValue(config.LIGHT_MODE_KEY, True)  # Save preference
        elif self.dark_mode_radio.isChecked():
            dark_style = "background-color: #2e2e2e; color: white;"
            self.setStyleSheet(dark_style)  # Dark mode for settings window
            self.main_widget.setStyleSheet(dark_style)  # Dark mode for main widget
            config.settings.setValue(config.LIGHT_MODE_KEY, False)  # Save preference

        config.settings.setValue(config.WORK_HOURS, times)
        for hours in times:
            hours[0] = time.fromisoformat(hours[0])
            hours[1] = time.fromisoformat(hours[1])

        config.work_hours = times

        if self.gemini_key_input:
            config.settings.setValue(config.GEMINI_KEY, self.gemini_key_input.toPlainText())
            utils.update_gemini_api_key()

        if self.notion_token_input:
            config.settings.setValue(config.NOTION_TOKEN, self.notion_token_input.toPlainText())
            utils.notion_key()

        if self.google_auth_file:
            config.settings.setValue(config.GOOGLE_AUTH, self.google_auth_label.text().split(": ")[1])
        
        # Set Gemini API key
        utils.update_gemini_api_key()
