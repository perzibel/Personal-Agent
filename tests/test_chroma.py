from app.chroma_config import get_chroma_client, get_or_create_collection

client = get_chroma_client()
collection = get_or_create_collection(client)

collection.upsert(
    ids=["chunk_1", "chunk_2"],
    documents=[
        "Photo of a baby sleeping in a stroller",
        "Screenshot of a hotel booking confirmation with check-in details"
    ],
    metadatas=[
        {
            "file_id": 1,
            "file_name": "baby_photo.jpg",
            "file_type": "image",
            "chunk_type": "caption",
            "source_folder": "baby"
        },
        {
            "file_id": 2,
            "file_name": "booking_screenshot.png",
            "file_type": "image",
            "chunk_type": "ocr_text",
            "source_folder": "screenshots"
        }
    ]
)

results = collection.query(
    query_texts=["Do I have a picture of my baby?"],
    n_results=2
)

print("Query results:")
print(results)