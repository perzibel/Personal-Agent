from pathlib import Path
import sqlite3

# Project root = one level above /scripts
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "agent_memory.db"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_file_id TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    mime_type TEXT,
    source_folder TEXT,
    drive_web_link TEXT,
    local_cache_path TEXT,
    checksum TEXT,
    file_size_bytes INTEGER,
    drive_created_time TEXT,
    drive_modified_time TEXT,
    exif_capture_time TEXT,
    file_category TEXT,
    processing_status TEXT DEFAULT 'pending',
    processing_error TEXT,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TEXT,
    last_processed_at TEXT
);

CREATE TABLE IF NOT EXISTS file_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    extracted_text TEXT,
    ocr_text TEXT,
    image_caption TEXT,
    raw_metadata_json TEXT,
    content_language TEXT,
    content_summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_type TEXT,
    chunk_text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    embedding_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    confidence REAL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generated_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    output_type TEXT NOT NULL,
    output_text TEXT NOT NULL,
    output_json TEXT,
    model_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT,
    files_seen INTEGER DEFAULT 0,
    files_added INTEGER DEFAULT 0,
    files_updated INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_drive_file_id ON files(drive_file_id);
CREATE INDEX IF NOT EXISTS idx_files_file_category ON files(file_category);
CREATE INDEX IF NOT EXISTS idx_files_exif_capture_time ON files(exif_capture_time);
CREATE INDEX IF NOT EXISTS idx_files_drive_created_time ON files(drive_created_time);
CREATE INDEX IF NOT EXISTS idx_entities_file_id ON entities(file_id);
CREATE INDEX IF NOT EXISTS idx_entities_type_value ON entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_generated_outputs_file_id ON generated_outputs(file_id);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"Database created successfully at: {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()