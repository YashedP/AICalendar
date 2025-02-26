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

from openai import OpenAI
import json

import config

class Event(BaseModel):
    title: str
    start: str
    end: str

class Events(BaseModel):
    events: list[Event]

# From the tasks, create the events on the AI Tasks Calendar
def auto_schedule_tasks(days=2):
    check_AI_tasks_calendar()
    parse_passed_tasks()
    tasks = get_tasks()
    intervals = find_open_time(days)
    ai_tasks = find_task_times(days, tasks, intervals)
    
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
                
        for day in range(len(free_times)):
            i = (day + datetime.now().weekday()) % len(free_times)
            for intervals in free_times[i]:
                intervals[0] = datetime.combine(datetime.today() + timedelta(days=day), intervals[0])
                intervals[1] = datetime.combine(datetime.today() + timedelta(days=day), intervals[1])
            
                
        return free_times
    except HttpError as error:
        print(f"HttpError error occurred: {error}")

# Get the times that is going to be occupied from the AI model
def find_task_times(days: int, tasks: list[list[str, str]], free_times: list[list[time, time]]) -> list[Event]:
    if free_times == None or tasks == None:
        return

    task_list = ""
    for task in tasks:
        task_list += f"{task[0]}, Priority: {task[1]}\n"

    free_time_list = ""
    for day in range(days):
        i = (day + datetime.today().weekday()) % len(free_times)
        
        free_time_list += f"Day {day + 1}:\n"
        for interval in free_times[i]:
            free_time_list += f"dateTime start: {interval[0].isoformat()}, dateTime end: {interval[1].isoformat()}\n"
        free_time_list += "\n"
    
    # prompt = f"""
    # You are a personal assistant that takes information about any given task and its priority, 
    # you will predict the time it will take to complete the task and list the start and end time in the a day in ISO standard.
    # The minimum length of a scheduled task is 15 minutes.
    
    # Here are your list of tasks to schedule:

    # {task_list}

    # Here are times the user is free, you should scheduling tasks during these times:

    # {free_time_list}
    # """

    gemini_prompt =  f"""
    You are a personal assistant that takes information about any given task and its priority, and tries to plan out the specified days in an efficient manner.
    You will predict the time it will take to complete the task and list the start and end time in the a day in ISO standard.
    The minimum length of a scheduled task is 15 minutes.
    
    You will be provided with the list of tasks to schedule and the times the user is free in ISO format.
    
    Tasks to schedule:
    {task_list}
    
    Intervals of time the user is free:
    {free_time_list}
    """

    system_prompt = f"""
    You are a personal assistant that takes information about any given task and its priority, and tries to plan out the specified days in an efficient manner.
    You will predict the time it will take to complete the task and list the start and end time in the a day in ISO standard.
    
    Minimum length of a scheduled task is 15 minutes.
    You are allowed to put multiple tasks in the same time slot if they are small enough.
    
    You will be provided with the list of tasks to schedule and the times the user is free in ISO format.
    """

    prompt = f"""
    Tasks to schedule:
    {task_list}


    Intervals of time the user is free:
    {free_time_list}
    """

    print(task_list)
    response = config.gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=gemini_prompt,
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[Event],
        },
    ).parsed
    
    # client = OpenAI(api_key=client.settings.value(config.GEMINI_KEY, "", type=str))
    
    # response = client.beta.chat.completions.parse(
    #     model="gpt-4o-mini-2024-07-18",
    #     messages=[
    #         {"role": "system", "content": system_prompt},
    #         {"role": "user", "content": prompt}
    #     ],
    #     response_format=Events,
    # )
    
    # response = response.choices[0].message.parsed.events
    
    for i in range(len(response)):
        start = datetime.fromisoformat(response[i].start)
        end = datetime.fromisoformat(response[i].end)
        
        print(f"Task {response[i].title}: {start.hour}:{start.minute:02} to {end.hour}:{end.minute:02}")
    
    return response

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
        return

    calendar = {
        "summary": "AI Tasks",
        "timeZone": get_localzone().key
    }

    service.calendars().insert(body=calendar).execute()
