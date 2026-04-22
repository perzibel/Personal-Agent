import sqlite3
from app.config import SQLITE_DB_PATH


def main():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM files
    """)

    rows = cursor.fetchall()

    print("Recently processed files:")
    for row in rows:
        print(row)

    conn.close()


if __name__ == "__main__":
    main()
