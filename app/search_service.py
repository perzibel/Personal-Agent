from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable
from typing import Any
from chromadb.api.models.Collection import Collection


@dataclass
class SearchFilters:
    query: str = ""
    file_name: str | None = None
    tags: list[str] = field(default_factory=list)

    date_from: str | None = None
    date_to: str | None = None
    date_field: str = "best_available"  # best_available | drive_created_time | drive_modified_time | exif_capture_time | first_seen_at | last_processed_at

    processing_status: str | None = None
    file_category: str | None = None
    mime_type: str | None = None
    source_folder: str | None = None

    limit: int = 25
    offset: int = 0


_ALLOWED_DATE_FIELDS = {
    "best_available",
    "drive_created_time",
    "drive_modified_time",
    "exif_capture_time",
    "first_seen_at",
    "last_processed_at",
}
MATCH_TYPE_WEIGHTS = {
    "exact_query": 1.00,
    "file_name": 0.95,
    "tag": 0.90,
    "metadata": 0.80,
    "semantic": 0.70,
}
CHUNK_TYPE_WEIGHTS = {
    "visual_summary": 0.20,
    "image_caption": 0.15,
    "extracted_text": 0.10,
    "ocr_text": -0.10,
}

def _safe_text(value: str | None) -> str:
    return value or ""


def _build_snippet(text: str, needle: str, radius: int = 60) -> str:
    if not text or not needle:
        return ""

    text_lower = text.lower()
    needle_lower = needle.lower()

    idx = text_lower.find(needle_lower)
    if idx == -1:
        return text[: radius * 2].strip()

    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)

    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


def _explain_match(row_result: dict[str, Any], query: str, requested_tags: list[str] | None = None) -> dict[str, Any]:
    requested_tags = requested_tags or []
    query_tokens = [t.strip().lower() for t in query.split() if t.strip()]

    matched_fields: list[str] = []
    match_reasons: list[str] = []
    match_snippets: dict[str, str] = {}

    fields_to_check = {
        "file_name": row_result.get("file_name", ""),
        "source_folder": row_result.get("source_folder", ""),
        "ocr_text": row_result.get("ocr_text", ""),
        "image_caption": row_result.get("image_caption", ""),
        "visual_summary": row_result.get("visual_summary", ""),
        "extracted_text": row_result.get("extracted_text", ""),
        "content_summary": row_result.get("content_summary", ""),
        "tags_json": row_result.get("tags_json", ""),
    }

    entity_tags = [str(x).lower() for x in row_result.get("entity_tags", [])]

    for token in query_tokens:
        for field_name, field_value in fields_to_check.items():
            if token in _safe_text(field_value).lower():
                if field_name not in matched_fields:
                    matched_fields.append(field_name)
                match_reasons.append(f"{field_name} contains '{token}'")
                if field_name not in match_snippets:
                    match_snippets[field_name] = _build_snippet(_safe_text(field_value), token)
                break

        if token in entity_tags:
            if "entity_tags" not in matched_fields:
                matched_fields.append("entity_tags")
            match_reasons.append(f"entity_tags contains exact tag '{token}'")

    for tag in requested_tags:
        tag_l = tag.lower()
        if tag_l in entity_tags:
            if "entity_tags" not in matched_fields:
                matched_fields.append("entity_tags")
            match_reasons.append(f"requested tag matched entity_tags: '{tag}'")
        elif tag_l in _safe_text(row_result.get("tags_json", "")).lower():
            if "tags_json" not in matched_fields:
                matched_fields.append("tags_json")
            match_reasons.append(f"requested tag matched tags_json: '{tag}'")
            if "tags_json" not in match_snippets:
                match_snippets["tags_json"] = _build_snippet(_safe_text(row_result.get("tags_json", "")), tag)

    row_result["matched_fields"] = matched_fields
    row_result["match_reasons"] = match_reasons
    row_result["match_snippets"] = match_snippets
    return row_result


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _like_param(value: str) -> str:
    return f"%{_escape_like(value)}%"


def _tokenize_query(query: str) -> list[str]:
    return [part.strip() for part in query.split() if part.strip()]


def _build_date_expr(date_field: str) -> str:
    if date_field not in _ALLOWED_DATE_FIELDS:
        raise ValueError(f"Unsupported date_field: {date_field}")

    if date_field == "best_available":
        return """
        COALESCE(
            f.exif_capture_time,
            f.drive_modified_time,
            f.drive_created_time,
            f.last_processed_at,
            f.first_seen_at
        )
        """

    return f"f.{date_field}"


def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
    tags = []
    raw_tags = row["entity_tags"]
    if raw_tags:
        tags = [tag.strip() for tag in raw_tags.split("||") if tag.strip()]

    return {
        "file_id": row["file_id"],
        "drive_file_id": row["drive_file_id"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "source_folder": row["source_folder"],
        "drive_web_link": row["drive_web_link"],
        "file_category": row["file_category"],
        "processing_status": row["processing_status"],
        "drive_created_time": row["drive_created_time"],
        "drive_modified_time": row["drive_modified_time"],
        "exif_capture_time": row["exif_capture_time"],
        "first_seen_at": row["first_seen_at"],
        "last_processed_at": row["last_processed_at"],
        "ocr_text": row["ocr_text"],
        "image_caption": row["image_caption"],
        "visual_summary": row["visual_summary"],
        "extracted_text": row["extracted_text"],
        "content_summary": row["content_summary"],
        "tags_json": row["tags_json"],
        "entity_tags": tags,
        "score": row["score"],
    }


def get_result_file_id(item: dict[str, Any]) -> Any:
    return item.get("file_id") or item.get("id") or item.get("drive_file_id")


def build_match_reason(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": item.get("source"),
        "match_type": item.get("match_type"),
        "chunk_type": item.get("chunk_type"),
        "score": item.get("score"),
        "distance": item.get("distance"),
        "why_matched": item.get("why_matched"),
        "text_preview": (item.get("text") or "")[:300],
    }


def calculate_keyword_boost(query: str, text: str | None) -> float:
    if not query or not text:
        return 0.0

    query_lower = query.lower().strip()
    text_lower = text.lower()

    if query_lower in text_lower:
        return 0.25

    query_terms = [
        term.strip()
        for term in query_lower.split()
        if len(term.strip()) >= 3
    ]

    if not query_terms:
        return 0.0

    matched_terms = sum(
        1 for term in query_terms
        if term in text_lower
    )

    return min(0.20, 0.08 * matched_terms)


def normalize_score(value: float | int | None, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        value = float(value)
    except (TypeError, ValueError):
        return default

    if value < 0:
        return 0.0

    return value


def calculate_result_score(
    item: dict[str, Any],
    query: str,
) -> float:
    match_type = item.get("match_type")
    chunk_type = item.get("chunk_type")

    raw_score = normalize_score(item.get("score"))

    match_type_boost = MATCH_TYPE_WEIGHTS.get(match_type, 0.50)
    chunk_type_boost = CHUNK_TYPE_WEIGHTS.get(chunk_type, 0.0)

    searchable_text = " ".join(
        str(value or "")
        for value in [
            item.get("file_name"),
            item.get("text"),
            item.get("source_folder"),
            item.get("file_category"),
        ]
    )

    keyword_boost = calculate_keyword_boost(query, searchable_text)

    final_score = raw_score + match_type_boost + chunk_type_boost + keyword_boost

    return round(final_score, 6)


def semantic_search_chroma(
    collection: Collection,
    query: str,
    limit: int = 10,
    chunk_types: list[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """
    Search ChromaDB using semantic similarity.

    This returns fuzzy meaning-based matches from embedded chunks.
    Useful for matching:
    - visual summaries
    - captions
    - OCR text
    - extracted document text
    """

    if not query or not query.strip():
        return []

    where_filter = None

    if chunk_types:
        where_filter = {
            "chunk_type": {
                "$in": chunk_types
            }
        }

    results = collection.query(
        query_texts=[query.strip()],
        n_results=limit,
        where=where_filter,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]

    search_results: list[dict[str, Any]] = []

    for doc_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
    ):
        metadata = metadata or {}
        file_id = metadata.get("file_id")
        sqlite_file = None

        if conn is not None and file_id is not None:
            sqlite_file = get_file_by_id(
                conn=conn,
                file_id=int(file_id),
            )

        file_data = sqlite_file or {}

        search_results.append(
            {
                "source": "chroma",
                "match_type": "semantic",
                "chunk_id": doc_id,

                # Prefer SQLite source of truth
                "file_id": file_data.get("id") or file_id,
                "file_name": file_data.get("file_name") or metadata.get("file_name"),
                "drive_file_id": file_data.get("drive_file_id") or metadata.get("drive_file_id"),
                "drive_web_link": file_data.get("drive_web_link") or metadata.get("drive_web_link"),
                "mime_type": file_data.get("mime_type") or metadata.get("mime_type"),
                "source_folder": file_data.get("source_folder") or metadata.get("source_folder"),

                # Time fields from SQLite
                "drive_created_time": file_data.get("drive_created_time"),
                "drive_modified_time": file_data.get("drive_modified_time"),
                "exif_capture_time": file_data.get("exif_capture_time"),
                "first_seen_at": file_data.get("first_seen_at"),
                "last_synced_at": file_data.get("last_synced_at"),
                "last_processed_at": file_data.get("last_processed_at"),

                # Optional convenience field
                "created_at": (
                        file_data.get("exif_capture_time")
                        or file_data.get("drive_created_time")
                        or file_data.get("first_seen_at")
                ),

                "file_category": file_data.get("file_category"),
                "processing_status": file_data.get("processing_status"),

                # Chunk-level fields from Chroma
                "chunk_type": metadata.get("chunk_type"),
                "text": document,
                "distance": distance,
                "score": 1 / (1 + distance) if distance is not None else None,

                "why_matched": {
                    "reason": "Semantic similarity in ChromaDB",
                    "query": query,
                    "matched_chunk_type": metadata.get("chunk_type"),
                    "matched_text_preview": document[:500] if document else "",
                    "distance": distance,
                    "sqlite_metadata_found": sqlite_file is not None,
                    "created_at_source": (
                        "exif_capture_time"
                        if file_data.get("exif_capture_time")
                        else "drive_created_time"
                        if file_data.get("drive_created_time")
                        else "first_seen_at"
                        if file_data.get("first_seen_at")
                        else None
                    ),
                },
            }
        )

    return search_results


def search_sqlite_metadata(
        conn: sqlite3.Connection,
        filters: SearchFilters,
) -> list[dict[str, Any]]:
    """
    Search across:
    - files.file_name
    - files.source_folder
    - file_content.extracted_text
    - file_content.ocr_text
    - file_content.image_caption
    - file_content.visual_summary
    - file_content.content_summary
    - file_content.tags_json
    - entities(entity_type='tag')
    - date fields on files table
    """
    conn.row_factory = sqlite3.Row

    query = _normalize_text(filters.query)
    file_name = _normalize_text(filters.file_name)
    source_folder = _normalize_text(filters.source_folder)
    processing_status = _normalize_text(filters.processing_status)
    file_category = _normalize_text(filters.file_category)
    mime_type = _normalize_text(filters.mime_type)
    tags = [t.strip().lower() for t in filters.tags if t and t.strip()]

    date_expr = _build_date_expr(filters.date_field)

    where_clauses: list[str] = []
    where_params: list[Any] = []

    if filters.date_from:
        where_clauses.append(f"({date_expr}) IS NOT NULL AND ({date_expr}) >= ?")
        where_params.append(filters.date_from)

    if filters.date_to:
        where_clauses.append(f"({date_expr}) IS NOT NULL AND ({date_expr}) <= ?")
        where_params.append(filters.date_to)

    if file_name:
        where_clauses.append("LOWER(f.file_name) LIKE ? ESCAPE '\\'")
        where_params.append(_like_param(file_name.lower()))

    if source_folder:
        where_clauses.append("LOWER(COALESCE(f.source_folder, '')) LIKE ? ESCAPE '\\'")
        where_params.append(_like_param(source_folder.lower()))

    if processing_status:
        where_clauses.append("LOWER(COALESCE(f.processing_status, '')) = ?")
        where_params.append(processing_status.lower())

    if file_category:
        where_clauses.append("LOWER(COALESCE(f.file_category, '')) = ?")
        where_params.append(file_category.lower())

    if mime_type:
        where_clauses.append("LOWER(COALESCE(f.mime_type, '')) LIKE ? ESCAPE '\\'")
        where_params.append(_like_param(mime_type.lower()))

    # Require all requested tags to exist in either entities or tags_json
    for tag in tags:
        where_clauses.append(
            """
            (
                EXISTS (
                    SELECT 1
                    FROM entities et
                    WHERE et.file_id = f.id
                      AND LOWER(et.entity_type) = 'tag'
                      AND LOWER(et.entity_value) = ?
                )
                OR LOWER(COALESCE(fc.tags_json, '')) LIKE ? ESCAPE '\\'
            )
            """
        )
        where_params.extend([tag, _like_param(tag)])

    query_tokens = _tokenize_query(query)
    if query_tokens:
        token_clauses: list[str] = []

        for token in query_tokens:
            like_value = _like_param(token.lower())
            token_clauses.append(
                """
                (
                    LOWER(COALESCE(f.file_name, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(f.source_folder, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.ocr_text, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.image_caption, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.visual_summary, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.extracted_text, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.content_summary, '')) LIKE ? ESCAPE '\\'
                    OR LOWER(COALESCE(fc.tags_json, '')) LIKE ? ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1
                        FROM entities eq
                        WHERE eq.file_id = f.id
                          AND LOWER(eq.entity_type) = 'tag'
                          AND LOWER(eq.entity_value) LIKE ? ESCAPE '\\'
                    )
                )
                """
            )
            where_params.extend([like_value] * 9)

        where_clauses.append("(" + " AND ".join(token_clauses) + ")")

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    whole_query_like = _like_param(query.lower()) if query else ""

    score_sql = """
        (
            CASE
                WHEN ? != '' AND LOWER(COALESCE(f.file_name, '')) = LOWER(?) THEN 140
                WHEN ? != '' AND LOWER(COALESCE(f.file_name, '')) LIKE ? ESCAPE '\\' THEN 90
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(f.source_folder, '')) LIKE ? ESCAPE '\\' THEN 30
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.image_caption, '')) LIKE ? ESCAPE '\\' THEN 45
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.visual_summary, '')) LIKE ? ESCAPE '\\' THEN 45
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.ocr_text, '')) LIKE ? ESCAPE '\\' THEN 28
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.extracted_text, '')) LIKE ? ESCAPE '\\' THEN 24
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.content_summary, '')) LIKE ? ESCAPE '\\' THEN 26
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND LOWER(COALESCE(fc.tags_json, '')) LIKE ? ESCAPE '\\' THEN 22
                ELSE 0
            END
            +
            CASE
                WHEN ? != '' AND EXISTS (
                    SELECT 1
                    FROM entities es
                    WHERE es.file_id = f.id
                      AND LOWER(es.entity_type) = 'tag'
                      AND LOWER(es.entity_value) LIKE ? ESCAPE '\\'
                ) THEN 35
                ELSE 0
            END
        )
    """

    whole_query_like = _like_param(query.lower()) if query else ""

    score_params = [
        # file_name exact
        query, query,
        # file_name like
        query, whole_query_like,
        # source_folder
        query, whole_query_like,
        # image_caption
        query, whole_query_like,
        # visual_summary
        query, whole_query_like,
        # ocr_text
        query, whole_query_like,
        # extracted_text
        query, whole_query_like,
        # content_summary
        query, whole_query_like,
        # tags_json
        query, whole_query_like,
        # entities tag
        query, whole_query_like,
    ]

    sql = f"""
        SELECT
            f.id AS file_id,
            f.drive_file_id,
            f.file_name,
            f.mime_type,
            f.source_folder,
            f.drive_web_link,
            f.file_category,
            f.processing_status,
            f.drive_created_time,
            f.drive_modified_time,
            f.exif_capture_time,
            f.first_seen_at,
            f.last_processed_at,
            fc.extracted_text,
            fc.ocr_text,
            fc.image_caption,
            fc.visual_summary,
            fc.content_summary,
            fc.tags_json,
            (
                SELECT GROUP_CONCAT(e.entity_value, '||')
                FROM entities e
                WHERE e.file_id = f.id
                  AND LOWER(e.entity_type) = 'tag'
            ) AS entity_tags,
            {score_sql} AS score
        FROM files f
        LEFT JOIN file_content fc
            ON fc.file_id = f.id
        {where_sql}
        ORDER BY
            score DESC,
            ({date_expr}) DESC,
            f.file_name ASC
        LIMIT ?
        OFFSET ?
    """

    final_params = score_params + where_params + [filters.limit, filters.offset]
    rows = conn.execute(sql, final_params).fetchall()
    results = [_row_to_result(row) for row in rows]
    return [
        _explain_match(result, query=filters.query, requested_tags=filters.tags)
        for result in results
    ]


def search_sqlite_by_query(
        conn: sqlite3.Connection,
        query: str,
        limit: int = 25,
        offset: int = 0,
) -> list[dict[str, Any]]:
    return search_sqlite_metadata(
        conn,
        SearchFilters(
            query=query,
            limit=limit,
            offset=offset,
        ),
    )


def search_sqlite_by_tags(
        conn: sqlite3.Connection,
        tags: Iterable[str],
        limit: int = 25,
        offset: int = 0,
) -> list[dict[str, Any]]:
    return search_sqlite_metadata(
        conn,
        SearchFilters(
            tags=list(tags),
            limit=limit,
            offset=offset,
        ),
    )


def search_sqlite_by_file_name(
        conn: sqlite3.Connection,
        file_name: str,
        limit: int = 25,
        offset: int = 0,
) -> list[dict[str, Any]]:
    return search_sqlite_metadata(
        conn,
        SearchFilters(
            file_name=file_name,
            limit=limit,
            offset=offset,
        ),
    )


def search_sqlite_by_date_range(
        conn: sqlite3.Connection,
        date_from: str | None = None,
        date_to: str | None = None,
        date_field: str = "best_available",
        limit: int = 25,
        offset: int = 0,
) -> list[dict[str, Any]]:
    return search_sqlite_metadata(
        conn,
        SearchFilters(
            date_from=date_from,
            date_to=date_to,
            date_field=date_field,
            limit=limit,
            offset=offset,
        ),
    )


def get_file_by_id(
    conn: sqlite3.Connection,
    file_id: int,
) -> dict[str, Any] | None:
    """
    Fetch file-level metadata from SQLite.

    SQLite should be the source of truth for file metadata like:
    - drive_web_link
    - drive_created_time
    - drive_modified_time
    - exif_capture_time
    - first_seen_at
    - last_synced_at
    - last_processed_at
    """

    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT
            id,
            drive_file_id,
            file_name,
            mime_type,
            source_folder,
            drive_web_link,
            drive_created_time,
            drive_modified_time,
            exif_capture_time,
            first_seen_at,
            last_synced_at,
            last_processed_at,
            file_category,
            processing_status
        FROM files
        WHERE id = ?
        """,
        (file_id,),
    ).fetchone()

    if row is None:
        return None

    return dict(row)


def merge_result_into_file(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    existing_reasons = existing.setdefault("match_reasons", [])
    existing_reasons.append(build_match_reason(incoming))

    existing["match_count"] = len(existing_reasons)

    incoming_rank_score = calculate_result_score(incoming, query)
    existing_rank_score = normalize_score(existing.get("rank_score"))

    existing["rank_score"] = round(existing_rank_score + incoming_rank_score, 6)

    existing["best_match_score"] = max(
        normalize_score(existing.get("best_match_score")),
        incoming_rank_score,
    )

    existing["matched_sources"] = sorted(
        set(existing.get("matched_sources", []))
        | {str(incoming.get("source"))}
    )

    existing["matched_types"] = sorted(
        set(existing.get("matched_types", []))
        | {str(incoming.get("match_type"))}
    )

    if incoming.get("chunk_type"):
        existing["matched_chunk_types"] = sorted(
            set(existing.get("matched_chunk_types", []))
            | {str(incoming.get("chunk_type"))}
        )

    # Prefer non-empty metadata from incoming
    for field in [
        "file_id",
        "file_name",
        "drive_file_id",
        "drive_web_link",
        "mime_type",
        "source_folder",
        "drive_created_time",
        "drive_modified_time",
        "exif_capture_time",
        "first_seen_at",
        "last_synced_at",
        "last_processed_at",
        "created_at",
        "file_category",
        "processing_status",
    ]:
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming.get(field)

    return existing


def search_all(
    conn: sqlite3.Connection,
    collection: Collection,
    query: str,
    limit: int = 10,
    semantic_limit: int = 25,
    include_ocr: bool = False,
) -> list[dict[str, Any]]:
    """
    Search across SQLite and ChromaDB, merge results by file_id,
    and return one ranked list.

    Sources:
    - SQLite exact / metadata query
    - SQLite filename search
    - SQLite tag search
    - Chroma semantic search
    """

    if not query or not query.strip():
        return []

    query = query.strip()

    all_results: list[dict[str, Any]] = []

    # 1. SQLite broad metadata/text query
    try:
        sqlite_query_results = search_sqlite_by_query(
            conn=conn,
            query=query,
            limit=limit * 3,
        )

        for item in sqlite_query_results:
            item["source"] = item.get("source") or "sqlite"
            item["match_type"] = item.get("match_type") or "exact_query"
            all_results.append(item)

    except Exception as error:
        all_results.append(
            {
                "source": "sqlite",
                "match_type": "exact_query",
                "error": str(error),
                "score": 0,
            }
        )

    # 2. SQLite filename search
    try:
        filename_results = search_sqlite_by_file_name(
            conn=conn,
            file_name=query,
            limit=limit * 3,
        )

        for item in filename_results:
            item["source"] = item.get("source") or "sqlite"
            item["match_type"] = item.get("match_type") or "file_name"
            all_results.append(item)

    except Exception as error:
        all_results.append(
            {
                "source": "sqlite",
                "match_type": "file_name",
                "error": str(error),
                "score": 0,
            }
        )

    # 3. SQLite tag search
    try:
        tag_results = search_sqlite_by_tags(
            conn=conn,
            tags=[query],
            limit=limit * 3,
        )

        for item in tag_results:
            item["source"] = item.get("source") or "sqlite"
            item["match_type"] = item.get("match_type") or "tag"
            all_results.append(item)

    except Exception as error:
        all_results.append(
            {
                "source": "sqlite",
                "match_type": "tag",
                "error": str(error),
                "score": 0,
            }
        )

    # 4. Chroma semantic search
    semantic_chunk_types = [
        "visual_summary",
        "image_caption",
        "extracted_text",
    ]

    if include_ocr:
        semantic_chunk_types.append("ocr_text")

    try:
        semantic_results = semantic_search_chroma(
            collection=collection,
            conn=conn,
            query=query,
            limit=semantic_limit,
            chunk_types=semantic_chunk_types,
        )

        for item in semantic_results:
            item["source"] = item.get("source") or "chroma"
            item["match_type"] = item.get("match_type") or "semantic"
            all_results.append(item)

    except Exception as error:
        all_results.append(
            {
                "source": "chroma",
                "match_type": "semantic",
                "error": str(error),
                "score": 0,
            }
        )

    # 5. Merge by file_id
    merged_by_file: dict[Any, dict[str, Any]] = {}

    for item in all_results:
        if item.get("error"):
            continue

        file_key = get_result_file_id(item)

        if not file_key:
            continue

        if file_key not in merged_by_file:
            base = {
                "file_id": item.get("file_id") or item.get("id"),
                "file_name": item.get("file_name"),
                "drive_file_id": item.get("drive_file_id"),
                "drive_web_link": item.get("drive_web_link"),
                "mime_type": item.get("mime_type"),
                "source_folder": item.get("source_folder"),
                "drive_created_time": item.get("drive_created_time"),
                "drive_modified_time": item.get("drive_modified_time"),
                "exif_capture_time": item.get("exif_capture_time"),
                "first_seen_at": item.get("first_seen_at"),
                "last_synced_at": item.get("last_synced_at"),
                "last_processed_at": item.get("last_processed_at"),
                "created_at": item.get("created_at"),
                "file_category": item.get("file_category"),
                "processing_status": item.get("processing_status"),
                "rank_score": 0.0,
                "best_match_score": 0.0,
                "match_count": 0,
                "matched_sources": [],
                "matched_types": [],
                "matched_chunk_types": [],
                "match_reasons": [],
            }

            merged_by_file[file_key] = base

        merge_result_into_file(
            existing=merged_by_file[file_key],
            incoming=item,
            query=query,
        )

    ranked_results = list(merged_by_file.values())

    # 6. Extra bonus for files with multiple independent signals
    for item in ranked_results:
        source_count = len(item.get("matched_sources", []))
        type_count = len(item.get("matched_types", []))
        match_count = item.get("match_count", 0)

        multi_signal_boost = 0.0

        if source_count >= 2:
            multi_signal_boost += 0.30

        if type_count >= 2:
            multi_signal_boost += 0.20

        if match_count >= 3:
            multi_signal_boost += 0.15

        item["multi_signal_boost"] = round(multi_signal_boost, 6)
        item["rank_score"] = round(
            normalize_score(item.get("rank_score")) + multi_signal_boost,
            6,
        )

    # 7. Sort final results
    ranked_results.sort(
        key=lambda item: (
            item.get("rank_score") or 0,
            item.get("best_match_score") or 0,
            item.get("match_count") or 0,
        ),
        reverse=True,
    )

    return ranked_results[:limit]

