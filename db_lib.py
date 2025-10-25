import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "spacedrep.db"


def get_connection():
    """Return a connection to the local SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    return conn


def init_db():
    """Create the cards table if it doesn't already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        tags TEXT CHECK(json_valid(tags)),
        length TEXT CHECK(length IN ('short', 'medium', 'long')) DEFAULT 'short',
        ef REAL DEFAULT 2.5,
        interval INTEGER DEFAULT 1,
        repetitions INTEGER DEFAULT 0,
        due_date TEXT DEFAULT CURRENT_DATE,
        last_score INTEGER
    );
    """)

    conn.commit()
    conn.close()

def add_card(question: str, answer: str, tags: list[str], length: str = "short"):
    """Insert a new card into the database."""
    try:
        tags_json = json.dumps(tags)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cards (question, answer, tags, length)
            VALUES (?, ?, ?, ?)
        """, (question, answer, tags_json, length))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error adding card: {e}")
        return False
init_db()