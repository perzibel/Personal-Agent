import sqlite3
from app.config import SQLITE_DB_PATH

conn = sqlite3.connect(SQLITE_DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT
        f.file_name,
        c.chunk_type,
        c.chunk_index,
        c.chunk_text
    FROM chunks c
    JOIN files f ON f.id = c.file_id
    ORDER BY c.id DESC
    LIMIT 20
""")

rows = cursor.fetchall()

for row in rows:
    file_name, chunk_type, chunk_index, chunk_text = row
    print("\n" + "=" * 80)
    print(f"FILE: {file_name}")
    print(f"CHUNK TYPE: {chunk_type}")
    print(f"CHUNK INDEX: {chunk_index}")
    print(f"TEXT:\n{chunk_text[:500]}")

conn.close()