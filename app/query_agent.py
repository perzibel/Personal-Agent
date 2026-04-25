from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chromadb.api.models.Collection import Collection

from app.config import SQLITE_DB_PATH
from app.search_service import classify_query_intent, search_all

from enum import Enum


class QueryMode(str, Enum):
    FILE_SEARCH = "file_search"
    IMAGE_SEARCH = "image_search"
    DATE_BASED_SEARCH = "date_based_search"
    DOCUMENT_SUMMARY = "document_summary"
    QA = "qa"
    ACTION_EXTRACTION = "action_extraction"
    DEBUG_EXPLANATION = "debug_explanation"


@dataclass
class QueryIntent:
    original_query: str
    mode: QueryMode
    retrieval_query: str
    include_ocr: bool = False
    needs_semantic: bool = True
    needs_latest_sort: bool = False
    needs_oldest_sort: bool = False
    target_file_type: str | None = None
    target_mime_type: str | None = None
    wants_debug: bool = False
    wants_summary: bool = False
    wants_actions: bool = False


@dataclass
class QueryAgentResponse:
    query: str
    retrieval_query: str
    intent: QueryIntent
    answer: str
    context: str
    results: list[dict[str, Any]]


GENERIC_FILE_TERMS = {
    "cv",
    "resume",
    "curriculum",
    "vitae",
    "pdf",
    "doc",
    "docx",
    "document",
    "file",
    "files",
    "image",
    "photo",
    "picture",
    "screenshot",
}


def extract_required_terms(retrieval_query: str) -> list[str]:
    """
    Extract specific terms that must appear in the result.

    Example:
    'liron cv' -> ['liron']
    'dor resume' -> ['dor']
    'cv' -> []
    """
    tokens = [
        token.strip().lower()
        for token in retrieval_query.split()
        if token.strip()
    ]

    return [
        token
        for token in tokens
        if token not in GENERIC_FILE_TERMS and len(token) >= 3
    ]


def result_contains_required_terms(
        item: dict[str, Any],
        required_terms: list[str],
) -> bool:
    if not required_terms:
        return True

    searchable_parts: list[str] = [
        str(item.get("file_name") or ""),
        str(item.get("source_folder") or ""),
        str(item.get("mime_type") or ""),
        str(item.get("file_category") or ""),
    ]

    for reason in item.get("match_reasons", []) or []:
        searchable_parts.append(str(reason.get("text_preview") or ""))

        why = reason.get("why_matched") or {}
        searchable_parts.append(str(why.get("matched_text_preview") or ""))

        snippets = reason.get("match_snippets") or {}
        if isinstance(snippets, dict):
            searchable_parts.extend(str(value) for value in snippets.values())

    searchable_text = " ".join(searchable_parts).lower()

    return all(term in searchable_text for term in required_terms)


def filter_results_by_required_terms(
        results: list[dict[str, Any]],
        required_terms: list[str],
) -> list[dict[str, Any]]:
    if not required_terms:
        return results

    filtered = [
        item for item in results
        if result_contains_required_terms(
            item=item,
            required_terms=required_terms,
        )
    ]

    return filtered


def route_query_intent(query: str) -> QueryIntent:
    q = query.strip()
    q_lower = q.lower()

    image_terms = {
        "image",
        "images",
        "photo",
        "photos",
        "picture",
        "pictures",
        "pic",
        "pics",
        "screenshot",
        "screenshots",
        "jpg",
        "jpeg",
        "png",
        "heic",
        "webp",
    }

    document_terms = {
        "document",
        "documents",
        "doc",
        "docs",
        "pdf",
        "word",
        "docx",
        "cv",
        "resume",
        "file",
        "files",
    }

    latest_terms = {
        "latest",
        "last",
        "newest",
        "recent",
        "most recent",
    }

    oldest_terms = {
        "first",
        "oldest",
        "earliest",
    }

    summary_terms = {
        "summarize",
        "summary",
        "explain this document",
        "what is this document about",
        "what does this file say",
    }

    qa_terms = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "does",
        "do",
        "is",
        "are",
    }

    action_terms = {
        "action",
        "actions",
        "todo",
        "todos",
        "task",
        "tasks",
        "next steps",
        "follow up",
        "follow-up",
        "extract action",
        "extract actions",
    }

    debug_terms = {
        "why did",
        "why matched",
        "why was this",
        "debug",
        "explain match",
        "explain results",
        "why result",
        "why returned",
    }

    words = set(q_lower.replace("?", " ").replace(".", " ").split())

    has_image_word = bool(words & image_terms)
    has_document_word = bool(words & document_terms)

    asks_latest = any(term in q_lower for term in latest_terms)
    asks_oldest = any(term in q_lower for term in oldest_terms)

    wants_summary = any(term in q_lower for term in summary_terms)
    wants_actions = any(term in q_lower for term in action_terms)
    wants_debug = any(term in q_lower for term in debug_terms)

    starts_like_question = any(q_lower.startswith(term + " ") for term in qa_terms)

    retrieval_query = build_retrieval_query(query=q)

    target_file_type = None
    target_mime_type = None

    if has_image_word:
        target_file_type = "image"

    if "pdf" in words:
        target_file_type = "document"
        target_mime_type = "application/pdf"

    if "docx" in words or "word" in words:
        target_file_type = "document"
        target_mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if "cv" in words or "resume" in words:
        target_file_type = "document"

    if wants_debug:
        mode = QueryMode.DEBUG_EXPLANATION
    elif wants_actions:
        mode = QueryMode.ACTION_EXTRACTION
    elif wants_summary:
        mode = QueryMode.DOCUMENT_SUMMARY
    elif asks_latest or asks_oldest:
        mode = QueryMode.DATE_BASED_SEARCH
    elif has_image_word:
        mode = QueryMode.IMAGE_SEARCH
    elif starts_like_question:
        mode = QueryMode.QA
    else:
        mode = QueryMode.FILE_SEARCH

    return QueryIntent(
        original_query=q,
        mode=mode,
        retrieval_query=retrieval_query,
        include_ocr=has_image_word,
        needs_semantic=not wants_debug,
        needs_latest_sort=asks_latest,
        needs_oldest_sort=asks_oldest,
        target_file_type=target_file_type,
        target_mime_type=target_mime_type,
        wants_debug=wants_debug,
        wants_summary=wants_summary,
        wants_actions=wants_actions,
    )


def build_retrieval_query(query: str) -> str:
    """
    Convert a natural-language user question into a cleaner retrieval query.

    Examples:
    'show me the latest document that is a CV' -> 'cv'
    'show me liron CV' -> 'liron cv'
    'find dor resume' -> 'dor resume'
    """
    q = query.lower().strip()

    stop_words = {
        "show",
        "me",
        "the",
        "a",
        "an",
        "that",
        "is",
        "are",
        "was",
        "were",
        "latest",
        "last",
        "newest",
        "recent",
        "most",
        "document",
        "documents",
        "file",
        "files",
        "image",
        "images",
        "photo",
        "photos",
        "picture",
        "pictures",
        "please",
        "find",
        "get",
        "give",
        "bring",
    }

    normalized = (
        q.replace("?", " ")
        .replace(".", " ")
        .replace(",", " ")
        .replace("-", " ")
        .replace("_", " ")
    )

    tokens = [
        token.strip()
        for token in normalized.split()
        if token.strip() and token.strip() not in stop_words
    ]

    if not tokens:
        return query.strip()

    return " ".join(tokens)


def is_document_like_result(item: dict[str, Any]) -> bool:
    mime_type = str(item.get("mime_type") or "").lower()
    file_name = str(item.get("file_name") or "").lower()
    file_category = str(item.get("file_category") or "").lower()

    if file_category in {"document", "pdf", "word", "spreadsheet"}:
        return True

    if mime_type in {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        return True

    return file_name.endswith((
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".txt",
    ))


def parse_sortable_datetime(value: str | None):
    if not value:
        return None

    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_document_event_datetime(item: dict[str, Any]):
    """
    For latest document questions, prefer:
    1. Drive created time
    2. Drive modified time
    3. first_seen_at
    4. last_processed_at
    """
    for field_name in [
        "drive_created_time",
        "drive_modified_time",
        "first_seen_at",
        "last_processed_at",
        "created_at",
    ]:
        parsed = parse_sortable_datetime(item.get(field_name))
        if parsed is not None:
            return parsed

    return None


def apply_agent_post_ranking(
        results: list[dict[str, Any]],
        original_query: str,
        intent: QueryIntent,
) -> list[dict[str, Any]]:
    q = original_query.lower()

    asks_latest = intent.needs_latest_sort
    asks_oldest = intent.needs_oldest_sort

    asks_document = (
            intent.target_file_type == "document"
            or any(
        word in q
        for word in ["document", "documents", "file", "files", "cv", "resume", "pdf", "docx"]
    )
    )

    if (asks_latest or asks_oldest) and asks_document:
        document_results = [
            item for item in results
            if is_document_like_result(item)
        ]

        for item in document_results:
            doc_date = get_document_event_datetime(item)
            item["document_event_datetime"] = doc_date.isoformat() if doc_date else None

        document_results.sort(
            key=lambda item: (
                get_document_event_datetime(item) is not None,
                get_document_event_datetime(item) or "",
                item.get("rank_score") or 0,
            ),
            reverse=asks_latest,
        )

        return document_results

    return results

def _clip_text(value: str | None, max_chars: int) -> str:
    if not value:
        return ""

    value = str(value).strip()

    if len(value) <= max_chars:
        return value

    return value[:max_chars].rstrip() + "..."


def _extract_best_reason(item: dict[str, Any]) -> dict[str, Any]:
    reasons = item.get("match_reasons") or []

    if not reasons:
        return {}

    # Prefer the reason with the strongest score breakdown if available.
    def reason_score(reason: dict[str, Any]) -> float:
        breakdown = reason.get("score_breakdown") or {}
        try:
            return float(breakdown.get("final_score") or reason.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0

    return sorted(reasons, key=reason_score, reverse=True)[0]


def _extract_reason_preview(reason: dict[str, Any]) -> str:
    why = reason.get("why_matched") or {}

    return (
        why.get("matched_text_preview")
        or reason.get("text_preview")
        or ""
    )


def build_llm_context_pack(
    results: list[dict[str, Any]],
    max_results: int = 5,
    max_ocr_chars: int = 700,
    max_extracted_text_chars: int = 1200,
    max_visual_summary_chars: int = 700,
    max_reason_chars: int = 500,
) -> str:
    """
    Convert top ranked retrieval results into compact LLM-ready context.

    Includes:
    - file name
    - Drive link
    - dates
    - OCR
    - extracted text
    - visual summary
    - matched reason
    - score/debug metadata
    """

    context_blocks: list[str] = []

    for index, item in enumerate(results[:max_results], start=1):
        reason = _extract_best_reason(item)
        explanation = item.get("explanation") or {}

        reason_preview = _extract_reason_preview(reason)

        score_breakdown = reason.get("score_breakdown") or {}
        date_boost = explanation.get("date_boost") or {}

        block = f"""
[Result {index}]
File name: {item.get("file_name")}
File ID: {item.get("file_id")}
Drive link: {item.get("drive_web_link")}
MIME type: {item.get("mime_type")}
Source folder: {item.get("source_folder")}
File category: {item.get("file_category")}

Dates:
- Created at: {item.get("created_at")}
- Drive created: {item.get("drive_created_time")}
- Drive modified: {item.get("drive_modified_time")}
- EXIF capture time: {item.get("exif_capture_time")}
- First seen: {item.get("first_seen_at")}
- Last processed: {item.get("last_processed_at")}
- Document event datetime: {item.get("document_event_datetime")}
- Image event datetime: {item.get("image_event_datetime")}

Ranking:
- Rank score: {item.get("rank_score")}
- Best match score: {item.get("best_match_score")}
- Match count: {item.get("match_count")}
- Matched sources: {item.get("matched_sources")}
- Matched types: {item.get("matched_types")}
- Matched chunk types: {item.get("matched_chunk_types")}

Matched reason:
- Source: {reason.get("source")}
- Match type: {reason.get("match_type")}
- Chunk type: {reason.get("chunk_type")}
- Chroma distance: {reason.get("distance")}
- Matched fields: {reason.get("matched_fields")}
- Matched terms: {reason.get("matched_terms")}
- Reason: {(reason.get("why_matched") or {}).get("reason")}
- Preview: {_clip_text(reason_preview, max_reason_chars)}

Score breakdown:
- Raw score: {score_breakdown.get("raw_score")}
- Match type weight: {score_breakdown.get("match_type_weight")}
- Chunk type weight: {score_breakdown.get("chunk_type_weight")}
- Keyword boost: {score_breakdown.get("keyword_boost")}
- Final score: {score_breakdown.get("final_score")}

Date boost:
- Applied: {date_boost.get("applied")}
- Reason: {date_boost.get("reason")}
- Date field: {date_boost.get("date_field")}
- Date value: {date_boost.get("date_value")}

Visual summary:
{_clip_text(item.get("visual_summary"), max_visual_summary_chars)}

OCR text:
{_clip_text(item.get("ocr_text"), max_ocr_chars)}

Extracted text:
{_clip_text(item.get("extracted_text"), max_extracted_text_chars)}
""".strip()

        context_blocks.append(block)

    return "\n\n---\n\n".join(context_blocks)


def build_answer_context(
        results: list[dict[str, Any]],
        max_results: int = 5,
) -> str:
    context_parts: list[str] = []

    for index, item in enumerate(results[:max_results], start=1):
        reasons = item.get("match_reasons") or []

        reason_lines = []
        for reason in reasons[:3]:
            why = reason.get("why_matched") or {}
            reason_lines.append(
                "\n".join(
                    [
                        f"- Source: {reason.get('source')}",
                        f"  Type: {reason.get('match_type')}",
                        f"  Chunk: {reason.get('chunk_type')}",
                        f"  Score: {reason.get('score')}",
                        f"  Distance: {reason.get('distance')}",
                        f"  Reason: {why.get('reason')}",
                        f"  Preview: {why.get('matched_text_preview') or reason.get('text_preview')}",
                    ]
                )
            )

        context_parts.append(
            "\n".join(
                [
                    f"Result #{index}",
                    f"File: {item.get('file_name')}",
                    f"File ID: {item.get('file_id')}",
                    f"Link: {item.get('drive_web_link')}",
                    f"MIME type: {item.get('mime_type')}",
                    f"Source folder: {item.get('source_folder')}",
                    f"File category: {item.get('file_category')}",
                    f"Created at: {item.get('created_at')}",
                    f"Drive created: {item.get('drive_created_time')}",
                    f"Drive modified: {item.get('drive_modified_time')}",
                    f"EXIF capture time: {item.get('exif_capture_time')}",
                    f"Rank score: {item.get('rank_score')}",
                    f"Best match score: {item.get('best_match_score')}",
                    f"Match count: {item.get('match_count')}",
                    f"Matched sources: {item.get('matched_sources')}",
                    f"Matched types: {item.get('matched_types')}",
                    f"Matched chunk types: {item.get('matched_chunk_types')}",
                    "Reasons:",
                    "\n".join(reason_lines),
                ]
            )
        )

    return "\n\n---\n\n".join(context_parts)


def generate_answer(
        query: str,
        intent: QueryIntent,
        results: list[dict[str, Any]],
) -> str:
    if not results:
        return "I could not find matching files for this question."

    if intent.mode == QueryMode.DATE_BASED_SEARCH and intent.needs_oldest_sort:
        title = "The earliest matching file I found is:"
        max_items = 1
    elif intent.mode == QueryMode.DATE_BASED_SEARCH and intent.needs_latest_sort:
        title = "The latest matching file I found is:"
        max_items = 1
    elif intent.mode == QueryMode.IMAGE_SEARCH:
        title = "Here are the strongest image matches I found:"
        max_items = 5
    elif intent.mode == QueryMode.DOCUMENT_SUMMARY:
        title = "I found this document to summarize:"
        max_items = 1
    elif intent.mode == QueryMode.ACTION_EXTRACTION:
        title = "I found this document for action extraction:"
        max_items = 1
    elif intent.mode == QueryMode.DEBUG_EXPLANATION:
        title = "Here is why the strongest matches were returned:"
        max_items = 5
    else:
        title = "Here are the strongest matches I found:"
        max_items = 5

    lines = [title, ""]

    for index, item in enumerate(results[:max_items], start=1):
        lines.append(f"{index}. {item.get('file_name')}")
        lines.append(f"   Link: {item.get('drive_web_link')}")
        lines.append(f"   MIME type: {item.get('mime_type')}")
        lines.append(f"   Rank score: {item.get('rank_score')}")
        lines.append(f"   Match count: {item.get('match_count')}")

        if item.get("document_event_datetime"):
            lines.append(f"   Document date: {item.get('document_event_datetime')}")
        elif item.get("image_event_datetime"):
            lines.append(f"   Image date: {item.get('image_event_datetime')}")
        elif item.get("exif_capture_time"):
            lines.append(f"   EXIF capture time: {item.get('exif_capture_time')}")
        elif item.get("drive_created_time"):
            lines.append(f"   Drive created time: {item.get('drive_created_time')}")
        elif item.get("drive_modified_time"):
            lines.append(f"   Drive modified time: {item.get('drive_modified_time')}")

        reasons = item.get("match_reasons") or []
        if reasons:
            first_reason = reasons[0]
            why = first_reason.get("why_matched") or {}

            reason_text = why.get("reason")
            preview = why.get("matched_text_preview") or first_reason.get("text_preview")

            if reason_text:
                lines.append(f"   Why: {reason_text}")

            if preview:
                lines.append(f"   Preview: {preview}")

        lines.append("")

    return "\n".join(lines).strip()


def query_agent(
        query: str,
        collection: Collection,
        sqlite_db_path: str | Path = SQLITE_DB_PATH,
        limit: int = 10,
        semantic_limit: int = 25,
        include_ocr: bool | None = None,
) -> QueryAgentResponse:
    query = query.strip()

    if not query:
        return QueryAgentResponse(
            query=query,
            retrieval_query="",
            intent={},
            answer="Please provide a non-empty question.",
            context="",
            results=[],
        )

    intent = route_query_intent(query)

    if include_ocr is None:
        include_ocr = intent.include_ocr

    conn = sqlite3.connect(sqlite_db_path)

    try:
        retrieval_query = intent.retrieval_query

        results = search_all(
            conn=conn,
            collection=collection,
            query=retrieval_query,
            limit=limit,
            semantic_limit=semantic_limit,
            include_ocr=include_ocr,
        )

        required_terms = extract_required_terms(retrieval_query)

        results = filter_results_by_required_terms(
            results=results,
            required_terms=required_terms,
        )

        results = apply_agent_post_ranking(
            results=results,
            original_query=query,
            intent=intent,
        )

        context = build_llm_context_pack(results)

        answer = generate_answer(
            query=query,
            intent=intent,
            results=results,
        )

        return QueryAgentResponse(
            query=query,
            retrieval_query=retrieval_query,
            intent=intent,
            answer=answer,
            context=context,
            results=results,
        )

    finally:
        conn.close()
