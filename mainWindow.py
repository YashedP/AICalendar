from PySide6 import QtCore, QtWidgets

import config
import utils
from settingsWindow import SettingsWindow

# Main window class
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Load Settings
        self.settings = config.settings
        light_mode = config.settings.value(config.LIGHT_MODE_KEY, True, type=bool)
        
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

        utils.apply_initial_theme(self, light_mode)

    # Open the settings window
    @QtCore.Slot()
    def open_settings(self):
        """Open a new settings window."""
        self.settings_window = SettingsWindow(self)  # Pass main widget to settings
        self.settings_window.show()

    # Retrieve tasks from the database and schedule them
    @QtCore.Slot()
    def fetch_and_schedule(self):
        print("Tasks fetched and scheduled!")

    def closeEvent(self, event):
        event.ignore()  # Ignore the close event to prevent closing the window
        self.hide()  # Hide the window instead