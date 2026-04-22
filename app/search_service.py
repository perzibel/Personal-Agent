from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable


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