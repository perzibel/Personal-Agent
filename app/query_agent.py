from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.config import SQLITE_DB_PATH


def search_chroma_visual_chunks(
    collection,
    query_text: str,
    n_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Query Chroma for semantically similar chunks, including visual_summary chunks.
    Assumes chunk metadata includes file_id and chunk_type.
    """
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    hits: list[dict[str, Any]] = []

    for doc, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        chunk_type = metadata.get("chunk_type")

        hits.append(
            {
                "source": "chroma",
                "match_type": "semantic_chunk",
                "file_id": metadata.get("file_id"),
                "chunk_type": chunk_type,
                "text": doc,
                "score": 1 - float(distance) if distance is not None else 0.0,
                "metadata": metadata,
            }
        )

    return hits


def search_sqlite_vision_entities(
    conn: sqlite3.Connection,
    query_text: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Search entities table for matches that likely came from visual extraction.
    Assumes entities.source distinguishes visual sources like:
    - visual_summary
    - vision_json
    - image_caption
    """
    cursor = conn.cursor()

    like_query = f"%{query_text}%"

    cursor.execute(
        """
        SELECT
            e.file_id,
            e.entity_type,
            e.entity_value,
            e.confidence,
            e.source
        FROM entities e
        WHERE
            e.source IN ('visual_summary', 'vision_json', 'image_caption')
            AND e.entity_value LIKE ?
        ORDER BY
            COALESCE(e.confidence, 0) DESC,
            e.created_at DESC
        LIMIT ?
        """,
        (like_query, limit),
    )

    rows = cursor.fetchall()

    hits: list[dict[str, Any]] = []
    for row in rows:
        hits.append(
            {
                "source": "sqlite",
                "match_type": "vision_entity",
                "file_id": row[0],
                "entity_type": row[1],
                "entity_value": row[2],
                "score": float(row[3]) if row[3] is not None else 0.5,
                "metadata": {
                    "entity_source": row[4],
                },
            }
        )

    return hits


def load_file_details(conn: sqlite3.Connection, file_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not file_ids:
        return {}

    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in file_ids)

    cursor.execute(
        f"""
        SELECT
            f.id,
            f.file_name,
            f.mime_type,
            f.source_folder,
            f.drive_web_link,
            fc.extracted_text,
            fc.ocr_text,
            fc.image_caption,
            fc.visual_summary,
            fc.vision_json
        FROM files f
        LEFT JOIN file_content fc ON fc.file_id = f.id
        WHERE f.id IN ({placeholders})
        """,
        file_ids,
    )

    rows = cursor.fetchall()

    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        vision_json = None
        if row[9]:
            try:
                vision_json = json.loads(row[9])
            except json.JSONDecodeError:
                vision_json = row[9]

        result[row[0]] = {
            "file_id": row[0],
            "file_name": row[1],
            "mime_type": row[2],
            "source_folder": row[3],
            "drive_web_link": row[4],
            "extracted_text": row[5],
            "ocr_text": row[6],
            "image_caption": row[7],
            "visual_summary": row[8],
            "vision_json": vision_json,
        }

    return result


def merge_results(
    chroma_hits: list[dict[str, Any]],
    entity_hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge hits by file_id and keep supporting evidence from both sources.
    """
    merged: dict[int, dict[str, Any]] = {}

    for hit in chroma_hits + entity_hits:
        file_id = hit.get("file_id")
        if file_id is None:
            continue

        if file_id not in merged:
            merged[file_id] = {
                "file_id": file_id,
                "score": 0.0,
                "semantic_hits": [],
                "entity_hits": [],
            }

        merged[file_id]["score"] += hit.get("score", 0.0)

        if hit["source"] == "chroma":
            merged[file_id]["semantic_hits"].append(hit)
        elif hit["source"] == "sqlite":
            merged[file_id]["entity_hits"].append(hit)

    return sorted(
        merged.values(),
        key=lambda item: item["score"],
        reverse=True,
    )


def query_agent(
    query_text: str,
    chroma_collection,
    sqlite_db_path=SQLITE_DB_PATH,
    semantic_limit: int = 10,
    entity_limit: int = 10,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(sqlite_db_path)
    try:
        chroma_hits = search_chroma_visual_chunks(
            collection=chroma_collection,
            query_text=query_text,
            n_results=semantic_limit,
        )

        entity_hits = search_sqlite_vision_entities(
            conn=conn,
            query_text=query_text,
            limit=entity_limit,
        )

        merged = merge_results(chroma_hits, entity_hits)

        file_ids = [item["file_id"] for item in merged]
        file_details = load_file_details(conn, file_ids)

        for item in merged:
            item["file"] = file_details.get(item["file_id"], {})

        return merged

    finally:
        conn.close()