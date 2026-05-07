from pathlib import Path
from typing import Optional

from app.config import (
    DOCUMENTS_FOLDER,
    IMAGES_FOLDER,
    RECEIPTS_FOLDER,
    SCREENSHOTS_FOLDER,
)


def classify_upload_folder(
    local_path: Path,
    mime_type: str,
    caption: Optional[str] = None,
) -> dict:
    text = " ".join(
        [
            local_path.name or "",
            mime_type or "",
            caption or "",
        ]
    ).lower()

    suffix = local_path.suffix.lower()
    mime_lower = (mime_type or "").lower()

    if any(word in text for word in ["receipt", "invoice", "payment", "total", "חשבונית", "קבלה"]):
        return {
            "folder_name": "receipts",
            "folder_id": RECEIPTS_FOLDER,
            "reason": "receipt/invoice keywords detected",
        }

    if any(word in text for word in ["screenshot", "screen shot", "צילום מסך"]):
        return {
            "folder_name": "screenshots",
            "folder_id": SCREENSHOTS_FOLDER,
            "reason": "screenshot keywords detected",
        }

    if suffix in [".pdf", ".docx", ".doc", ".txt"]:
        return {
            "folder_name": "documents",
            "folder_id": DOCUMENTS_FOLDER,
            "reason": "document file extension",
        }

    if mime_lower.startswith("image/"):
        return {
            "folder_name": "images",
            "folder_id": IMAGES_FOLDER,
            "reason": "image MIME type",
        }

    return {
        "folder_name": "documents",
        "folder_id": DOCUMENTS_FOLDER,
        "reason": "fallback route",
    }