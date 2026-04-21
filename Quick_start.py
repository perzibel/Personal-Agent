import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import (
    GOOGLE_OAUTH_CREDENTIALS,
    GOOGLE_TOKEN_PATH,
    GOOGLE_DRIVE_FOLDER_ID,
    DOCUMENTS_FOLDER,
    IMAGES_FOLDER,
    RECEIPTS_FOLDER,
    SCREENSHOTS_FOLDER,
)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]


def get_drive_service():
    creds = None

    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)

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


def list_files_in_folder(service, folder_name: str, folder_id: str) -> None:
    if not folder_id:
        print(f"[SKIP] {folder_name}: no folder ID configured")
        return

    print(f"\n=== {folder_name} ===")
    print(f"Folder ID: {folder_id}")

    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None
    found_any = False

    while True:
        results = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            )
            .execute()
        )

        items = results.get("files", [])

        for item in items:
            found_any = True
            print(f"{item['name']} ({item['id']}) - {item['mimeType']}")

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    if not found_any:
        print("No files found.")


def main():
    folders = {
        "root_folder": GOOGLE_DRIVE_FOLDER_ID,
        "documents_folder": DOCUMENTS_FOLDER,
        "images_folder": IMAGES_FOLDER,
        "receipts_folder": RECEIPTS_FOLDER,
        "screenshots_folder": SCREENSHOTS_FOLDER,
    }

    try:
        service = get_drive_service()

        for folder_name, folder_id in folders.items():
            list_files_in_folder(service, folder_name, folder_id)

    except HttpError as error:
        print(f"An error occurred: {error}")

    try:
        # Full first initiative flow
        # Import all relevant functions from all files
        from app.init_db import init_db
        from app.sync_drive import main as sync_main
        from app.process_files import main as process_main
        from app.check_processed import main as check_main

        # Run the initiate flow in the right order
        init_db()
        sync_main()
        process_main()
        check_main()

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
