from __future__ import annotations

import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from app.vision_utils import analyze_image_with_vision_model

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from docx import Document as DocxDocument
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.chroma_config import get_chroma_client, get_or_create_collection
from app.config import (
    SQLITE_DB_PATH,
    GOOGLE_OAUTH_CREDENTIALS,
    GOOGLE_TOKEN_PATH,
    TEMP_DOWNLOAD_DIR,
    TESSERACT_CMD,
    VISION_ENABLED,
    VISION_MODEL_NAME,
    VISION_GENERATE_SUMMARY,
    VISION_GENERATE_JSON,
)

SCOPES = [
    scope.strip()
    for scope in os.getenv("GOOGLE_SCOPES", "").split(",")
    if scope.strip()
]

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_supported_mvp_type(mime_type: str, suffix_lower: str) -> bool:
    mime_lower = (mime_type or "").lower()

    if mime_lower == "application/pdf" or suffix_lower == ".pdf":
        return True
    if "wordprocessingml" in mime_lower or suffix_lower == ".docx":
        return True
    if mime_lower.startswith("text/") or suffix_lower == ".txt":
        return True
    if mime_lower.startswith("image/") or suffix_lower in [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]:
        return True

    return False


def get_db_connection():
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_drive_service():
    creds = None

    if GOOGLE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GOOGLE_OAUTH_CREDENTIALS),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        GOOGLE_TOKEN_PATH.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def fetch_pending_files(conn, limit: int = 20):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, drive_file_id, file_name, mime_type, source_folder, drive_modified_time
        FROM files
        WHERE processing_status = 'pending'
        ORDER BY drive_modified_time DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cursor.fetchall()


def mark_file_processing_status(
        conn,
        file_id: int,
        status: str,
        error: Optional[str] = None,
):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE files
        SET processing_status = ?,
            processing_error = ?,
            last_processed_at = ?
        WHERE id = ?
        """,
        (status, error, utc_now_iso(), file_id),
    )
    conn.commit()


def update_exif_capture_time(conn, file_id: int, exif_capture_time: Optional[str]):
    if not exif_capture_time:
        return

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE files
        SET exif_capture_time = ?
        WHERE id = ?
        """,
        (exif_capture_time, file_id),
    )
    conn.commit()


def download_drive_file(service, drive_file_id: str, target_path: Path):
    target_path.parent.mkdir(parents=True, exist_ok=True)

    request = service.files().get_media(fileId=drive_file_id)
    fh = io.FileIO(target_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.close()


def extract_text_from_pdf(file_path: Path) -> str:
    doc = fitz.open(file_path)
    try:
        pages = [page.get_text("text") for page in doc]
        return "\n".join(pages).strip()
    finally:
        doc.close()


def extract_text_from_docx(file_path: Path) -> str:
    doc = DocxDocument(file_path)
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extract_text_from_txt(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="ignore").strip()


def extract_ocr_text(file_path: Path) -> str:
    image = Image.open(file_path)
    try:
        return pytesseract.image_to_string(image).strip()
    finally:
        image.close()


def normalize_visual_json(visual_json):
    if visual_json is None:
        return None

    if isinstance(visual_json, dict):
        return visual_json

    if isinstance(visual_json, str):
        visual_json = visual_json.strip()
        if not visual_json:
            return None
        try:
            parsed = json.loads(visual_json)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            return None

    return None


def infer_tags(
        file_name: str = "",
        source_folder: str = "",
        ocr_text: str = "",
        image_caption: str = "",
        visual_summary: str = "",
        visual_json: dict | None = None,
) -> list[str]:
    tags = set()

    file_name_lower = (file_name or "").lower()
    source_lower = (source_folder or "").lower()
    ocr_lower = (ocr_text or "").lower()
    caption_lower = (image_caption or "").lower()
    summary_lower = (visual_summary or "").lower()

    visual_parts = []
    if isinstance(visual_json, dict):
        for key in ["scene_type", "document_type"]:
            value = visual_json.get(key)
            if value:
                visual_parts.append(str(value).lower())

        for key in ["people", "objects", "text_visible", "activities", "brand_names", "locations"]:
            values = visual_json.get(key, [])
            if isinstance(values, list):
                visual_parts.extend(str(v).lower() for v in values if v)

        raw_tags = visual_json.get("tags") or visual_json.get("Tags") or []
        if isinstance(raw_tags, list):
            visual_parts.extend(str(v).lower() for v in raw_tags if v)

    combined = " ".join([
        file_name_lower,
        source_lower,
        ocr_lower,
        caption_lower,
        summary_lower,
        " ".join(visual_parts),
    ])

    # Identity documents
    if any(x in combined for x in [
        "passport", "identity card", "id card", "national id",
        "driver license", "driver's license", "driver licence", "driver's licence",
        "license number", "licence number", "id number", "document number", "CV"
    ]):
        tags.add("identity_doc")
        tags.add("document")

    # Baby / child
    if any(x in combined for x in [
        "baby", "infant", "newborn", "toddler", "child", "mother and child", "parenting"
    ]):
        tags.add("baby_related")

    # Specific baby objects
    if "stroller" in combined:
        tags.add("stroller")
        tags.add("baby_related")

    if "crib" in combined:
        tags.add("crib")
        tags.add("baby_related")

    if any(x in combined for x in ["baby bottle", "bottle feeding", "feeding bottle"]):
        tags.add("baby_bottle")

    # Receipt
    if any(x in combined for x in [
        "receipt", "tax invoice", "invoice", "subtotal", "total", "cash", "visa", "pdf", "cv"
    ]):
        tags.add("receipt")
        tags.add("document")

    # Booking / reservation
    if any(x in combined for x in [
        "booking", "reservation", "check-in", "check out", "check-out",
        "hotel", "flight", "boarding pass", "airbnb", "confirmation number"
    ]):
        tags.add("booking")
        tags.add("document")
        tags.add("travel")

    # Screenshot
    if "screenshot" in combined or file_name_lower.startswith("screenshot_"):
        tags.add("screenshot")

    # Document / form
    if any(x in combined for x in [
        "form", "application", "statement", "certificate", "document",
        "technical support documentation", "knowledge base article"
    ]):
        tags.add("document")

    # Sensitive
    if "identity_doc" in tags:
        tags.add("sensitive")

    return sorted(tags)


def build_image_caption(
        source_folder: str,
        file_name: str,
        ocr_text: str = "",
        visual_json: dict | None = None,
) -> str:
    file_name_lower = (file_name or "").lower()
    source_lower = (source_folder or "").lower()
    ocr_lower = (ocr_text or "").lower()
    visual_json = normalize_visual_json(visual_json)

    if visual_json:
        scene_type = visual_json.get("scene_type")
        document_type = visual_json.get("document_type")
        people = visual_json.get("people", [])
        objects = visual_json.get("objects", [])
        activities = visual_json.get("activities", [])
        text_visible = visual_json.get("text_visible", [])
        brand_names = visual_json.get("brand_names", [])
        tags = visual_json.get("tags", [])

        parts = []

        if document_type:
            parts.append(document_type)

        if scene_type and scene_type != document_type:
            parts.append(f"showing {scene_type.lower()}")

        if people:
            parts.append(f"with {people[0].rstrip('.')}")

        if activities:
            parts.append(f"related to {activities[0].rstrip('.').lower()}")

        # Add a few notable visible elements
        notable_objects = objects[:2]
        if notable_objects:
            parts.append(
                "including " + ", ".join(obj.rstrip(".") for obj in notable_objects)
            )

        if brand_names:
            parts.append(f"associated with {', '.join(brand_names[:2])}")

        if text_visible:
            visible_text = ", ".join(str(x) for x in text_visible[:4])
            parts.append(f"visible text: {visible_text}")

        caption = ", ".join(parts).strip()
        if caption:
            return caption

    if any(x in ocr_lower for x in ["passport", "identity", "driver", "license", "id"]):
        return "Image that may contain an identity document"

    if "receipt" in source_lower or "receipt" in file_name_lower:
        return "Photo or screenshot of a receipt"

    if "screenshot" in source_lower or "screenshot" in file_name_lower:
        return "Screenshot containing visible text or app content"

    if "baby" in source_lower or "baby" in file_name_lower:
        return "Photo likely related to a baby"

    if ocr_text.strip():
        short_ocr = " ".join(ocr_text.split())[:120]
        return f"Image containing visible text: {short_ocr}"

    # 3. Final fallback
    return f"Image from folder '{source_folder}' named '{file_name}'"


def extract_image_metadata_and_caption(file_path: Path, source_folder: str, file_name: str,
                                       visual_json: dict | None = None, ):
    image = Image.open(file_path)
    try:
        exif_capture_time = None
        raw_exif = {}

        exif = image.getexif()
        if exif:
            for tag_id, value in exif.items():
                raw_exif[str(tag_id)] = str(value)

            # 36867 = DateTimeOriginal
            date_original = exif.get(36867)
            if date_original:
                try:
                    exif_capture_time = datetime.strptime(
                        str(date_original), "%Y:%m:%d %H:%M:%S"
                    ).isoformat()
                except ValueError:
                    exif_capture_time = str(date_original)

        ocr_text = pytesseract.image_to_string(image).strip()
        ocr_lower = ocr_text.lower()

        caption = build_image_caption(
            source_folder=source_folder,
            file_name=file_name,
            ocr_text=ocr_text,
            visual_json=visual_json,
        )

        return {
            "ocr_text": ocr_lower,
            "image_caption": caption,
            "exif_capture_time": exif_capture_time,
            "raw_metadata_json": json.dumps({"exif": raw_exif}, ensure_ascii=False),
        }
    finally:
        image.close()


def infer_entities(file_name: str, source_folder: str, extracted_text: str, ocr_text: str, image_caption: str,
                   visual_summary: str | None,
                   vision_json: str | None):
    entities = []
    haystack = " ".join([
        (file_name or ""),
        (source_folder or ""),
        (extracted_text or ""),
        (ocr_text or ""),
        (image_caption or ""),
        (visual_summary or ""),
        (vision_json or ""),
    ]).lower()

    def add(entity_type: str, entity_value: str, confidence: float, source: str):
        entities.append((entity_type, entity_value, confidence, source))

    if any(x in haystack for x in ["passport", "identity", "driver license", "driver's license", " id "]):
        add("document_type", "identity_document", 0.8, "rule")

    if "receipt" in haystack:
        add("document_type", "receipt", 0.9, "rule")

    if any(x in haystack for x in ["booking", "reservation", "check-in", "check in"]):
        add("document_type", "booking", 0.75, "rule")

    if "baby" in haystack:
        add("subject", "baby", 0.75, "rule")

    return entities


def split_text_into_chunks(text: str, chunk_size: int = 900, overlap: int = 150):
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append((chunk_text, start, end))
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)

    return chunks


def delete_existing_processed_data(conn, file_id: int):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM file_content WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM entities WHERE file_id = ?", (file_id,))
    cursor.execute("DELETE FROM generated_outputs WHERE file_id = ?", (file_id,))
    conn.commit()


def delete_chroma_chunks_for_file(collection, file_id: int):
    # Get IDs from SQLite chunk records is ideal, but for MVP we also allow delete by metadata filter if supported.
    # Safer approach here: delete by explicit IDs after recreating from SQLite is not possible post-delete,
    # so we use a metadata-based delete.
    try:
        collection.delete(where={"file_id": file_id})
    except Exception:
        # Some Chroma versions may behave differently; ignore for MVP if no prior chunks exist.
        pass


def upsert_file_content(conn, file_id: int, extracted_text: str | None, ocr_text: str | None, image_caption: str | None,
                        visual_summary: str | None, vision_json: str | None, raw_metadata_json: str | None, tags_json:
        dict | None):
    cursor = conn.cursor()
    tags_json = ', '.join(tags_json)
    cursor.execute(
        """
        INSERT INTO file_content (
            file_id,
            extracted_text,
            ocr_text,
            image_caption,
            visual_summary,
            vision_json,
            raw_metadata_json,
            created_at,
            updated_at,
            tags_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,?)
        """,
        (
            file_id,
            extracted_text,
            ocr_text,
            image_caption,
            visual_summary,
            vision_json,
            raw_metadata_json,
            utc_now_iso(),
            utc_now_iso(),
            tags_json,
        ),
    )
    conn.commit()


def insert_entities(conn, file_id: int, entities: list[tuple]):
    if not entities:
        return

    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT INTO entities (
            file_id,
            entity_type,
            entity_value,
            confidence,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (file_id, entity_type, entity_value, confidence, source, utc_now_iso())
            for entity_type, entity_value, confidence, source in entities
        ],
    )
    conn.commit()


def build_chunk_records(file_id: int, file_row: dict, extracted_text: str, ocr_text: str, image_caption: str,
                        visual_summary: str | None,
                        vision_json: str | None):
    records = []

    if extracted_text:
        for idx, (chunk_text, char_start, char_end) in enumerate(split_text_into_chunks(extracted_text)):
            records.append({
                "chunk_id": f"file_{file_id}_chunk_{idx}_document_text",
                "chunk_index": idx,
                "chunk_type": "document_text",
                "chunk_text": chunk_text,
                "char_start": char_start,
                "char_end": char_end,
                "metadata": {
                    "file_id": file_id,
                    "drive_file_id": file_row["drive_file_id"],
                    "file_name": file_row["file_name"],
                    "file_type": file_row["mime_type"] or "unknown",
                    "source_folder": file_row["source_folder"] or "",
                    "chunk_type": "document_text",
                    "chunk_index": idx
                },
            })

    if ocr_text:
        for idx, (chunk_text, char_start, char_end) in enumerate(split_text_into_chunks(ocr_text)):
            records.append({
                "chunk_id": f"file_{file_id}_chunk_{idx}_ocr_text",
                "chunk_index": idx,
                "chunk_type": "ocr_text",
                "chunk_text": chunk_text,
                "char_start": char_start,
                "char_end": char_end,
                "metadata": {
                    "file_id": file_id,
                    "drive_file_id": file_row["drive_file_id"],
                    "file_name": file_row["file_name"],
                    "file_type": file_row["mime_type"] or "unknown",
                    "source_folder": file_row["source_folder"] or "",
                    "chunk_type": "ocr_text",
                    "chunk_index": idx
                },
            })

    if image_caption:
        records.append({
            "chunk_id": f"file_{file_id}_chunk_0_caption",
            "chunk_index": 0,
            "chunk_type": "caption",
            "chunk_text": image_caption,
            "char_start": 0,
            "char_end": len(image_caption),
            "metadata": {
                "file_id": file_id,
                "drive_file_id": file_row["drive_file_id"],
                "file_name": file_row["file_name"],
                "file_type": file_row["mime_type"] or "unknown",
                "source_folder": file_row["source_folder"] or "",
                "chunk_type": "caption",
                "chunk_index": 0
            },
        })

    if visual_summary:
        records.append({
            "chunk_id": f"file_{file_id}_chunk_0_visual_summary",
            "chunk_index": 0,
            "chunk_type": "visual_summary",
            "chunk_text": visual_summary,
            "char_start": 0,
            "char_end": len(visual_summary),
            "metadata": {
                "file_id": file_id,
                "drive_file_id": file_row["drive_file_id"],
                "file_name": file_row["file_name"],
                "file_type": file_row["mime_type"] or "unknown",
                "source_folder": file_row["source_folder"] or "",
                "chunk_type": "visual_summary",
                "chunk_index": 0,
                "visual_summary": visual_summary,
                "vision_json": vision_json
            },
        })

    return records


def insert_chunks_into_sqlite(conn, file_id: int, chunk_records: list[dict]):
    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT INTO chunks (
            file_id,
            chunk_index,
            chunk_type,
            chunk_text,
            char_start,
            char_end,
            embedding_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                file_id,
                record["chunk_index"],
                record["chunk_type"],
                record["chunk_text"],
                record["char_start"],
                record["char_end"],
                record["chunk_id"],
                utc_now_iso(),
            )
            for record in chunk_records
        ],
    )
    conn.commit()


def upsert_chunks_to_chroma(collection, chunk_records: list[dict], file_id):
    if not chunk_records:
        return

    collection.upsert(
        ids=[record["chunk_id"] for record in chunk_records],
        documents=[record["chunk_text"] for record in chunk_records],
        metadatas=[record["metadata"] for record in chunk_records],
    )


def process_single_file(conn, service, collection, row):
    vision_json = ""
    tags_json = ""
    file_id, drive_file_id, file_name, mime_type, source_folder, drive_modified_time = row

    file_row = {
        "file_id": file_id,
        "drive_file_id": drive_file_id,
        "file_name": file_name,
        "mime_type": mime_type,
        "source_folder": source_folder,
        "drive_modified_time": drive_modified_time,
    }

    safe_name = file_name.replace("/", "_").replace("\\", "_")
    temp_path = TEMP_DOWNLOAD_DIR / f"{file_id}_{safe_name}"

    suffix_lower = temp_path.suffix.lower()

    if not is_supported_mvp_type(mime_type, suffix_lower):
        raise RuntimeError(
            f"SKIP_UNSUPPORTED: mime_type={mime_type}, suffix={suffix_lower}"
        )

    print(f"\nProcessing file: {file_name} ({drive_file_id})")

    download_drive_file(service, drive_file_id, temp_path)

    extracted_text = ""
    ocr_text = ""
    image_caption = ""
    raw_metadata_json = "{}"
    exif_capture_time = None
    visual_summary = ""
    vision_json = "{}"

    mime_lower = (mime_type or "").lower()
    suffix_lower = temp_path.suffix.lower()

    if mime_lower == "application/pdf" or suffix_lower == ".pdf":
        extracted_text = extract_text_from_pdf(temp_path)

    elif "wordprocessingml" in mime_lower or suffix_lower == ".docx":
        extracted_text = extract_text_from_docx(temp_path)

    elif mime_lower.startswith("text/") or suffix_lower == ".txt":
        extracted_text = extract_text_from_txt(temp_path)

    elif mime_lower.startswith("image/") or suffix_lower in [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]:
        visual_summary, vision_json = analyze_image_with_vision_model(temp_path)
        image_data = extract_image_metadata_and_caption(temp_path, source_folder or "", file_name or "",
                                                        vision_json or "")
        ocr_text = image_data["ocr_text"]
        image_caption = image_data["image_caption"]
        raw_metadata_json = image_data["raw_metadata_json"]
        exif_capture_time = image_data["exif_capture_time"]
        tags_json = infer_tags(file_name, source_folder, ocr_text, image_caption, visual_summary, vision_json)

    else:
        raise RuntimeError(
            f"SKIP_UNSUPPORTED: mime_type={mime_type}, suffix={suffix_lower}"
        )

    delete_existing_processed_data(conn, file_id)
    delete_chroma_chunks_for_file(collection, file_id)

    upsert_file_content(
        conn=conn,
        file_id=file_id,
        extracted_text=extracted_text,
        ocr_text=ocr_text,
        image_caption=image_caption,
        raw_metadata_json=raw_metadata_json,
        vision_json=vision_json,
        visual_summary=visual_summary,
        tags_json=tags_json,
    )

    update_exif_capture_time(conn, file_id, exif_capture_time)

    entities = infer_entities(
        file_name=file_name or "",
        source_folder=source_folder or "",
        extracted_text=extracted_text,
        ocr_text=ocr_text,
        image_caption=image_caption,
        visual_summary=visual_summary,
        vision_json=vision_json,
    )
    insert_entities(conn, file_id, entities)

    chunk_records = build_chunk_records(
        file_id=file_id,
        file_row=file_row,
        extracted_text=extracted_text,
        ocr_text=ocr_text,
        image_caption=image_caption,
        visual_summary=visual_summary,
        vision_json=vision_json,
    )
    insert_chunks_into_sqlite(conn, file_id, chunk_records)
    upsert_chunks_to_chroma(collection, chunk_records, file_id)

    mark_file_processing_status(conn, file_id, "processed", None)

    if temp_path.exists():
        temp_path.unlink()

    print(f"Processed successfully: {file_name}")


def main():
    TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection()
    service = get_drive_service()
    chroma_client = get_chroma_client()
    collection = get_or_create_collection(chroma_client)

    rows = fetch_pending_files(conn)

    if not rows:
        print("No pending files to process.")
        conn.close()
        return

    print(f"Found {len(rows)} pending file(s).")

    for row in rows:
        file_id = row[0]
        file_name = row[2]

        try:
            process_single_file(conn, service, collection, row)
        except Exception as e:
            error_text = str(e)[:1000]
            mark_file_processing_status(conn, file_id, "failed", error_text)
            print(f"Failed processing {file_name}: {error_text}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
