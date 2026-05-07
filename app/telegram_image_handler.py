from pathlib import Path
from datetime import datetime, timezone
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from app.image_ingestion_service import ingest_telegram_image
from app.pending_requests import create_pending_folder_choice


TELEGRAM_DOWNLOAD_DIR = Path("data/telegram_uploads")
TELEGRAM_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

processing_lock = asyncio.Lock()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    if not message or not message.photo:
        return

    await message.reply_text("Got the image. Running visual analysis...")

    photo = message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    local_path = TELEGRAM_DOWNLOAD_DIR / f"telegram_{timestamp}_{photo.file_unique_id}.jpg"

    await telegram_file.download_to_drive(custom_path=local_path)

    try:
        await message.reply_text("Image queued. Processing now...")

        async with processing_lock:
            result = await asyncio.to_thread(
                ingest_telegram_image,
                local_path=local_path,
                telegram_file_id=photo.file_id,
                telegram_file_unique_id=photo.file_unique_id,
                caption=message.caption,
                sender_id=update.effective_user.id if update.effective_user else None,
                chat_id=update.effective_chat.id,
            )

            if result.get("status") == "needs_user_choice":
                pending = create_pending_folder_choice(
                    local_path=local_path,
                    mime_type=result["mime_type"],
                    telegram_file_id=result["telegram_file_id"],
                    telegram_file_unique_id=result["telegram_file_unique_id"],
                    caption=result.get("telegram_caption"),
                    sender_id=result.get("telegram_sender_id"),
                    chat_id=update.effective_chat.id,
                    file_hint=result.get("file_name") or local_path.name,
                    candidate_folders=result["candidate_folders"],
                    reason=result["routing_reason"],
                )

                folders_text = ", ".join(result["candidate_folders"])

                await message.reply_text(
                    "I need your help choosing a folder.\n\n"
                    f"Request ID: {pending.request_id}\n"
                    f"File: {pending.file_hint}\n"
                    f"Reason: {pending.reason}\n"
                    f"Candidate folders: {folders_text}\n\n"
                    f"Reply with:\n/choose {pending.request_id} <folder>\n\n"
                    f"Example:\n/choose {pending.request_id} cars"
                )
                return
        visual_summary = result.get("visual_summary") or "No visual summary was generated."
        drive_link = result.get("drive_web_link") or "No Drive link was returned."
        selected_folder = result.get("selected_folder") or "unknown"
        routing_reason = result.get("routing_reason") or "unknown"

        reply = (
            "Image processed successfully.\n\n"
            f"Uploaded to: {selected_folder}\n"
            f"Reason: {routing_reason}\n\n"
            f"Summary:\n{visual_summary}\n\n"
            f"Google Drive:\n{drive_link}"
        )

        await message.reply_text(reply)

    except Exception as e:
        await message.reply_text(f"Failed to process image: {e}")