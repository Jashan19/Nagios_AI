# database.py

import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Store the database inside the project folder.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "chatbot.db"


def get_connection():
    """Create a connection to the SQLite database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")

    return connection


@contextmanager
def database_connection():
    """Manage a database connection and its transaction."""
    connection = get_connection()

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create all database tables and indexes if they don't exist."""

    with database_connection() as db:

        # 1. Users
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                display_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Conversations
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New chat',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        # 3. Messages
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            )
        """)

        # 4. Long-term memories
        db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL
                    CHECK (type IN (
                        'episodic',
                        'semantic',
                        'procedural',
                        'relational',
                        'working'
                    )),
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.5
                    CHECK (importance BETWEEN 0 AND 1),
                confidence REAL NOT NULL DEFAULT 0.5
                    CHECK (confidence BETWEEN 0 AND 1),
                source_message_id INTEGER,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (source_message_id)
                    REFERENCES messages(id)
                    ON DELETE SET NULL
                    )
            """)

        # 5. Relationships between memories
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_memory_id INTEGER NOT NULL,
                target_memory_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5
                    CHECK (confidence BETWEEN 0 AND 1),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                CHECK (source_memory_id != target_memory_id),

                UNIQUE (
                    source_memory_id,
                    target_memory_id,
                    relation_type
                ),

                FOREIGN KEY (source_memory_id)
                    REFERENCES memories(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (target_memory_id)
                    REFERENCES memories(id)
                    ON DELETE CASCADE
            )
        """)

        # Indexes for common lookups
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user
            ON conversations(user_id, updated_at)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_type
            ON memories(user_id, type)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_source
            ON memories(source_message_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_expiry
            ON memories(expires_at)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_source
            ON memory_relations(source_memory_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_target
            ON memory_relations(target_memory_id)
        """)

        # Add authentication columns to existing databases.
        user_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        if "username" not in user_columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN username TEXT"
            )

        if "password_hash" not in user_columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN password_hash TEXT"
            )

        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
            ON users(username COLLATE NOCASE)
            WHERE username IS NOT NULL
        """)
    print(f"Database initialized: {DB_PATH}")
if __name__ == "__main__":
    initialize_database()
