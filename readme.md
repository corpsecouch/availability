## Installation

``` pip install streamlit google-auth-oauthlib google-auth-httplib2 google-api-python-client ```

## Google Cloud Setup

1. Go to the Google Cloud Console
2. Create a new project
3. Enable the Google Calendar API
4. Create OAuth 2.0 Client ID credentials
- - Application type: Desktop app
5. Download the credentials
6. Save the downloaded file as credentials.json in the same directory as your script

## Running the App
``` streamlit run availability.py ```