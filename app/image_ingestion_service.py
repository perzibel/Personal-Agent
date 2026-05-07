from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import sqlite3

from app.config import IMAGES_FOLDER, SQLITE_DB_PATH
from app.drive_service import get_drive_service, upload_file_to_drive
from app.chroma_config import get_chroma_client, get_or_create_collection
from app.process_files import process_single_file
from app.file_router import classify_upload_folder
from app.folder_config import get_folder_id
from app.vision_utils import analyze_image_with_vision_model
from app.process_files import extract_image_metadata_and_caption
from app.folder_decision_service import decide_folder_for_file


def analyze_local_image_for_routing(
        local_path: Path,
        caption: Optional[str],
) -> dict:
    visual_summary = ""
    vision_json = "{}"
    image_caption = ""
    ocr_text = ""

    try:
        visual_summary, vision_json = analyze_image_with_vision_model(local_path)
    except Exception as error:
        print(f"Routing visual analysis failed: {error}")

    try:
        image_data = extract_image_metadata_and_caption(
            local_path,
            "telegram",
            local_path.name,
            vision_json or "{}",
        )
        ocr_text = image_data.get("ocr_text") or ""
        image_caption = image_data.get("image_caption") or ""
    except Exception as error:
        print(f"Routing metadata/OCR analysis failed: {error}")

    decision = decide_folder_for_file(
        local_path=local_path,
        mime_type="image/jpeg",
        caption=caption,
        visual_summary=visual_summary,
        ocr_text=ocr_text,
        image_caption=image_caption,
    )

    return {
        "visual_summary": visual_summary,
        "vision_json": vision_json,
        "ocr_text": ocr_text,
        "image_caption": image_caption,
        "decision": decision,
    }


def complete_telegram_image_ingestion(
    local_path: Path,
    folder_name: str,
    telegram_file_id: str,
    telegram_file_unique_id: str,
    caption: Optional[str] = None,
    sender_id: Optional[int] = None,
    routing_reason: Optional[str] = None,
    routing_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    conn = sqlite3.connect(SQLITE_DB_PATH)

    try:
        service = get_drive_service()
        chroma_client = get_chroma_client()
        collection = get_or_create_collection(chroma_client)

        folder_id = get_folder_id(folder_name)

        drive_result = upload_file_to_drive(
            local_path=local_path,
            parent_folder_id=folder_id,
            mime_type="image/jpeg",
        )

        drive_file_id = drive_result["drive_file_id"]
        drive_web_link = drive_result["drive_web_link"]

        file_id = insert_telegram_file_record(
            conn=conn,
            drive_file_id=drive_file_id,
            file_name=local_path.name,
            mime_type="image/jpeg",
            source_folder=folder_name,
            drive_web_link=drive_web_link,
            local_cache_path=str(local_path),
            file_size_bytes=local_path.stat().st_size,
        )

        row = (
            file_id,
            drive_file_id,
            local_path.name,
            "image/jpeg",
            folder_name,
            datetime.now(timezone.utc).isoformat(),
        )

        process_single_file(
            conn=conn,
            service=service,
            collection=collection,
            row=row,
        )

        visual_summary = get_visual_summary_for_file(conn, file_id)

        return {
            "file_id": file_id,
            "file_name": local_path.name,
            "mime_type": "image/jpeg",
            "source_folder": folder_name,
            "selected_folder": folder_name,
            "drive_file_id": drive_file_id,
            "drive_web_link": drive_web_link,
            "local_cache_path": str(local_path),
            "telegram_file_id": telegram_file_id,
            "telegram_file_unique_id": telegram_file_unique_id,
            "telegram_caption": caption,
            "telegram_sender_id": sender_id,
            "visual_summary": visual_summary,
            "routing_reason": routing_reason,
            "routing_confidence": routing_confidence,
        }

    finally:
        conn.close()


def insert_telegram_file_record(
        conn,
        drive_file_id: str,
        file_name: str,
        mime_type: str,
        source_folder: str,
        drive_web_link: str,
        local_cache_path: str,
        file_size_bytes: int,
) -> int:
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO files (
            drive_file_id,
            file_name,
            mime_type,
            source_folder,
            drive_web_link,
            local_cache_path,
            file_size_bytes,
            drive_created_time,
            drive_modified_time,
            first_seen_at,
            last_synced_at,
            processing_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            drive_file_id,
            file_name,
            mime_type,
            source_folder,
            drive_web_link,
            local_cache_path,
            file_size_bytes,
            now,
            now,
            now,
            now,
            "pending",
        ),
    )

    conn.commit()
    return cursor.lastrowid


def get_visual_summary_for_file(conn, file_id: int) -> str:
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT visual_summary
        FROM file_content
        WHERE file_id = ?
        """,
        (file_id,),
    )

    row = cursor.fetchone()
    return row[0] if row and row[0] else ""


def ingest_telegram_image(
        local_path: Path,
        telegram_file_id: str,
        telegram_file_unique_id: str,
        caption: Optional[str] = None,
        sender_id: Optional[int] = None,
        chat_id: Optional[int] = None,
) -> Dict[str, Any]:
    routing_analysis = analyze_local_image_for_routing(
        local_path=local_path,
        caption=caption,
    )

    decision = routing_analysis["decision"]

    if decision["needs_user_choice"]:
        return {
            "status": "needs_user_choice",
            "local_path": str(local_path),
            "file_name": local_path.name,
            "mime_type": "image/jpeg",
            "telegram_file_id": telegram_file_id,
            "telegram_file_unique_id": telegram_file_unique_id,
            "telegram_caption": caption,
            "telegram_sender_id": sender_id,
            "candidate_folders": decision["candidate_folders"],
            "routing_reason": decision["reason"],
            "visual_summary": routing_analysis.get("visual_summary") or "",
        }

    result = complete_telegram_image_ingestion(
        local_path=local_path,
        folder_name=decision["folder_name"],
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        caption=caption,
        sender_id=sender_id,
    )

    result["routing_reason"] = decision["reason"]
    result["routing_confidence"] = decision.get("confidence")
    result["candidate_folders"] = decision.get("candidate_folders", [])

    return result
