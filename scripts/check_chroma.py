from app.chroma_config import get_chroma_client, get_or_create_collection

client = get_chroma_client()
collection = get_or_create_collection(client)

results = collection.get(limit=10)

print("IDs:")
print(results.get("ids"))

print("\nDocuments:")
for doc in results.get("documents", []):
    print("-" * 80)
    print(doc[:500] if doc else None)

print("\nMetadatas:")
for meta in results.get("metadatas", []):
    print(meta)