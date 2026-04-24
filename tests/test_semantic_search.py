from pathlib import Path
import sqlite3

from app.chroma_config import get_chroma_client, get_or_create_collection
from app.search_service import semantic_search_chroma


def main():
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "data" / "agent_memory.db"

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    conn = sqlite3.connect(db_path)

    try:
        results = semantic_search_chroma(
            collection=collection,
            conn=conn,
            query="baby",
            limit=10,
            chunk_types=["visual_summary", "image_caption","document_text"],
        )

        for item in results:
            dis = item.get('why_matched', {}).get('distance')
            if dis < 0.75:
                print(item)
                print(f"File: {item.get('file_name')}")
                print(f"Link: {item.get('drive_web_link')}")
                print(f"Created at: {item.get('created_at')}")
                print(f"Created source: {item.get('why_matched', {}).get('created_at_source')}")
                print(f"SQLite metadata found: {item.get('why_matched', {}).get('sqlite_metadata_found')}")
                print(f"Matched reason: {item.get('why_matched', {}).get('reason')}")
                print(f"Matched text: {item.get('why_matched', {}).get('matched_text_preview')}")
                print(f"Matched type: {item.get('why_matched', {}).get('matched_chunk_type')}")
                print(
                    f"Matched distance: {item.get('why_matched', {}).get('distance')} ## the higher this is, the worst "
                    f"the result, should be close to 0")
                print("-" * 80)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
