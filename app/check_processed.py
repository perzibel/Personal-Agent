import sqlite3
from app.config import SQLITE_DB_PATH

conn = sqlite3.connect(SQLITE_DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT *
    FROM files
    ORDER BY last_processed_at DESC
    LIMIT 20
""")

rows = cursor.fetchall()

print("Recently processed files:")
for row in rows:
    print(row)

conn.close()