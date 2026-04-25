from pathlib import Path
import sqlite3

from app.chroma_config import get_chroma_client, get_or_create_collection
from app.search_service import search_all


def main():
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "data" / "agent_memory.db"

    conn = sqlite3.connect(db_path)

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    try:
        results = search_all(
            conn=conn,
            collection=collection,
            query="show me the latest document that is a CV",
            limit=10,
            include_ocr=False,
        )

        print("\nMerged ranked results:")
        print("=" * 100)

        for index, item in enumerate(results, start=1):
            print(f"#{index}")
            print(f"File: {item.get('file_name')}")
            print(f"File ID: {item.get('file_id')}")
            print(f"Link: {item.get('drive_web_link')}")
            print(f"Created at: {item.get('created_at')}")
            print(f"Rank score: {item.get('rank_score')}")
            print(f"Best match score: {item.get('best_match_score')}")
            print(f"Match count: {item.get('match_count')}")
            print(f"Matched sources: {item.get('matched_sources')}")
            print(f"Matched types: {item.get('matched_types')}")
            print(f"Matched chunk types: {item.get('matched_chunk_types')}")
            print(f"Matched reason: {item.get("match_reasons", [])}")
            print()

            print("Why matched:")
            for reason in item.get("match_reasons", []):
                print(f"- Source: {reason.get('source')}")
                print(f"  Type: {reason.get('match_type')}")
                print(f"  Chunk type: {reason.get('matched_chunk_types')}")
                print(f"  Score: {reason.get('score')}")
                print(f"  Distance: {reason.get('distance')}")

                why = reason.get("why_matched") or {}
                if why:
                    print(f"  Reason: {why.get('reason')}")
                    print(f"  Preview: {why.get('matched_text_preview') or reason.get('text_preview')}")

                print()

            print("=" * 100)

    finally:
        conn.close()


if __name__ == "__main__":
    main()