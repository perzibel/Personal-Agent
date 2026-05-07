import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from app.folder_decision_service import AVAILABLE_FOLDERS
from app.pending_requests import pop_pending_folder_choice, list_pending_folder_choices
from app.image_ingestion_service import complete_telegram_image_ingestion


async def handle_choose_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if len(context.args) < 2:
        await message.reply_text(
            "Usage:\n/choose <request_id> <folder>\n\n"
            "Example:\n/choose abc123ef cars"
        )
        return

    request_id = context.args[0].strip()
    folder_name = context.args[1].strip().lower()

    if folder_name not in AVAILABLE_FOLDERS:
        await message.reply_text(
            f"Unknown folder: {folder_name}\n"
            f"Available folders: {', '.join(AVAILABLE_FOLDERS)}"
        )
        return

    pending = pop_pending_folder_choice(request_id)

    if not pending:
        await message.reply_text(
            f"No pending request found for ID: {request_id}"
        )
        return

    if pending.chat_id != chat.id:
        await message.reply_text(
            "This request belongs to another chat."
        )
        return

    await message.reply_text(
        f"Got it. Uploading {pending.file_hint} to folder: {folder_name}"
    )

    try:
        result = await asyncio.to_thread(
            complete_telegram_image_ingestion,
            local_path=Path(pending.local_path),
            folder_name=folder_name,
            telegram_file_id=pending.telegram_file_id,
            telegram_file_unique_id=pending.telegram_file_unique_id,
            caption=pending.caption,
            sender_id=pending.sender_id,
            routing_reason=f"User selected folder from pending request {pending.request_id}",
            routing_confidence=1.0,
        )

        visual_summary = result.get("visual_summary") or "No visual summary was generated."
        drive_link = result.get("drive_web_link") or "No Drive link was returned."

        await message.reply_text(
            "File processed successfully.\n\n"
            f"Uploaded to: {folder_name}\n\n"
            f"Summary:\n{visual_summary}\n\n"
            f"Google Drive:\n{drive_link}"
        )

    except Exception as error:
        await message.reply_text(
            f"Failed to complete request {request_id}: {error}"
        )


async def handle_pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    pending_items = list_pending_folder_choices(chat_id=chat.id)

    if not pending_items:
        await message.reply_text("No pending folder choices.")
        return

    lines = ["Pending folder choices:"]

    for item in pending_items:
        lines.append(
            "\n"
            f"Request ID: {item['request_id']}\n"
            f"File: {item['file_hint']}\n"
            f"Candidates: {', '.join(item['candidate_folders'])}\n"
            f"Reason: {item['reason']}"
        )

    await message.reply_text("\n".join(lines))