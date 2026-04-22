from pathlib import Path
import sqlite3
from app.search_service import search_sqlite_by_query


def main():
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "data" / "agent_memory.db"

    conn = sqlite3.connect(db_path)
    try:
        results = search_sqlite_by_query(
            conn=conn,
            query="baby",
            limit=10,
        )

        print("Query results:")
        for item in results:
            print("=" * 80)
            print("file:", item["file_name"])
            print("score:", item["score"])
            print("link:", item["drive_web_link"])
            print("matched_fields:", item.get("matched_fields"))
            print("match_reasons:")
            for reason in item.get("match_reasons", []):
                print(" -", reason)
            print("match_snippets:")
            for field, snippet in item.get("match_snippets", {}).items():
                print(f" - {field}: {snippet}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()