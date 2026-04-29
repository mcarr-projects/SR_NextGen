import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "spacedrep.db"
DEFAULT_USER_ID = 1
MAX_PERFORMANCE_HISTORY = 100
VALID_LENGTHS = {"short", "medium", "long"}


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        length TEXT NOT NULL DEFAULT 'short'
            CHECK (length IN ('short', 'medium', 'long')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS card_tags (
        card_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE (card_id, tag_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_card_state (
        user_id INTEGER NOT NULL,
        card_id INTEGER NOT NULL,
        next_review_time TEXT NOT NULL,
        last_reviewed_at TEXT,
        last_performance INTEGER,
        current_interval INTEGER NOT NULL DEFAULT 1,
        repetitions INTEGER NOT NULL DEFAULT 0,
        ef REAL NOT NULL DEFAULT 2.5,
        lapse_count INTEGER NOT NULL DEFAULT 0,
        performance_history_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (user_id, card_id),
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_card_tags_tag_id
    ON card_tags(tag_id);
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_card_state_user_next_review
    ON user_card_state(user_id, next_review_time);
    """)

    conn.commit()
    conn.close()


def clean_tags(tags):
    if tags is None:
        return []
    if not isinstance(tags, (list, tuple)):
        raise TypeError("tags must be a list or tuple of strings")

    cleaned = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("each tag must be a string")
        clean_tag = tag.strip()
        if clean_tag and clean_tag not in seen:
            cleaned.append(clean_tag)
            seen.add(clean_tag)

    return cleaned


def add_card(question, answer, tags=None, length="short", user_id=DEFAULT_USER_ID, next_review_time=None):
    if length not in VALID_LENGTHS:
        raise ValueError("length must be one of: short, medium, long")

    card_tags = clean_tags(tags)
    next_review_time = next_review_time or utc_now_iso()

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
        INSERT INTO cards (question, answer, length)
        VALUES (?, ?, ?)
        """, (question, answer, length))
        card_id = cur.lastrowid

        for tag in card_tags:
            cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag,))
            tag_id = cur.fetchone()["id"]

            cur.execute("""
            INSERT OR IGNORE INTO card_tags (card_id, tag_id)
            VALUES (?, ?)
            """, (card_id, tag_id))

        cur.execute("""
        INSERT INTO user_card_state (user_id, card_id, next_review_time)
        VALUES (?, ?, ?)
        """, (user_id, card_id, next_review_time))

        conn.commit()
        return {"success": True, "card_id": card_id, "tags": card_tags}

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}

    finally:
        conn.close()


def get_cards(tags, user_id=DEFAULT_USER_ID):
    if not isinstance(tags, list):
        raise TypeError("tags must be a list; use ['ALL'] to fetch all cards")

    if not tags:
        raise ValueError("tags must be a non-empty list; use ['ALL'] to fetch all cards")

    if "ALL" in tags and tags != ["ALL"]:
        raise ValueError("use ['ALL'] by itself, not mixed with other tags")

    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("each tag must be a string")

    conn = get_connection()
    cur = conn.cursor()

    try:
        if tags == ["ALL"]:
            cur.execute("""
                SELECT id
                FROM cards
                ORDER BY id ASC
            """)
            card_ids = [row["id"] for row in cur.fetchall()]
        else:
            placeholders = ",".join("?" for _ in tags)

            cur.execute(f"""
                SELECT c.id
                FROM cards c
                JOIN card_tags ct
                    ON ct.card_id = c.id
                JOIN tags t
                    ON t.id = ct.tag_id
                WHERE t.name IN ({placeholders})
                GROUP BY c.id
                HAVING COUNT(DISTINCT t.name) = ?
                ORDER BY c.id ASC
            """, (*tags, len(tags)))

            card_ids = [row["id"] for row in cur.fetchall()]

        if not card_ids:
            return []

        id_placeholders = ",".join("?" for _ in card_ids)

        cur.execute(f"""
            SELECT
                c.id,
                c.question,
                c.answer,
                c.length,
                c.created_at,
                c.updated_at,
                ucs.next_review_time,
                ucs.last_reviewed_at,
                ucs.last_performance,
                ucs.current_interval,
                ucs.repetitions,
                ucs.ef,
                ucs.lapse_count,
                COALESCE(GROUP_CONCAT(DISTINCT t.name), '') AS tags
            FROM cards c
            LEFT JOIN user_card_state ucs
                ON ucs.card_id = c.id
                AND ucs.user_id = ?
            LEFT JOIN card_tags ct
                ON ct.card_id = c.id
            LEFT JOIN tags t
                ON t.id = ct.tag_id
            WHERE c.id IN ({id_placeholders})
            GROUP BY c.id
            ORDER BY c.id ASC
        """, (user_id, *card_ids))

        rows = cur.fetchall()
        return [row_to_card_dict(row) for row in rows]

    except Exception as e:
        print("Error retrieving cards:", e)
        return []

    finally:
        conn.close()


def get_due_cards(user_id=DEFAULT_USER_ID, as_of=None, limit=None):
    #TBD
    return

def record_review(card_id, score, user_id=DEFAULT_USER_ID, reviewed_at=None, next_review_time=None):
    #TBD
    return 

def row_to_card_dict(row):
    card = dict(row)
    tags = card.get("tags", "")
    card["tags"] = [tag for tag in tags.split(",") if tag] if tags else []
    return card


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
