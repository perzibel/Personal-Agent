from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agent_memory.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT id, drive_file_id, file_name, file_category, processing_status FROM files;")
rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()