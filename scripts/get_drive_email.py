# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
refresh_token = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")

if not refresh_token:
    print("No refresh token found.")
    exit(1)

try:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token"
    )
    service = build("drive", "v3", credentials=creds)
    about = service.about().get(fields="user").execute()
    user_info = about.get("user", {})
    print("DRIVE_EMAIL:", user_info.get("emailAddress"))
    print("DISPLAY_NAME:", user_info.get("displayName"))
except Exception as e:
    print("ERROR:", e)
