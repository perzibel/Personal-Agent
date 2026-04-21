from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SQLITE_DB_PATH = PROJECT_ROOT / "data" / "agent_memory.db"
CHROMA_PERSIST_DIR = PROJECT_ROOT / "data" / "chroma"
JSON_TOKEN = PROJECT_ROOT / "token.json"

OPTIONAL_DIRS_TO_CLEAR = [
    PROJECT_ROOT / "data" / "processed",
    PROJECT_ROOT / "data" / "temp",
]

DIRS_TO_RECREATE = [
    SQLITE_DB_PATH.parent,
    CHROMA_PERSIST_DIR,
    *OPTIONAL_DIRS_TO_CLEAR,
]


def remove_file(file_path: Path) -> None:
    if file_path.exists():
        file_path.unlink()
        print(f"[+] Deleted file: {file_path}")
    else:
        print(f"[-] File not found, skipping: {file_path}")


def remove_dir(dir_path: Path) -> None:
    if dir_path.exists():
        shutil.rmtree(dir_path)
        print(f"[+] Deleted directory: {dir_path}")
    else:
        print(f"[-] Directory not found, skipping: {dir_path}")


def recreate_dirs() -> None:
    for dir_path in DIRS_TO_RECREATE:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"[+] Ensured directory exists: {dir_path}")


def reset_everything() -> None:
    confirmation = input(
        "This will permanently delete the DB and Chroma data. Type 'RESET' to continue: "
    ).strip()

    if confirmation != "RESET":
        print("Aborted.")
        return

    print("Starting full reset...")

    remove_file(SQLITE_DB_PATH)
    remove_dir(CHROMA_PERSIST_DIR)

    for folder in OPTIONAL_DIRS_TO_CLEAR:
        remove_dir(folder)

    remove_file(JSON_TOKEN)
    recreate_dirs()

    print("\n[+] Reset completed. Clean slate ready.")


if __name__ == "__main__":
    reset_everything()