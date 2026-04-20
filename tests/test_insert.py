from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agent_memory.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
INSERT INTO files (
    drive_file_id,
    file_name,
    mime_type,
    source_folder,
    drive_created_time,
    drive_modified_time,
    file_category,
    processing_status
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "test_file_001",
    "baby_photo_01.jpg",
    "image/jpeg",
    "baby",
    "2026-04-18T10:00:00",
    "2026-04-18T10:05:00",
    "image",
    "pending"
))

conn.commit()
print("Inserted sample row into files table.")

conn.close()