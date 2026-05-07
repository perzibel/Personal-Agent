from app.config import (
    DOCUMENTS_FOLDER,
    IMAGES_FOLDER,
    RECEIPTS_FOLDER,
    SCREENSHOTS_FOLDER,
)

# Add these to config.py when you create the folders:
# CARS_FOLDER
# IDS_FOLDER
# FAMILY_FOLDER
# HOME_FOLDER
# WORK_FOLDER
# UNCATEGORIZED_FOLDER

try:
    from app.config import (
        CARS_FOLDER,
        IDS_FOLDER,
        FAMILY_FOLDER,
        HOME_FOLDER,
        WORK_FOLDER,
        UNCATEGORIZED_FOLDER,
    )
except ImportError:
    CARS_FOLDER = None
    IDS_FOLDER = None
    FAMILY_FOLDER = None
    HOME_FOLDER = None
    WORK_FOLDER = None
    UNCATEGORIZED_FOLDER = None


FOLDER_ID_BY_NAME = {
    "documents": DOCUMENTS_FOLDER,
    "images": IMAGES_FOLDER,
    "receipts": RECEIPTS_FOLDER,
    "screenshots": SCREENSHOTS_FOLDER,
    "cars": CARS_FOLDER or IMAGES_FOLDER,
    "ids": IDS_FOLDER or DOCUMENTS_FOLDER,
    "family": FAMILY_FOLDER or IMAGES_FOLDER,
    "home": HOME_FOLDER or DOCUMENTS_FOLDER,
    "work": WORK_FOLDER or DOCUMENTS_FOLDER,
    "uncategorized": UNCATEGORIZED_FOLDER or DOCUMENTS_FOLDER,
}


def get_folder_id(folder_name: str) -> str:
    folder_id = FOLDER_ID_BY_NAME.get(folder_name)

    if not folder_id:
        raise RuntimeError(f"No Google Drive folder ID configured for folder: {folder_name}")

    return folder_id