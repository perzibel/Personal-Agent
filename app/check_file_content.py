import sqlite3
from app.config import SQLITE_DB_PATH

conn = sqlite3.connect(SQLITE_DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT
        f.id,
        f.file_name,
        fc.ocr_text,
        fc.image_caption,
        fc.extracted_text
    FROM files f
    JOIN file_content fc ON f.id = fc.file_id
    ORDER BY f.last_processed_at DESC
    LIMIT 10
""")

rows = cursor.fetchall()

for row in rows:
    file_id, file_name, ocr_text, image_caption, extracted_text = row
    print("\n" + "=" * 80)
    print(f"FILE ID: {file_id}")
    print(f"FILE NAME: {file_name}")
    print(f"IMAGE CAPTION: {image_caption}")
    print(f"OCR TEXT (first 500 chars):\n{(ocr_text or '')[:500]}")
    print(f"EXTRACTED TEXT (first 500 chars):\n{(extracted_text or '')[:500]}")

conn.close()