import os
import sys
from google import genai
from notion_client import Client as notion_client

import config

# Apply the initial theme based on the light mode preference, referenced by all windows
def apply_initial_theme(QWindow, light_mode):
    """Apply the initial theme based on the light mode preference."""
    if not light_mode:
        dark_style = "background-color: #2e2e2e; color: white;"
        QWindow.setStyleSheet(dark_style)  # Dark mode for settings window

def resource_path(relative_path) -> str:
    """Get the absolute path to the resource, works for development and PyInstaller builds."""
    if getattr(sys, '_MEIPASS', None): # Check if running from PyInstaller
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(relative_path)

# Update the API key for Gemini
def update_gemini_api_key() -> None:
    global gemini_client

    gemini_key = config.settings.value(config.GEMINI_KEY, "", type=str)
    if gemini_key:
        gemini_client = genai.Client(api_key=gemini_key)
    else:
        gemini_client = None

# Update the API key for Notion
def notion_key() -> None:
    global notion_client

    notion_key = config.settings.value(config.GEMINI_KEY, "", type=str)
    if notion_key:
        notion_client = notion_client(auth=config.settings.value(config.NOTION_TOKEN, "", type=str))
    else:
        notion_client = None
