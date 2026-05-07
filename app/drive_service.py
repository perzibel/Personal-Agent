# app/drive_service.py

from pathlib import Path
from typing import Dict

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Reuse your existing auth logic if you already have it.
# This assumes you already have a get_credentials() function.
from app.google_drive_service import get_drive_service


def upload_file_to_drive(
    local_path: Path,
    parent_folder_id: str,
    mime_type: str,
) -> Dict[str, str]:
    service = get_drive_service()

    file_metadata = {
        "name": local_path.name,
        "parents": [parent_folder_id],
    }

    media = MediaFileUpload(
        str(local_path),
        mimetype=mime_type,
        resumable=True,
    )

    uploaded_file = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        )
        .execute()
    )

    return {
        "drive_file_id": uploaded_file["id"],
        "drive_web_link": uploaded_file.get("webViewLink"),
        "drive_file_name": uploaded_file.get("name"),
    }