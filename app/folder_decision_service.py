from pathlib import Path
from typing import Optional


AVAILABLE_FOLDERS = [
    "documents",
    "images",
    "receipts",
    "screenshots",
    "cars",
    "ids",
    "family",
    "home",
    "work",
    "uncategorized",
]


def decide_folder_for_file(
    local_path: Path,
    mime_type: str,
    caption: Optional[str],
    visual_summary: Optional[str],
    ocr_text: Optional[str],
    image_caption: Optional[str],
) -> dict:
    """
    MVP deterministic decision layer.

    Later this can be replaced with an LLM call that returns:
    {
      "folder_name": "...",
      "confidence": 0.0-1.0,
      "needs_user_choice": true/false,
      "candidate_folders": [...],
      "reason": "..."
    }
    """

    text = " ".join(
        [
            local_path.name or "",
            mime_type or "",
            caption or "",
            visual_summary or "",
            ocr_text or "",
            image_caption or "",
        ]
    ).lower()

    # High-confidence receipt
    if any(word in text for word in ["receipt", "invoice", "tax invoice", "total", "קבלה", "חשבונית"]):
        return {
            "folder_name": "receipts",
            "confidence": 0.9,
            "needs_user_choice": False,
            "candidate_folders": ["receipts", "documents"],
            "reason": "Receipt/invoice language was detected.",
        }

    # High-confidence screenshot
    if any(word in text for word in ["screenshot", "screen shot", "צילום מסך"]):
        return {
            "folder_name": "screenshots",
            "confidence": 0.9,
            "needs_user_choice": False,
            "candidate_folders": ["screenshots", "images"],
            "reason": "Screenshot language was detected.",
        }

    # Car-related
    if any(word in text for word in ["car", "vehicle", "seat", "ibiza", "license plate", "רכב", "לוחית רישוי"]):
        return {
            "folder_name": "cars",
            "confidence": 0.85,
            "needs_user_choice": False,
            "candidate_folders": ["cars", "images"],
            "reason": "Car-related visual/caption context was detected.",
        }

    # IDs
    if any(word in text for word in ["passport", "id card", "identity card", "driver license", "תעודת זהות", "דרכון", "רישיון"]):
        return {
            "folder_name": "ids",
            "confidence": 0.9,
            "needs_user_choice": False,
            "candidate_folders": ["ids", "documents"],
            "reason": "Identity document context was detected.",
        }

    # Family/person
    if any(word in text for word in ["baby", "child", "mother", "father", "wife", "family", "תינוק", "תינוקת", "ילד", "ילדה", "משפחה"]):
        return {
            "folder_name": "family",
            "confidence": 0.75,
            "needs_user_choice": False,
            "candidate_folders": ["family", "images"],
            "reason": "Family/person context was detected.",
        }

    # Generic documents
    if mime_type in ["application/pdf", "text/plain"] or local_path.suffix.lower() in [".pdf", ".docx", ".doc", ".txt"]:
        return {
            "folder_name": "documents",
            "confidence": 0.8,
            "needs_user_choice": False,
            "candidate_folders": ["documents", "work", "home"],
            "reason": "Document file type was detected.",
        }

    # Generic image but uncertain
    if mime_type.startswith("image/"):
        return {
            "folder_name": None,
            "confidence": 0.45,
            "needs_user_choice": True,
            "candidate_folders": ["images", "family", "cars", "home", "work"],
            "reason": "The file is an image, but the best folder is unclear.",
        }

    return {
        "folder_name": None,
        "confidence": 0.3,
        "needs_user_choice": True,
        "candidate_folders": ["documents", "images", "uncategorized"],
        "reason": "The file type or content is unclear.",
    }