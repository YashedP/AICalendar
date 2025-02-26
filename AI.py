import copy
import os
from datetime import datetime, time, timedelta

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from notion_client import errors
from pydantic import BaseModel
from tzlocal import get_localzone

import config

class Event(BaseModel):
    title: str
    start: str
    end: str

# From the tasks, create the events on the AI Tasks Calendar
def auto_schedule_tasks(days=1):
    check_AI_tasks_calendar()
    parse_passed_tasks()
    tasks = get_tasks()
    intervals = find_open_time(days)
    ai_tasks = find_task_times(tasks, intervals)
    schedule_tasks_on_calendar(ai_tasks)

# Check all the tasks that have finished and ask the user if they're finished
# Design question: should we make the user manually mark them done on the notion database and check that?
# Or ask the user for every task that have passed on the google calendar if it is completed or not
def parse_passed_tasks():
    pass

# Get tasks from the notion database that is schedulable
def get_tasks() -> list[list[str, str]]:
    if config.notion_client == None:
        return None
    
    try:
        my_page = config.notion_client.databases.query(
            **{
                "database_id": config.database_id,
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
    except errors.HTTPResponseError():
        return None

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

# Get all the free intervals for when the user is free
def find_open_time(days: int) -> list[list[time, time]]:
    days -= 1
    
    creds = google_auth()
    
    try:
        free_times = copy.deepcopy(config.work_hours)

        for i in range(len(free_times)):
            free_times[i] = [[free_times[i][0], free_times[i][1]]]
        
        for calendar in config.calendars:
            service = build("calendar", "v3", credentials=creds)

            now = datetime.now().astimezone().isoformat()
            
            timeMax = (datetime.today().replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days)).astimezone().isoformat()

            events_result = (
                service.events()
                .list(
                    calendarId=calendar,
                    timeMin=now,
                    timeMax=timeMax,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            # Start from the time it is now
            intervals = free_times[datetime.today().weekday()]
            interval = intervals[0]
            now = time(datetime.now().hour, datetime.now().minute, 0)
            
            now = time(10, 3, 0) # For testing purposes
            if interval[1] < now:
                intervals.remove(interval)    
            elif interval[0] < now:
                if now.minute > 45:
                    interval[0] = time(now.hour + 1, 0, 0)
                else:
                    for n in [15, 30, 45]:
                        if now.minute < n:
                            interval[0] = time(now.hour, n, 0)
                            break

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

# Get the times that is going to be occupied from the AI model
def find_task_times(tasks: list[list[str, str]], free_times: list[list[time, time]]) -> list[list[datetime, datetime]]:
    if free_times == None or tasks == None:
        return

    task_list = ""
    for task in tasks:
        task_list += f"{task[0]}, Priority: {task[1]}\n"

    free_time_list = ""
    for interval in free_times[datetime.today().weekday()]:
        free_time_list += f"dateTime start: {interval[0].isoformat()}, dateTime end: {interval[1].isoformat()}"

    prompt = f"""You are a bot that takes information about any given task and its priority, 
    you will predict the time it will take to complete the task and list the start and end time in the a day.
    Return in ISO Standard
    Here are your list of tasks to schedule:

    {task_list}

    Here are times the user is free, you should scheduling tasks during these times:

    {free_time_list}
    """

    response = config.gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[Event],
        },
    )
    
    print(response)
    return None

# Schedule the AI Tasks events on the AI Tasks Calendar
def schedule_tasks_on_calendar(events: list[list[datetime, datetime]]):
    pass

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

                    print("string: " + config.settings.value(config.GOOGLE_AUTH, "", type=str))
                    flow = InstalledAppFlow.from_client_secrets_file(
                        config.settings.value(config.GOOGLE_AUTH, "", type=str), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            run = False
        except RefreshError as error:
            os.remove("token.json")
            print("Refresh error, token.json removed")
    return creds

# Check if the user has an AI Tasks calendar and if not, create one
def check_AI_tasks_calendar():
    creds = google_auth()

    service = build("calendar", "v3", credentials=creds)

    AI_Tasks = False

    for calendar in service.calendarList().list().execute()['items']:
        if calendar["summary"] == "AI Tasks":
            AI_Tasks = True
        else:
            config.calendars.append(calendar["id"])
        

    if AI_Tasks:
        print("AI Tasks already exists")
        return

    calendar = {
        "summary": "AI Tasks",
        "timeZone": get_localzone().key
    }

    service.calendars().insert(body=calendar).execute()
