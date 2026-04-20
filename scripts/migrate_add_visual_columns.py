from pathlib import Path
import sqlite3

# Project root = one level above /scripts
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "agent_memory.db"


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        if not column_exists(conn, "file_content", "visual_summary"):
            conn.execute("ALTER TABLE file_content ADD COLUMN visual_summary TEXT;")
            print("Added column: visual_summary")
        else:
            print("Column already exists: visual_summary")

        if not column_exists(conn, "file_content", "vision_json"):
            conn.execute("ALTER TABLE file_content ADD COLUMN vision_json TEXT;")
            print("Added column: vision_json")
        else:
            print("Column already exists: vision_json")

        conn.commit()
        print("Migration completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()