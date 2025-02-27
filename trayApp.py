from PySide6 import QtCore, QtGui, QtWidgets

import AI
import config
import utils
from mainWindow import MainWindow

# Tray window class
class TrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Set the icon of the tray application to the calendar icon
        self.setIcon(QtGui.QIcon(utils.resource_path("Images/AICalendar.png")))
        
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

        # Add "Exit" option
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_app)

        self.setContextMenu(menu)

        # Create the main window
        self.window = MainWindow()

    # Show the main window upon clicking "Open"
    @QtCore.Slot()
    def show_window(self):
        self.window.show()

    # Regenerate the day
    @QtCore.Slot()
    def regenerate_day(self):
        AI.auto_schedule_tasks(1)

    @QtCore.Slot()
    def regenerate_3_days(self):
        AI.auto_schedule_tasks(3)
    
    @QtCore.Slot()
    def regenerate_week(self):
        AI.auto_schedule_tasks(7)
    
    @QtCore.Slot()
    def test(self):        
        AI.auto_schedule_tasks(2)

    # Exit the application upon clicking "Exit"
    @QtCore.Slot()
    def exit_app(self):
        QtWidgets.QApplication.quit()
        