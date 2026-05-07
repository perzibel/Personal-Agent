import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import (
    GOOGLE_DRIVE_FOLDER_ID,
    DOCUMENTS_FOLDER,
    IMAGES_FOLDER,
    RECEIPTS_FOLDER,
    SCREENSHOTS_FOLDER,
    SQLITE_DB_PATH,
    GOOGLE_OAUTH_CREDENTIALS,
    GOOGLE_TOKEN_PATH,
)

SCOPES = [
    scope.strip()
    for scope in os.getenv("GOOGLE_SCOPES", "").split(",")
    if scope.strip()
]

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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

        GOOGLE_TOKEN_PATH.write_text(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    return service


def get_db_connection():
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def fetch_drive_files(service, folder_id: str):
    files = []
    page_token = None

    query = (
        f"'{folder_id}' in parents "
        f"and trashed = false "
        f"and mimeType != 'application/vnd.google-apps.folder'"
    )

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                orderBy="modifiedTime desc",
                pageSize=100,
                pageToken=page_token,
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, createdTime, modifiedTime, webViewLink, size)"
                ),
            )
            .execute()
        )

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return files


def get_existing_drive_file_ids(conn) -> set[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT drive_file_id FROM files")
    rows = cursor.fetchall()
    return {row[0] for row in rows}


def infer_file_category(mime_type: str, file_name: str, source_folder: str | None = None) -> str:
    mime_type = (mime_type or "").lower()
    file_name = (file_name or "").lower()
    source_folder = (source_folder or "").lower()

    if mime_type.startswith("image/"):
        if "screenshot" in source_folder or "screenshot" in file_name:
            return "screenshot"
        return "image"

    if mime_type == "application/pdf":
        return "document"

    if "wordprocessingml" in mime_type or file_name.endswith(".docx"):
        return "document"

    if mime_type.startswith("text/") or file_name.endswith(".txt"):
        return "document"

    return "unknown"


def insert_missing_files(conn, drive_files: list[dict], source_folder: str):
    existing_ids = get_existing_drive_file_ids(conn)
    now_iso = utc_now_iso()

    inserted = 0
    skipped = 0

    cursor = conn.cursor()

    for file in drive_files:
        drive_file_id = file["id"]
        if file.get("mimeType") == "application/vnd.google-apps.folder":
            skipped += 1
            continue

        if drive_file_id in existing_ids:
            skipped += 1
            continue

        file_name = file.get("name")
        mime_type = file.get("mimeType")
        drive_created_time = file.get("createdTime")
        drive_modified_time = file.get("modifiedTime")
        drive_web_link = file.get("webViewLink")
        file_size_bytes = int(file["size"]) if file.get("size") else None
        file_category = infer_file_category(mime_type, file_name, source_folder)

        cursor.execute(
            """
            INSERT INTO files (
                drive_file_id,
                file_name,
                mime_type,
                source_folder,
                drive_web_link,
                file_size_bytes,
                drive_created_time,
                drive_modified_time,
                file_category,
                processing_status,
                first_seen_at,
                last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                drive_file_id,
                file_name,
                mime_type,
                source_folder,
                drive_web_link,
                file_size_bytes,
                drive_created_time,
                drive_modified_time,
                file_category,
                "pending",
                now_iso,
                now_iso,
            ),
        )
        inserted += 1

    conn.commit()
    return inserted, skipped


def update_sync_run(conn, status: str, files_seen: int, files_added: int, files_updated: int = 0, files_failed: int = 0,
                    notes: str = ""):
    cursor = conn.cursor()
    started_at = utc_now_iso()
    finished_at = utc_now_iso()

    cursor.execute(
        """
        INSERT INTO sync_runs (
            started_at,
            finished_at,
            status,
            files_seen,
            files_added,
            files_updated,
            files_failed,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            started_at,
            finished_at,
            status,
            files_seen,
            files_added,
            files_updated,
            files_failed,
            notes,
        ),
    )
    conn.commit()


def main():
    if not GOOGLE_DRIVE_FOLDER_ID:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID is empty in .env")

    print("Connecting to Google Drive...")
    service = get_drive_service()

    print("Fetching files from Drive...")
    folders_list = [(GOOGLE_DRIVE_FOLDER_ID,"Personal-Agent-Inbox "),
                    (DOCUMENTS_FOLDER,"documents"),
                    (IMAGES_FOLDER,"images"),
                    (RECEIPTS_FOLDER,"receipts"),
                    (SCREENSHOTS_FOLDER,"screenshots")]
    try:
        conn = get_db_connection()
        TotalInsert = 0
        TotalSkip = 0
        for folder,source_folder_name in folders_list:
            drive_files = fetch_drive_files(service, folder)

            print(f"Found {len(drive_files)} file(s) in Drive folder.")

            inserted, skipped = insert_missing_files(conn, drive_files, source_folder=source_folder_name)
            TotalInsert += inserted
            TotalSkip += skipped
            update_sync_run(
                conn=conn,
                status="success",
                files_seen=len(drive_files),
                files_added=inserted,
                files_updated=0,
                files_failed=0,
                notes=f"Skipped existing files: {skipped}",
            )

            print(f"Inserted {inserted} new file(s) into SQLite.")
            print(f"Skipped {skipped} existing file(s).")

            if drive_files:
                print("\nTop 10 files by last updated:")
                for file in drive_files[:10]:
                    print(f"- {file.get('modifiedTime')} | {file.get('name')} ({file.get('id')})")

        print(f"Total Inserted {TotalInsert} new file(s) into SQLite.")
        print(f"Total Skipped {TotalSkip} existing file(s).")

    finally:
        conn.close()


if __name__ == "__main__":
    print(f"SQLITE_DB_PATH from config: {SQLITE_DB_PATH}")
    print(f"Resolved path: {Path(SQLITE_DB_PATH).resolve()}")
    main()
