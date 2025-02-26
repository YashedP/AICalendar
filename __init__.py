import sys

from PySide6 import QtGui, QtWidgets

from trayApp import TrayApp
from utils import resource_path

# Entry point for the application
if __name__ == "__main__":
    # Create the application
    app = QtWidgets.QApplication(sys.argv)

    # Set the icon of the application to the calendar icon
    icon = QtGui.QIcon(resource_path("Images/AICalendar.png"))
    app.setWindowIcon(icon)
    
    # Create the tray application and the GUI can be accessed from the tray application
    tray_app = TrayApp()
    tray_app.setToolTip("AICalendar")
    tray_app.show()

    sys.exit(app.exec())
