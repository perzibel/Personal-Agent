from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agent_memory.db"


def get_table_names(cursor):
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    return [row[0] for row in cursor.fetchall()]


def get_column_names(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def get_best_order_clause(columns):
    preferred_order = [
        "id",
        "file_id",
        "chunk_id",
        "entity_id",
        "created_at",
        "updated_at",
        "name",
    ]

    for col in preferred_order:
        if col in columns:
            return f"ORDER BY {col}"

    return ""


def print_table(cursor, table_name):
    columns = get_column_names(cursor, table_name)

    print("\n" + "=" * 100)
    print(f"TABLE: {table_name}")
    print("=" * 100)

    print(f"Columns: {', '.join(columns)}")

    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]
    print(f"Row count: {row_count}")

    if row_count == 0:
        print("(empty)")
        return

    order_clause = get_best_order_clause(columns)
    query = f"SELECT * FROM {table_name} {order_clause}"

    cursor.execute(query)
    rows = cursor.fetchall()

    for i, row in enumerate(rows, start=1):
        print(f"\nRow {i}:")
        for col_name, value in zip(columns, row):
            print(f"  {col_name}: {value}")


def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        table_names = get_table_names(cursor)

        print(f"Database: {DB_PATH}")
        print(f"Found {len(table_names)} tables:")
        for table_name in table_names:
            print(f" - {table_name}")

        for table_name in table_names:
            print_table(cursor, table_name)

    finally:
        conn.close()


if __name__ == "__main__":
    main()