from datetime import time

from google import genai
from notion_client import Client as NotionClient
from PySide6 import QtCore

LIGHT_MODE_KEY = "light_mode"
GEMINI_KEY = "gemini_key"
GOOGLE_AUTH = "google_auth"
NOTION_TOKEN = "notion_token"
WORK_HOURS = "work_hours"

# Qt decides where to store the settings based on the OS
settings = QtCore.QSettings("Yash", "AICalendar")

work_hours = settings.value(WORK_HOURS, [[time(7, 0, 0).isoformat(), time(22, 0, 0).isoformat()]] * 7, type=list)
for hours in work_hours:
    hours[0] = time.fromisoformat(hours[0])
    hours[1] = time.fromisoformat(hours[1])

def create_gemini_client():
    api_key = settings.value(GEMINI_KEY, None)
    if api_key:
        return genai.Client(api_key=api_key)
    return None

def create_notion_client():
    auth_token = settings.value(NOTION_TOKEN, None)
    if auth_token:
        return NotionClient(auth=auth_token)
    return None

# Create clients
gemini_client = create_gemini_client()
notion_client = create_notion_client()

database_id = "6728f8a2330a4092860d6d358a4c33f3"

calendars = []

ai_calendar = ""