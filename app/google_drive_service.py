import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import (
    GOOGLE_OAUTH_CREDENTIALS,
    GOOGLE_TOKEN_PATH,
)


SCOPES = [
    scope.strip()
    for scope in os.getenv("GOOGLE_SCOPES", "").split(",")
    if scope.strip()
]


def get_drive_service():
    creds = None

    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(GOOGLE_TOKEN_PATH),
            SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GOOGLE_OAUTH_CREDENTIALS),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        with open(GOOGLE_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)