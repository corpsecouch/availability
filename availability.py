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

# https://google-auth.readthedocs.io/en/stable/reference/google.oauth2.credentials.html
# https://google-auth.readthedocs.io/en/master/reference/google.auth.transport.requests.html
def get_google_calendar_service():
    """
    Authenticate and create a Google Calendar service object.
    Handles token storage and refresh.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        # print("creds don't exist or are not valid")
        # print("creds:", creds)
        # print("valid:", creds.valid)

        if creds.expired:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            creds.refresh(Request())
        
        # if creds and creds.expired and creds.refresh_token:
        #     print("creds are expired")
        #     print('valid:', creds.valid)
        #     print('expired:', creds.expired)
        #     print('refresh_token:', creds.refresh_token)
        #     print('token_uri:', creds.token_uri)
        #     print('client_id:', creds.client_id)
        #     print('client_secret:', creds.client_secret)
        #     print('scopes:', creds.scopes)

        #     print("refresh the token")
        #     req = Request()
        #     print(req)
        #     val = creds.refresh(Request())
        #     print(val)
        #     print("after")
        # else:
        #     print("four")
        #     flow = InstalledAppFlow.from_client_secrets_file(
        #         'credentials.json', SCOPES)
        #     creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

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


def calc_avail_for_day(date, earliest_time, latest_time, tz, smallest, events):
    # make sure the dates and times are adjusted for the timezone
    # earliest = datetime.combine(date=date, time=earliest_time, tzinfo=tz)
    # latest = datetime.combine(date=date, time=latest_time, tzinfo=tz)
    earliest = datetime.combine(date=date, time=earliest_time).astimezone(tz)
    latest = datetime.combine(date=date, time=latest_time).astimezone(tz)

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
    
    # when there are no events
    if busy_time == zero_time:
        availability.append(createSlot(earliest, latest))
    
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

        strAvail.append(f"{strStart} - {strEnd}")

    return strAvail


def get_availability(events, date_range, earliest_time, latest_time, tz, smallest):

    availability = []

    # build the list of availability for each date
    for date in date_range:
        # filter the busy events for any that start or end on the date
        # https://stackoverflow.com/questions/61577168/filter-array-of-objects-in-python
        filtered_events = list(filter(lambda p: datetime.fromisoformat(p['start']).date() == date or datetime.fromisoformat(p['end']).date() == date, events))

        # calculate the availability for the day
        avail = calc_avail_for_day(date, earliest_time, latest_time, tz, smallest, filtered_events)

        availability.append({
            'date': date,
            'slots': avail
        })
    
    return availability


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
        
        cal_list = service.calendarList().list().execute()
        
        cal_list_names = []
        for cal in cal_list['items']:
            cal_list_names.append(cal['summary'])

        cal_primary = list(filter(lambda cal: 'primary' in cal, cal_list['items']))[0]
        cal_primary_tz = ZoneInfo(cal_primary['timeZone'])
        cal_primary_tz_name = datetime.now().replace(tzinfo=cal_primary_tz).tzname()

        # todo: check for no primary calendar
        # todo: check for mulitple primary calendars

        # selected_calendars = st.multiselect("Calendars", cal_list_names, default=cal_primary['summary'])
        # print(selected_calendars)


        col1, col2 = st.columns(2)

        with col2:
            time_zone = st.selectbox("As Time Zone", [ZoneInfo('US/Eastern'), ZoneInfo('US/Central'), ZoneInfo('US/Mountain'), ZoneInfo('US/Pacific')])
            earliest = st.time_input("Earliest Time (" + cal_primary_tz_name + ")", time(hour=9, tzinfo=cal_primary_tz))
            latest = st.time_input("Latest Time (" + cal_primary_tz_name + ")", time(hour=17, tzinfo=cal_primary_tz))
            at_least = st.time_input("At Least", time(minute=30))

        date = datetime.now().replace(tzinfo=time_zone)# + timedelta(days=-3)

        with col1:
            st.text_input(label="Calendar", value=cal_primary['summary'] + " (" + cal_primary_tz_name + ")", disabled=True)
            date_range = st.date_input(label="Dates", value=[date, date + timedelta(days=7)])
            include_weekends = st.toggle('Ignore Weekends')
            hide_empty = st.toggle("Hide Unavailable Days")
        
        
        # expand the date range to be an explicit list
        date_range_start = date_range[0]
        date_range_end = date_range[1]
        date_range_diff = date_range_end - date_range_start
        dates = []
        for next in range(date_range_diff.days + 1):
            next_date = date_range_start + timedelta(days=next)
            dates.append(next_date)


        # get all the busy events from the calendar for the range of dates
        events = get_busy_events(service, [
            datetime.combine(date=date_range[0], time=earliest, tzinfo=time_zone),
            datetime.combine(date=date_range[len(date_range)-1], time=latest, tzinfo=time_zone)
        ], time_zone)


        # get availability
        # days = get_availability(service, dates, earliest, latest, time_zone, timedelta(hours=at_least.hour, minutes=at_least.minute, seconds=at_least.second))
        days = get_availability(
            events=events,
            date_range=dates,
            earliest_time=earliest,
            latest_time=latest,
            tz=time_zone,
            smallest=timedelta(hours=at_least.hour, minutes=at_least.minute, seconds=at_least.second)
        )

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
                    st.write(', '.join(slots))
                    # for slot in slots:
                    #     st.write(slot)
            # st.markdown('----')
    
    except Exception as e:
        # https://docs.python.org/3/tutorial/errors.html#handling-exceptions
        st.error(f"An error occurred: {e}")

if __name__ == '__main__':
    main()