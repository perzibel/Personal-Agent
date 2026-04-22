from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.chroma_config import get_chroma_client, get_or_create_collection

TEST_QUERIES = [
    "Do I have a picture of my baby?",
    "Show me the latest stroller image.",
    "Do I have an image of my ID?",
    "Show me the most recent photo of my baby.",
    "Find pictures where the stroller appears.",
    "Do I have any screenshots saved?",
    "Show me the latest screenshot.",
    "Find photos that include a passport or ID card.",
    "Do I have a picture of a receipt?",
    "Show me the newest image from the beach.",
    "Find images with a baby bottle.",
    "Do I have any photos of the crib?",
    "Show me the latest family picture.",
    "Find the newest image taken in the car.",
    "Do I have any blurry baby pictures?",
    "Show me images that contain documents.",
    "Find the latest image with a stroller and baby together.",
    "Do I have any duplicate-looking screenshots?",
    "Show me the newest photo from my phone camera.",
    "Find images that might contain personal identification information.",
]


def print_query_results(query_text: str, n_results: int = 5):
    results = query_collection(query_text, n_results=n_results)

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0] if "distances" in results else []

    print("\n" + "=" * 100)
    print(f"QUERY: {query_text}")
    print("=" * 100)

    for i, chunk_id in enumerate(ids):
        print(f"\nResult #{i + 1}")
        print(f"ID: {chunk_id}")

        if i < len(distances):
            print(f"Distance: {distances[i]}")

        if i < len(documents):
            print(f"Document: {documents[i]}")

        if i < len(metadatas):
            print("Metadata:")
            for k, v in metadatas[i].items():
                print(f"  {k}: {v}")


def query_collection(query_text: str, n_results: int = 10):
    client = get_chroma_client()
    collection = get_or_create_collection(client)

    return collection.query(
        query_texts=[query_text],
        n_results=n_results,
    )


def test_image_queries_do_not_crash():
    for query in TEST_QUERIES:
        results = query_collection(query, n_results=10)

        assert "ids" in results
        assert "documents" in results
        assert "metadatas" in results


def test_baby_query_returns_results():
    results = query_collection("Do I have a picture of my baby?", n_results=10)

    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]

    assert len(ids) > 0
    assert any(
        md.get("chunk_type") in {"caption", "visual_summary"}
        for md in metadatas
    )
    assert any(
        doc and ("baby" in doc.lower() or "infant" in doc.lower())
        for doc in documents
    )


def test_screenshot_query_returns_screenshot():
    results = query_collection("Show me the latest screenshot.", n_results=15)

    metadatas = results.get("metadatas", [[]])[0]

    assert len(metadatas) > 0
    assert any(
        "screenshot" in (md.get("file_name", "").lower())
        for md in metadatas
    )


def test_document_query_returns_document_like_content():
    results = query_collection("Show me images that contain documents.", n_results=15)

    documents = results.get("documents", [[]])[0]

    assert len(documents) > 0
    assert any(
        doc and any(
            word in doc.lower() for word in ["document", "text", "support", "technical", "article", "id", "passport"])
        for doc in documents
    )


def test_sensitive_id_query_returns_results():
    results = query_collection(
        "Find images that might contain personal identification information.",
        n_results=15,
    )

    documents = results.get("documents", [[]])[0]

    assert len(documents) > 0


if __name__ == "__main__":
    print_query_results("Do I have a picture of my baby?")
    print_query_results("Show me the latest screenshot.")
    print_query_results("Show me images that contain documents.")
    print_query_results("Find images that might contain personal identification information.")
