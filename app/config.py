from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
SQLITE_DB_PATH = PROJECT_ROOT / os.getenv("SQLITE_DB_PATH", "data/agent_memory.db")
GOOGLE_OAUTH_CREDENTIALS = PROJECT_ROOT / os.getenv("GOOGLE_OAUTH_CREDENTIALS", "credentials.json")
GOOGLE_TOKEN_PATH = PROJECT_ROOT / os.getenv("GOOGLE_TOKEN_PATH", "token.json")
DOCUMENTS_FOLDER = os.getenv("DOCUMENTS_FOLDER", "")
IMAGES_FOLDER = os.getenv("IMAGES_FOLDER", "")
RECEIPTS_FOLDER = os.getenv("RECEIPTES_FOLDER", "")
SCREENSHOTS_FOLDER = os.getenv("SCREENSHOTS_FOLDER", "")
TEMP_DOWNLOAD_DIR = PROJECT_ROOT / os.getenv("TEMP_DOWNLOAD_DIR", "data/tmp")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")