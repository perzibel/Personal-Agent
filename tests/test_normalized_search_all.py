from pathlib import Path
import sqlite3

from app.chroma_config import get_chroma_client, get_or_create_collection
from app.search_service import search_all


REQUIRED_KEYS = {
    "file_id",
    "file_name",
    "source_folder",
    "drive_web_link",
    "mime_type",
    "rank_score",
    "best_match_score",
    "match_count",
    "matched_sources",
    "matched_types",
    "match_reasons",
}


REQUIRED_REASON_KEYS = {
    "source",
    "match_type",
    "score",
    "distance",
    "matched_fields",
    "matched_terms",
    "score_breakdown",
    "text_preview",
}


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

        print("\nRESULT COUNT:", len(results))
        print("=" * 100)

        assert results, "Expected at least one result for query: liron cv"

        for item in results:
            missing = REQUIRED_KEYS - set(item.keys())
            assert not missing, f"Missing result keys: {missing}"

            assert item.get("file_id"), "Result missing file_id"
            assert item.get("file_name"), "Result missing file_name"
            assert isinstance(item.get("match_reasons"), list), "match_reasons must be a list"

            for reason in item.get("match_reasons", []):
                missing_reason = REQUIRED_REASON_KEYS - set(reason.keys())
                assert not missing_reason, f"Missing reason keys: {missing_reason}"

            print(f"File: {item.get('file_name')}")
            print(f"Rank score: {item.get('rank_score')}")
            print(f"Sources: {item.get('matched_sources')}")
            print(f"Types: {item.get('matched_types')}")
            print(f"Explanation: {item.get('explanation')}")
            print(f"Link: {item.get('drive_web_link')}")
            print("-" * 100)

        assert any(
            "liron" in str(item.get("file_name", "")).lower()
            for item in results
        ), "Expected at least one Liron CV result"

        assert not any(
            "dor" in str(item.get("file_name", "")).lower()
            for item in results
        ), "Did not expect Dor CV when searching liron cv"

        print("\nPASS: normalized search_all works")

    finally:
        conn.close()


if __name__ == "__main__":
    main()