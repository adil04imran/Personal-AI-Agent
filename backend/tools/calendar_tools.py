"""
Google Calendar integration tools.
Handles OAuth 2.0 authentication and REST API interactions for scheduling and retrieving events.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# The scopes required for reading and writing calendar events
SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "backend", "credentials.json")
if not os.path.exists(CREDENTIALS_FILE):
    CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")

TOKEN_FILE = os.path.join(BASE_DIR, "backend", "token.json")
if not os.path.exists(TOKEN_FILE):
    TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def _get_calendar_service():
    """Authenticates via OAuth 2.0 and constructs a Google Calendar v3 service resource."""
    creds = None
    
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google Calendar credentials not found at {CREDENTIALS_FILE}. "
                    "Please download your OAuth credentials from Google Cloud Console "
                    "and save them as backend/credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        try:
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
        except (PermissionError, OSError) as e:
            print(f"Warning: Could not save token.json (read-only filesystem?): {e}")
    
    return build("calendar", "v3", credentials=creds)


@tool
def create_calendar_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Creates a new event on the user's primary Google Calendar.
    
    IMPORTANT: Explicit user confirmation is strictly required prior to execution.
    Ensure all required temporal parameters (start and end times) are definitively resolved.
    
    Args:
        title: The title/name of the event.
        start_datetime: Start date and time in ISO 8601 format (e.g., '2025-01-15T14:00:00').
        end_datetime: End date and time in ISO 8601 format (e.g., '2025-01-15T15:00:00').
        description: Optional description or notes for the event.
        location: Optional location for the event.
    
    Returns:
        Confirmation message with a link to the created event.
    """
    try:
        service = _get_calendar_service()
        
        event_body = {
            "summary": title,
            "start": {
                "dateTime": start_datetime,
                "timeZone": "Asia/Kolkata",  # Default timezone (IST)
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": "Asia/Kolkata",
            },
        }
        
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        
        event = service.events().insert(calendarId="primary", body=event_body).execute()
        event_link = event.get("htmlLink", "N/A")
        event_id = event.get("id", "N/A")
        
        return (
            f"✅ Event created successfully!\n"
            f"Title: {title}\n"
            f"Start: {start_datetime}\n"
            f"End: {end_datetime}\n"
            f"Event ID: {event_id}\n"
            f"View it here: {event_link}"
        )
    
    except FileNotFoundError as e:
        return f"❌ Google Calendar not configured: {str(e)}"
    except HttpError as e:
        return f"❌ Google Calendar API error: {str(e)}"
    except Exception as e:
        return f"❌ Failed to create event: {str(e)}"


@tool
def list_upcoming_events(days_ahead: int = 7) -> str:
    """
    Retrieves upcoming events from the user's primary Google Calendar.
    Utilized for schedule verification and conflict avoidance prior to event creation.
    
    Args:
        days_ahead: Number of days to look ahead (default: 7 days).
    
    Returns:
        A formatted list of upcoming events, or a message if the calendar is clear.
    """
    try:
        service = _get_calendar_service()
        
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"
        
        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        
        events = events_result.get("items", [])
        
        if not events:
            return f"📅 Your calendar is clear for the next {days_ahead} days!"
        
        formatted = [f"📅 Upcoming events (next {days_ahead} days):"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date", "N/A"))
            title = event.get("summary", "No title")
            location = event.get("location", "")
            location_str = f" @ {location}" if location else ""
            formatted.append(f"• {title}{location_str} — {start}")
        
        return "\n".join(formatted)
    
    except FileNotFoundError as e:
        return f"❌ Google Calendar not configured: {str(e)}"
    except HttpError as e:
        return f"❌ Google Calendar API error: {str(e)}"
    except Exception as e:
        return f"❌ Failed to list events: {str(e)}"
