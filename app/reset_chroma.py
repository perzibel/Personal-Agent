from app.chroma_config import get_chroma_client
import os
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "personal_agent_memory")

client = get_chroma_client()

try:
    client.delete_collection(COLLECTION_NAME)
    print(f"Deleted collection: {COLLECTION_NAME}")
except Exception as e:
    print(f"Could not delete collection: {e}")