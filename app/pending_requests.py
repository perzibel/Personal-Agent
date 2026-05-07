from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone


@dataclass
class PendingFolderChoice:
    request_id: str
    local_path: str
    mime_type: str
    telegram_file_id: str
    telegram_file_unique_id: str
    caption: Optional[str]
    sender_id: Optional[int]
    chat_id: int
    file_hint: str
    candidate_folders: list[str]
    reason: str
    created_at: str


PENDING_FOLDER_CHOICES: dict[str, PendingFolderChoice] = {}


def create_pending_folder_choice(
    local_path: Path,
    mime_type: str,
    telegram_file_id: str,
    telegram_file_unique_id: str,
    caption: Optional[str],
    sender_id: Optional[int],
    chat_id: int,
    file_hint: str,
    candidate_folders: list[str],
    reason: str,
) -> PendingFolderChoice:
    request_id = uuid4().hex[:8]

    pending = PendingFolderChoice(
        request_id=request_id,
        local_path=str(local_path),
        mime_type=mime_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        caption=caption,
        sender_id=sender_id,
        chat_id=chat_id,
        file_hint=file_hint,
        candidate_folders=candidate_folders,
        reason=reason,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    PENDING_FOLDER_CHOICES[request_id] = pending
    return pending


def get_pending_folder_choice(request_id: str) -> Optional[PendingFolderChoice]:
    return PENDING_FOLDER_CHOICES.get(request_id)


def pop_pending_folder_choice(request_id: str) -> Optional[PendingFolderChoice]:
    return PENDING_FOLDER_CHOICES.pop(request_id, None)


def list_pending_folder_choices(chat_id: Optional[int] = None) -> list[dict]:
    items = list(PENDING_FOLDER_CHOICES.values())

    if chat_id is not None:
        items = [item for item in items if item.chat_id == chat_id]

    return [asdict(item) for item in items]