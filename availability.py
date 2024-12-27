import streamlit as st
import pickle
import os
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta, time
import zoneinfo
from zoneinfo import ZoneInfo
import copy

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_google_calendar_service():
    """
    Authenticate and create a Google Calendar service object.
    Handles token storage and refresh.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        print("five")
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        print("one")
        if creds and creds.expired and creds.refresh_token:
            print("before")
            creds.refresh(Request())
            print("after")
        else:
            print("four")
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    else:
        print("two")

    return build('calendar', 'v3', credentials=creds)


# creates and returns a new dictionary object with deep copies of the start and end date objects
def createSlot(start, end):
    return {
        'start': copy.deepcopy(start),
        'end': copy.deepcopy(end)
    }


def get_busy_events(service, date_range, tz):
    rval = service.freebusy().query(body={
        "timeMin": date_range[0].isoformat(),
        "timeMax": date_range[1].isoformat(),
        "timeZone": tz.key,
        "items":[
            {"id": 'primary'}
        ]
    }).execute()

    return rval['calendars']['primary']['busy']


def calc_busy_time_for_day(events):
    rval = timedelta()
    for event in events:
        event_start = event.get('start')
        event_start = datetime.fromisoformat(event_start)#.replace(tzinfo=tz)

        event_end = event.get('end')
        event_end = datetime.fromisoformat(event_end)#.replace(tzinfo=tz)

        rval = rval + (event_end - event_start)
    return rval


# returns the availablilty for a single date
def get_availablity_for_day(service, date, earliest_time, latest_time, tz, smallest):
    earliest = datetime.combine(date=date, time=earliest_time, tzinfo=tz)
    latest = datetime.combine(date=date, time=latest_time, tzinfo=tz)

    events = get_busy_events(service, [earliest, latest], tz)

    availability = []
    zero_time = timedelta(hours=0, minutes=0, seconds=0)

    # turn the events list into a linked list
    prev_event = None
    for event in events:
        if prev_event:
            prev_event.update({'next': event})
            event.update({'prev': prev_event})
        prev_event = event

    # calculate how much time is busy
    busy_time = calc_busy_time_for_day(events)

    # calculate how much potential availability window there is
    window_time = latest - earliest

    # there's no availabiltity for the day if the busy_time = window_time
    if window_time == busy_time:
        return availability

    # build the list of availability between events
    for event in events:
        event_start = event.get('start')
        event_start = datetime.fromisoformat(event_start).replace(tzinfo=tz)

        event_end = event.get('end')
        event_end = datetime.fromisoformat(event_end).replace(tzinfo=tz)

        prev_event = event.get('prev')
        next_event = event.get('next')

        if prev_event:
            prev_end = datetime.fromisoformat(prev_event.get('end'))
            diff = event_start - prev_end
            if diff >= smallest:
                availability.append(createSlot(prev_end, event_start))

        else:
            diff = event_start - earliest

            if diff > zero_time:
                if event_start-earliest >= smallest:
                    availability.append(createSlot(earliest, event_start))
            else:
                if latest - event_end >= smallest:
                    availability.append(createSlot(event_end, latest))
        
        if not next_event:
            if latest - event_end >= smallest:
                availability.append(createSlot(event_end, latest))

    return availability


# returns a formatted date string
def format_date(date):
    return date.strftime("%a, %b %-d")


# formats the list of availability
def format_slots(availability):
    strAvail = []

    # if there is no availability
    if not len(availability):
        strAvail.append('None')

    # if there is availability
    for slot in availability:
        
        # format the start time

        format_string = '%-I:%M%p'
        
        if not (slot['start'].hour < 12 and slot['end'].hour >= 12):
            format_string = format_string.replace('%p', '')

        if slot['start'].minute == 0:
            format_string = format_string.replace(':%M', '')

        strStart = slot['start'].strftime(format_string).lower()


        # format the end time

        format_string = '%-I:%M%p'

        if slot['end'].minute == 0:
            format_string = format_string.replace(':%M', '')
        strEnd = slot['end'].strftime(format_string).lower()

        strAvail.append(f"{strStart}-{strEnd}")

    return strAvail


def get_availability(service, date_range, earliest_time, latest_time, tz, smallest):
    dates = [
        datetime.combine(date=date_range[0], time=earliest_time, tzinfo=tz),
        datetime.combine(date=date_range[1], time=latest_time, tzinfo=tz)
    ]

    busy_events = get_busy_events(service, dates, tz)

    for event in busy_events:
        print(event)


# returns a list of availability for the list of dates
def get_availability_for_days(service, date_range, earliest_time, latest_time, tz, smallest):
    availability = []

    for date in date_range:
        avail = get_availablity_for_day(service, date, earliest_time, latest_time, tz, smallest)
        availability.append({
            'date': date,
            'slots': avail
        })

    return availability


# def get_date_range(date, num, weekends):
#     dates = []
#     next = 0
#     while len(dates) < num:
#         next_date = date + timedelta(days=next)
#         if next_date.weekday() < 5:
#             dates.append(next_date)
#         elif weekends:
#             dates.append(next_date)
#         next += 1
#     return dates


def is_US_timezone(item):
    return item.find('US/') >= 0

def main():
    st.title('Google Calendar Availability')
    
    # Authentication check
    if not os.path.exists('credentials.json'):
        st.error("""
        Google Cloud credentials file not found! 
        Please follow these steps:
        1. Go to Google Cloud Console
        2. Create a new project
        3. Enable Google Calendar API
        4. Create OAuth 2.0 Client ID credentials
        5. Download the credentials and save as 'credentials.json' in this directory
        """)
        return
    
    try:
        # Authenticate and create the google calendar service
        service = get_google_calendar_service()
        
        col1, col2 = st.columns(2)

        with col2:
            time_zone = st.selectbox("Time zone", [ZoneInfo('US/Eastern'), ZoneInfo('US/Central'), ZoneInfo('US/Mountain'), ZoneInfo('US/Pacific')])
            earliest = st.time_input("Earliest Time", time(hour=9))
            latest = st.time_input("Latest Time", time(hour=17))
            at_least = st.time_input("At Least", time(minute=30))
        
        date = datetime.now().replace(tzinfo=time_zone)# + timedelta(days=-3)

        with col1:
            date_range = st.date_input(label="Dates", value=[date, date + timedelta(days=7)])
            include_weekends = st.toggle('Hide Weekends')
            hide_empty = st.toggle("Hide Empty Days")
        
        
        # expand the date range to be an explicit list
        date_range_start = date_range[0]
        date_range_end = date_range[1]
        date_range_diff = date_range_end - date_range_start
        dates = []
        for next in range(date_range_diff.days + 1):
            next_date = date_range_start + timedelta(days=next)
            dates.append(next_date)


        # get availability
        # days = get_availability_for_days(service, dates, earliest, latest, time_zone, timedelta(hours=at_least.hour, minutes=at_least.minute, seconds=at_least.second))
        days = get_availability(service, dates, earliest, latest, time_zone, timedelta(hours=at_least.hour, minutes=at_least.minute, seconds=at_least.second))

        st.divider()

        # Display available time slots
        st.subheader('Available Time Slots')

        # print out the availability
        for day in days:
            visible = True
            if len(day.get('slots')) == 0 and hide_empty:
                visible = False
            if day.get('date').weekday() >= 5 and include_weekends:
                visible = False

            if visible:
                col1, col2 = st.columns(2)
                with col1:
                    st.write(format_date(day.get('date')))
                with col2:
                    slots = format_slots(day.get('slots'))
                    for slot in slots:
                        st.write(slot)
            # st.markdown('----')
    
    except Exception as e:
        # https://docs.python.org/3/tutorial/errors.html#handling-exceptions
        st.error(f"An error occurred: {e}")

if __name__ == '__main__':
    main()