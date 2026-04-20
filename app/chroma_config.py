from pathlib import Path
import os

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CHROMA_DB_PATH = PROJECT_ROOT / os.getenv("CHROMA_DB_PATH", "data/chroma")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "personal_agent_memory")
CHROMA_DISTANCE_METRIC = os.getenv("CHROMA_DISTANCE_METRIC", "cosine")

# Good lightweight default for local semantic search
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")


def get_embedding_function():
    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL_NAME
    )


def get_chroma_client():
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(CHROMA_DB_PATH),
        settings=Settings()
    )
    return client


def get_or_create_collection(client):
    embedding_function = get_embedding_function()

    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": CHROMA_DISTANCE_METRIC}
    )
    return collection