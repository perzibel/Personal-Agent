from __future__ import annotations
from tqdm import tqdm

import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
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


def extract_image_metadata_and_caption(file_path: Path, source_folder: str, file_name: str):
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
                # Typical EXIF format: 2026:04:18 10:30:11
                try:
                    exif_capture_time = datetime.strptime(
                        str(date_original), "%Y:%m:%d %H:%M:%S"
                    ).isoformat()
                except ValueError:
                    exif_capture_time = str(date_original)

        ocr_text = pytesseract.image_to_string(image).strip()

        # MVP caption: lightweight caption based on folder/name/OCR clues
        file_name_lower = file_name.lower()
        source_lower = (source_folder or "").lower()
        ocr_lower = ocr_text.lower()

        if "receipt" in source_lower or "receipt" in file_name_lower:
            caption = "Photo or screenshot of a receipt"
        elif "screenshot" in source_lower or "screenshot" in file_name_lower:
            caption = "Screenshot containing visible text or app content"
        elif any(x in ocr_lower for x in ["passport", "identity", "driver", "license", "id"]):
            caption = "Image that may contain an identity document"
        elif "baby" in source_lower or "baby" in file_name_lower:
            caption = "Photo likely related to a baby"
        else:
            caption = f"Image from folder '{source_folder}' named '{file_name}'"

        return {
            "ocr_text": ocr_text,
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
                        visual_summary: str | None, vision_json: str | None, raw_metadata_json: str | None):
    cursor = conn.cursor()
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
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def build_chunk_records(file_id: int, file_row: dict, extracted_text: str, ocr_text: str, image_caption: str, visual_summary: str | None,
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


def upsert_chunks_to_chroma(collection, chunk_records: list[dict],file_id):
    if not chunk_records:
        return

    collection.upsert(
        ids=[record["chunk_id"] for record in chunk_records],
        documents=[record["chunk_text"] for record in chunk_records],
        metadatas=[record["metadata"] for record in chunk_records],
    )


def process_single_file(conn, service, collection, row):
    global vision_json
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

    # Define the total number of logical steps in your pipeline
    total_steps = 6

    # Initialize the progress bar
    with tqdm(total=total_steps, desc="Pipeline Progress",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]") as pbar:

        # --- STEP 1: Download ---
        pbar.set_postfix_str("Status: Downloading file...")
        download_drive_file(service, drive_file_id, temp_path)
        pbar.update(1)

        # --- STEP 2: Extraction & Vision Model ---
        pbar.set_postfix_str("Status: Extracting text/metadata...")
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
            image_data = extract_image_metadata_and_caption(temp_path, source_folder or "", file_name or "")
            ocr_text = image_data["ocr_text"]
            image_caption = image_data["image_caption"]
            raw_metadata_json = image_data["raw_metadata_json"]
            exif_capture_time = image_data["exif_capture_time"]

            from app.vision_utils import analyze_image_with_vision_model
            # Update status right before the heavy vision model runs
            pbar.set_postfix_str("Status: Running Vision Model (Heavy)...")
            visual_summary, vision_json = analyze_image_with_vision_model(temp_path)

        else:
            raise RuntimeError(f"SKIP_UNSUPPORTED: mime_type={mime_type}, suffix={suffix_lower}")

        pbar.update(1)

        # --- STEP 3: Database Updates ---
        pbar.set_postfix_str("Status: Updating Database...")
        delete_existing_processed_data(conn, file_id)
        delete_chroma_chunks_for_file(collection, file_id)

        upsert_file_content(
            conn=conn, file_id=file_id, extracted_text=extracted_text, ocr_text=ocr_text,
            image_caption=image_caption, raw_metadata_json=raw_metadata_json,
            vision_json=vision_json, visual_summary=visual_summary
        )
        update_exif_capture_time(conn, file_id, exif_capture_time)
        pbar.update(1)

        # --- STEP 4: Entity Inference ---
        pbar.set_postfix_str("Status: Inferring Entities...")
        entities = infer_entities(
            file_name=file_name or "", source_folder=source_folder or "",
            extracted_text=extracted_text, ocr_text=ocr_text, image_caption=image_caption,
            visual_summary=visual_summary, vision_json=vision_json,
        )
        insert_entities(conn, file_id, entities)
        pbar.update(1)

        # --- STEP 5: Chunking & Vector DB ---
        pbar.set_postfix_str("Status: Generating/Inserting Chunks...")
        chunk_records = build_chunk_records(
            file_id=file_id, file_row=file_row, extracted_text=extracted_text,
            ocr_text=ocr_text, image_caption=image_caption, visual_summary=visual_summary,
            vision_json=vision_json,
        )
        insert_chunks_into_sqlite(conn, file_id, chunk_records)
        upsert_chunks_to_chroma(collection, chunk_records, file_id)
        pbar.update(1)

        # --- STEP 6: Cleanup & Finish ---
        pbar.set_postfix_str("Status: Finalizing cleanup...")
        mark_file_processing_status(conn, file_id, "processed", None)

        if temp_path.exists():
            temp_path.unlink()

        pbar.update(1)
        pbar.set_postfix_str("Status: Done!")

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
