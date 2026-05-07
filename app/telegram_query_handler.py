import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from app.config import SQLITE_DB_PATH
from app.chroma_config import get_chroma_client, get_or_create_collection
from app.drive_service import get_drive_service

# Replace this import path with the actual file that contains search_all
from app.search_service import search_all

# If download_drive_file currently lives in process_files.py, reuse it from there.
from app.process_files import download_drive_file

QUERY_RESULTS_DIR = Path("data/telegram_query_results")
QUERY_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


async def send_search_result(message, result: dict) -> None:
    file_path, should_delete = await asyncio.to_thread(resolve_file_path, result)

    try:
        summary = (result.get("visual_summary") or "").strip()
        if len(summary) > 300:
            summary = summary[:300] + "..."

        position = result.get("_result_position")
        total = result.get("_result_total")

        caption_parts = []

        if position and total:
            caption_parts.append(f"Result {position}/{total}")

        caption_parts.append(f"Best match: {result.get('file_name', 'Unknown file')}")

        if summary:
            caption_parts.append(f"Summary: {summary}")

        if result.get("drive_web_link"):
            caption_parts.append(f"Drive: {result['drive_web_link']}")

        caption = "\n\n".join(caption_parts)[:1024]

        mime_type = (result.get("mime_type") or "").lower()

        if mime_type.startswith("image/"):
            with open(file_path, "rb") as photo_file:
                await message.reply_photo(
                    photo=photo_file,
                    caption=caption,
                )
        else:
            with open(file_path, "rb") as document_file:
                await message.reply_document(
                    document=document_file,
                    caption=caption,
                )

    finally:
        if should_delete and file_path.exists():
            file_path.unlink()


def get_file_details(conn: sqlite3.Connection, file_id: int) -> dict | None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            f.id,
            f.file_name,
            f.mime_type,
            f.drive_file_id,
            f.drive_web_link,
            f.local_cache_path,
            fc.visual_summary
        FROM files f
        LEFT JOIN file_content fc
            ON fc.file_id = f.id
        WHERE f.id = ?
        """,
        (file_id,),
    )

    row = cursor.fetchone()
    if not row:
        return None

    return {
        "file_id": row[0],
        "file_name": row[1],
        "mime_type": row[2],
        "drive_file_id": row[3],
        "drive_web_link": row[4],
        "local_cache_path": row[5],
        "visual_summary": row[6] or "",
    }


def find_matching_files(query: str, limit: int = 10) -> list[dict]:
    conn = sqlite3.connect(SQLITE_DB_PATH)

    try:
        chroma_client = get_chroma_client()
        collection = get_or_create_collection(chroma_client)

        results = search_all(
            conn=conn,
            collection=collection,
            query=query,
            limit=limit,
            semantic_limit=25,
            include_ocr=True,
        )

        enriched_results = []

        for result in results:
            file_id = result.get("file_id")
            if not file_id:
                continue

            details = get_file_details(conn, file_id)
            if not details:
                continue

            enriched_results.append({
                **result,
                **details,
            })

        return enriched_results

    finally:
        conn.close()


def resolve_file_path(result: dict) -> tuple[Path, bool]:
    """
    Returns:
      (path, should_delete_after_send)
    """
    local_cache_path = result.get("local_cache_path")
    if local_cache_path:
        local_path = Path(local_cache_path)
        if local_path.exists():
            return local_path, False

    drive_file_id = result.get("drive_file_id")
    file_name = result.get("file_name") or "image.jpg"
    safe_name = file_name.replace("/", "_").replace("\\", "_")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_path = QUERY_RESULTS_DIR / f"{timestamp}_{result['file_id']}_{safe_name}"

    service = get_drive_service()
    download_drive_file(service, drive_file_id, temp_path)

    return temp_path, True


async def handle_find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    query = " ".join(context.args).strip()

    if not query:
        await message.reply_text("Usage: /find <query>\nExample: /find Liron CV")
        return

    await message.reply_text(f"Searching for a file matching: {query}")

    try:
        results = await asyncio.to_thread(find_matching_files, query, 10)

        if not results:
            context.chat_data.pop("last_search_results", None)
            context.chat_data.pop("last_search_index", None)
            context.chat_data.pop("last_search_query", None)

            await message.reply_text("I couldn't find a matching file.")
            return

        total = len(results)

        for index, result in enumerate(results, start=1):
            result["_result_position"] = index
            result["_result_total"] = total

        context.chat_data["last_search_results"] = results
        context.chat_data["last_search_index"] = 0
        context.chat_data["last_search_query"] = query

        await send_search_result(message, results[0])

        if total > 1:
            await message.reply_text(
                f"I found {total} results. Send /next to get the next one."
            )

    except Exception as e:
        await message.reply_text(f"Failed to search for file: {e}")


async def handle_next_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    results = context.chat_data.get("last_search_results")
    current_index = context.chat_data.get("last_search_index", 0)
    query = context.chat_data.get("last_search_query", "")

    if not results:
        await message.reply_text("No previous search found. Use /find <query> first.")
        return

    next_index = current_index + 1

    if next_index >= len(results):
        await message.reply_text(
            f"No more results for: {query}\nUse /find <query> to start a new search."
        )
        return

    context.chat_data["last_search_index"] = next_index

    try:
        await send_search_result(message, results[next_index])

        remaining = len(results) - next_index - 1
        if remaining > 0:
            await message.reply_text(f"{remaining} more result(s). Send /next again.")
        else:
            await message.reply_text("That was the last result.")

    except Exception as e:
        await message.reply_text(f"Failed to send next result: {e}")