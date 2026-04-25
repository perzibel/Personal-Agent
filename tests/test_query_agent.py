from pathlib import Path

from app.chroma_config import get_chroma_client, get_or_create_collection
from app.query_agent import query_agent


def main():
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "data" / "agent_memory.db"

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    response = query_agent(
        query="show me the latest document that is a CV",
        collection=collection,
        sqlite_db_path=db_path,
        limit=10,
    )

    print("\nANSWER:")
    print(response.answer)

    print("\nRETRIEVAL QUERY:")
    print(response.retrieval_query)

    print("\nRESULTS:")
    for item in response.results:
        print(item.get("file_name"), item.get("document_event_datetime"))

    assert response.results, "Expected at least one CV result"
    assert response.retrieval_query == "cv", "Expected cleaned retrieval query to be cv"

    first = response.results[0]
    assert "cv" in str(first.get("file_name", "")).lower(), "Top result should be a CV"

    print("\nPASS: latest CV query works")

    print("\nCONTEXT:")
    print("=" * 100)
    print(response.context)


if __name__ == "__main__":
    main()
