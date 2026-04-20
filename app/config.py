from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()


def get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parent.parent

GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
SQLITE_DB_PATH = PROJECT_ROOT / os.getenv("SQLITE_DB_PATH", "data/agent_memory.db")
GOOGLE_OAUTH_CREDENTIALS = PROJECT_ROOT / os.getenv("GOOGLE_OAUTH_CREDENTIALS", "credentials.json")
GOOGLE_TOKEN_PATH = PROJECT_ROOT / os.getenv("GOOGLE_TOKEN_PATH", "token.json")
DOCUMENTS_FOLDER = os.getenv("DOCUMENTS_FOLDER", "")
IMAGES_FOLDER = os.getenv("IMAGES_FOLDER", "")
RECEIPTS_FOLDER = os.getenv("RECEIPTS_FOLDER", "")
SCREENSHOTS_FOLDER = os.getenv("SCREENSHOTS_FOLDER", "")
TEMP_DOWNLOAD_DIR = PROJECT_ROOT / os.getenv("TEMP_DOWNLOAD_DIR", "data/tmp")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

# Vision config
VISION_ENABLED = get_bool_env("VISION_ENABLED", True)
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "gemma4")
VISION_GENERATE_SUMMARY = get_bool_env("VISION_GENERATE_SUMMARY", True)
VISION_GENERATE_JSON = get_bool_env("VISION_GENERATE_JSON", True)
VISION_MAX_IMAGES_PER_FILE = int(os.getenv("VISION_MAX_IMAGES_PER_FILE", "5"))
VISION_MAX_IMAGE_DIMENSION = int(os.getenv("VISION_MAX_IMAGE_DIMENSION", "2048"))
