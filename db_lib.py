import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "spacedrep.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    return conn


def init_db():
    """Initialize the database with normalized tag schema."""
    conn = get_connection()
    cur = conn.cursor()

    # === Core table for flashcards ===
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        length TEXT CHECK(length IN ('short', 'medium', 'long')) DEFAULT 'short',
        ef REAL DEFAULT 2.5,
        interval INTEGER DEFAULT 1,
        repetitions INTEGER DEFAULT 0,
        due_date TEXT DEFAULT CURRENT_DATE,
        last_score INTEGER
    );
    """)

    # === Tag lookup table ===
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    """)

    # === Many-to-many relationship ===
    cur.execute("""
    CREATE TABLE IF NOT EXISTS card_tags (
        card_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE(card_id, tag_id)
    );
    """)

    # === Indexes for faster lookup ===
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tag_name ON tags(name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_card_tag_tagid ON card_tags(tag_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_card_tag_cardid ON card_tags(card_id);")

    conn.commit()
    conn.close()

def add_card(question, answer, tags, length="short"):

    if not isinstance(tags, (list)):
        raise TypeError("tags must be a list or tuple of strings")
    
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
                    INSERT INTO cards (question, answer, length)
                    VALUES (?, ?, ?)
                    """, (question, answer, length))
        card_id = cur.lastrowid

        for tag in set(tags):
            cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag,))
            tag_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT OR IGNORE INTO card_tags (card_id, tag_id)
                VALUES (?, ?)
            """, (card_id, tag_id))

        conn.commit()
        return {"success": True, "card_id": card_id, "tags": tags}
        
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    
    finally:
        conn.close()


def get_cards(tags=""):

    conn = get_connection()
    cur = conn.cursor()

    try:
        if not tags.strip():
            cur.execute("""
                SELECT id, question, answer
                FROM cards
                ORDER BY id ASC
            """)

    except Exception as e:
        print("Error retrieving cards:", e)
        return []

    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")