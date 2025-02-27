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

class Events(BaseModel):
    events: list[Event]
    
# From the tasks, create the events on the AI Tasks Calendar
def auto_schedule_tasks(days=2):
    check_AI_tasks_calendar()
    parse_passed_tasks()
    tasks = get_tasks()
    free_time = find_free_time(days)
    ai_tasks = find_task_times(days, tasks, free_time)
    schedule_tasks_on_calendar(ai_tasks)

# Check if the user has an AI Tasks calendar and if not, create one
def check_AI_tasks_calendar():
    creds = google_auth()

    service = build("calendar", "v3", credentials=creds)

    AI_Tasks = False

    for calendar in service.calendarList().list().execute()['items']:
        if calendar["summary"] == "AI Tasks":
            AI_Tasks = True
            config.ai_calendar = calendar["id"]
        else:
            config.calendars.append(calendar["id"])
        

    if AI_Tasks:
        return

    calendar = {
        "summary": "AI Tasks",
        "timeZone": get_localzone().key
    }

    service.calendars().insert(body=calendar).execute()

# Check all the tasks that have finished and ask the user if they're finished
# Design question: should we make the user manually mark them done on the notion database and check that?
# Or ask the user for every task that have passed on the google calendar if it is completed or not
def parse_passed_tasks():
    creds = google_auth()
    service = build("calendar", "v3", credentials=creds)
    
    event_ids = config.settings.value(config.EVENT_IDS, [], type=list)
    
    for id in event_ids:
        service.events().delete(calendarId=config.ai_calendar, eventId=id).execute()

# Get tasks from the notion database that is schedulable
def get_tasks() -> list[list[str]]:
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
        duration = results[i]['properties']['Duration']['select']
        
        # If the user has not set a priority, set it to 0
        if priority == None:
            priority = "N/A"
        else:
            priority = priority['name']
        
        if duration == None:
            duration = "N/A"
        else:
            duration = duration['name']
        
        # Append the task and its priority to the list
        tasks.append([title, priority, duration])

    # Sort tasks by priority in descending order
    tasks.sort(key=lambda x: x[1], reverse=True)

    return tasks

# Get all the free intervals for when the user is free
def find_free_time(days: int) -> list[list[time, time]]:
    days -= 1
    
    creds = google_auth()
    
    try:
        free_times = copy.deepcopy(config.work_hours)

        for i in range(len(free_times)):
            free_times[i] = [[free_times[i][0], free_times[i][1]]]
        
        now = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0).astimezone().isoformat()
        timeMax = (datetime.today().replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=days)).astimezone().isoformat()            

        for calendar in config.calendars:
            service = build("calendar", "v3", credentials=creds)

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
            
            if config.debug_time_starts_at_beginning_of_day:
                time_now = time(0, 0, 0)
            else:
                time_now = time(datetime.now().hour, datetime.now().minute, 0)
            
            # If the interval is before the current time, remove it
            if interval[1] < time_now:
                intervals.remove(interval)    
            elif interval[0] < time_now:
                if time_now.minute > 45:
                    # if time_now.hour == 23:
                    #     interval[0] = time(0, 0, 0)
                    interval[0] = time(time_now.hour + 1, 0, 0)
                else:
                    for n in [15, 30, 45]:
                        if time_now.minute < n:
                            interval[0] = time(time_now.hour, n, 0)
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
                        interval[0] = time(end.hour, end.minute, 0)
                        break
                    
                    # 4. Event starts in the middle of the interval and ends after the interval
                    elif start.time() < interval[1] and end.time() >= interval[1]:
                        interval[1] = time(start.hour, start.minute, 0)
                        break
                    
                    # 5. Event starts in the middle of the interval and ends in the middle of the interval
                    elif start.time() > interval[0] and end.time() < interval[1]:
                        new_interval = [time(end.hour, end.minute, 0), interval[1]]
                        interval[1] = time(start.hour, start.minute, 0)
                        free_time.insert(i + 1, new_interval)
                    
                    # 6. Event overlaps the entire interval
                    else:
                        free_time.pop(i)

        # Change all of the time objects to datetime objects and add the day that it is on
        for day in range(len(free_times)):
            i = (day + datetime.now().weekday()) % len(free_times)
            for intervals in free_times[i]:
                intervals[0] = datetime.combine(datetime.today() + timedelta(days=day), intervals[0])
                intervals[1] = datetime.combine(datetime.today() + timedelta(days=day), intervals[1])

        # Remove all intervals that are less than 15 minutes
        for day in free_times:
            if len(day) > 2:
                for i in range(len(day) - 1, -1, -1):
                    interval = day[i]
                    start_time = interval[0]
                    end_time = interval[1]
                    
                    travel_time = config.travel_time
                    
                    # Remove intervals that are less than 2 * the travel time that user has specified, default is 30 minutes
                    if end_time - start_time <= timedelta(minutes=travel_time*2 + 30):
                        day.pop(i)
                        continue

        # Add travel_time for each event
        for day in free_times:
            for i in range(1, len(day) - 1):
                interval = day[i]
                
                interval[0] = interval[0] + timedelta(minutes=travel_time)
                interval[1] = interval[1] - timedelta(minutes=travel_time)
        
        # Add commute_times for each event
        for day in free_times:
            if len(day) > 2:
                start_interval = day[0]
                end_interval = day[-1]
                
                start_interval[1] = start_interval[1] - timedelta(minutes=config.commute_time)
                end_interval[0] = end_interval[0] + timedelta(minutes=config.commute_time)
        
        # Print the free times for debugging purposes
        if config.debug:
            print("Free Time")
            for day in free_times:
                print(f"Day {day[0][0].date()}")
                for interval in day:
                    start = interval[0].time().isoformat()
                    end = interval[1].time().isoformat()
                    print(f"Free time: {start} to {end}")
        
        return free_times
    except HttpError as error:
        print(f"HttpError error occurred: {error}")
    
    return None

# Get the times that is going to be occupied from the AI model
def find_task_times(days: int, tasks: list[list[str, str]], free_times: list[list[time, time]]) -> list[Event]:
    if free_times == None or tasks == None:
        return

    task_list = ""
    for i in range(len(tasks)):
        task_list += f"{i}. {tasks[i][0]}, Priority: {tasks[i][1]}, Duration: {tasks[i][2]}\n"

    free_time_list = ""
    for day in range(days):
        i = (day + datetime.today().weekday()) % len(free_times)
        
        free_time_list += f"Day {day + 1}:\n"
        for interval in free_times[i]:
            free_time_list += f"start time: {interval[0].isoformat()}, end time: {interval[1].isoformat()}\n"
        free_time_list += "\n"

    if config.use_gemini:
        gemini_prompt = f"""
You are a personal assistant that schedules tasks efficiently within the user's free time.  
Predict task durations and provide start/end times in ISO format.  
- Min task duration: 15 min.  
- **Prioritize high-priority tasks** if given.  
- **Use provided durations**, otherwise estimate based on complexity.  
- **Break large tasks** into smaller parts **if** split into different time intervals (e.g., "Task 1/2", "Task 2/2").  
- **Do not exceed free time intervals.**  
- **If placing tasks at the day's start/end, prefer earlier slots.**  
- **Keep flexibility** for unexpected changes.  

**Tasks to schedule:**  
{task_list}  

**User's free time slots:**  
{free_time_list}
        """

        if config.debug:
            print(gemini_prompt)

        response = config.gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=gemini_prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': list[Event],
            },
        ).parsed
    
    else:
        from openai import OpenAI
        
        system_prompt = """
You are a personal assistant that schedules tasks efficiently within the user's free time.  
Predict task durations and provide start/end times in ISO format.  

1. Predict the time each task will take and schedule them within the provided free time slots.
3. Enforce a minimum task duration of **15 minutes.**
4. **Prioritize high-priority tasks** when possible.
5. Use the user-provided duration if available; otherwise, estimate based on task complexity.
6. If a task is too large for a single interval, break it into smaller segments that fit into separate free time intervals.
7. Do not schedule tasks outside the provided free time intervals.
9. Optimize overall time allocation while allowing for flexibility.
    """

        user_prompt = f"""
Here are the tasks to schedule:  
{task_list}  

Here are the user's available free time slots:  
{free_time_list}
        """

        if config.debug:
            print(system_prompt)
            print(user_prompt)
        
        client = OpenAI(api_key=config.settings.value(config.CHATGPT_KEY, "", type=str))
        
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=Events,
        )
        
        response = response.choices[0].message.parsed.events
    
    if config.debug:
        for i in range(len(response)):
            start = datetime.fromisoformat(response[i].start)
            end = datetime.fromisoformat(response[i].end)
            
            print(f"Task {response[i].title}: {start.hour}:{start.minute:02} to {end.hour}:{end.minute:02}")
    
    return response

# Schedule the AI Tasks events on the AI Tasks Calendar
def schedule_tasks_on_calendar(events: list[Event]):
    if len(events) == 0:
        print("No events to schedule")
    
    event_id = []
    
    for event in events:
        creds = google_auth()
        service = build("calendar", "v3", credentials=creds)
        
        event = {
            "summary": event.title,
            "start": {"dateTime": event.start, "timeZone": get_localzone().key},
            "end": {"dateTime": event.end, "timeZone": get_localzone().key},
        }

        event_id.append(service.events().insert(calendarId=config.ai_calendar, body=event).execute().get("id"))
    
    config.settings.setValue(config.EVENT_IDS, event_id)    


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