from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agent_memory.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT * FROM files")
tables = cursor.fetchall()

print("Tables in database:")
for table in tables:
    print("-", table)

conn.close()