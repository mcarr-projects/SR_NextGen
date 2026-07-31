import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "spacedrep.db"
PRIVATE_PATH = Path(__file__).resolve().parent.parent.parent / "SR_Private"

if str(PRIVATE_PATH) not in sys.path:
    sys.path.insert(0, str(PRIVATE_PATH))

from review_scheduling import calc_next_review_info

DEFAULT_USER_ID = 1
MAX_PERFORMANCE_HISTORY = 100
VALID_LENGTHS = {"short", "medium", "long"}
VALID_GRADING_TYPES = {"binary", "scaled"}
FAILED_AI_SCORE = -1
VALID_REVIEW_SCORES = {FAILED_AI_SCORE, 1, 2, 3, 4, 5}

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def parse_iso_datetime(dt_text):
    return datetime.fromisoformat(dt_text)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            length TEXT NOT NULL DEFAULT 'short'
                CHECK (length IN ('short', 'medium', 'long')),
            grading_type TEXT
                CHECK (grading_type IN ('binary', 'scaled')),
            grading_criteria TEXT,
            llm_grading_info TEXT,
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
            recent_scores_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (user_id, card_id),
            FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            grading_mode TEXT NOT NULL
                CHECK (grading_mode IN ('manual', 'ai')),
            score INTEGER NOT NULL
                CHECK (score IN (-1, 1, 2, 3, 4, 5))
                CHECK (score != -1 OR grading_mode = 'ai'),
            user_answer TEXT,
            ai_feedback TEXT,
            FOREIGN KEY (card_id) REFERENCES cards(id)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            purpose TEXT NOT NULL CHECK (length(trim(purpose)) > 0),
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            provider_request_id TEXT,
            request_json TEXT NOT NULL,
            response_text TEXT,
            input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
            output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
            estimated_cost_usd REAL CHECK (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0),
            status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
            error_message TEXT,
            latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS review_llm_calls (
            review_id INTEGER NOT NULL,
            llm_call_id INTEGER NOT NULL UNIQUE,
            PRIMARY KEY (review_id, llm_call_id),
            FOREIGN KEY (review_id) REFERENCES review_history(id),
            FOREIGN KEY (llm_call_id) REFERENCES llm_calls(id)
        );
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_card_tags_tag_id ON card_tags(tag_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_card_state_user_next_review ON user_card_state(user_id, next_review_time);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_history_user_card_reviewed ON review_history(user_id, card_id, reviewed_at);")
        
def clean_tags(tags):

    def standardize_tag(tag):
        return " ".join(word.capitalize() for word in tag.strip().split())

    if tags is None:
        return []
    if not isinstance(tags, (list, tuple)):
        raise TypeError("tags must be a list or tuple of strings")

    cleaned = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("each tag must be a string")
        clean_tag = standardize_tag(tag)
        if clean_tag and clean_tag not in seen:
            cleaned.append(clean_tag)
            seen.add(clean_tag)

    return cleaned

def add_card(
    question,
    answer,
    tags=None,
    length="short",
    grading_type = None,
    grading_criteria= None,
    llm_grading_info = None,
    user_id=DEFAULT_USER_ID,
    next_review_time=None
):
    if length not in VALID_LENGTHS:
        raise ValueError("length must be one of: short, medium, long")

    if grading_type not in VALID_GRADING_TYPES:
        raise ValueError("grading_type must be one of: binary, scaled")

    card_tags = clean_tags(tags)
    next_review_time = next_review_time or utc_now_iso()

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
        INSERT INTO cards (question, answer, length, grading_type, grading_criteria, llm_grading_info)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (question, answer, length, grading_type, grading_criteria, llm_grading_info))

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
                c.grading_type,
                c.grading_criteria,
                c.llm_grading_info,
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

def row_to_card_dict(row):
    card = dict(row)
    tags = card.get("tags", "")
    card["tags"] = [tag for tag in tags.split(",") if tag] if tags else []
    return card

def get_all_tags():
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE ASC")
            return [row["name"] for row in cur.fetchall()]
    except Exception as e:
        print("Error retrieving tags:", e)
        return []

def record_card_review(
    card_id,
    score,
    grading_mode,
    user_id=DEFAULT_USER_ID,
    user_answer=None,
    ai_feedback=None
):
    reviewed_at = utc_now_iso()

    conn = get_connection()
    cur = conn.cursor()

    try:
        review_id = record_review_history(
            cur=cur,
            card_id=card_id,
            score=score,
            grading_mode=grading_mode,
            user_id=user_id,
            user_answer=user_answer,
            ai_feedback=ai_feedback,
            reviewed_at=reviewed_at
        )

        if score != FAILED_AI_SCORE:
            record_user_card_state(
                cur=cur,
                card_id=card_id,
                score=score,
                user_id=user_id,
                reviewed_at=reviewed_at
            )

        conn.commit()
        return {
            "success": True,
            "review_id": review_id,
            "requires_manual_grading": score == FAILED_AI_SCORE
        }

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}

    finally:
        conn.close()

def record_review_history(
    cur,
    card_id,
    score,
    grading_mode,
    user_id=DEFAULT_USER_ID,
    user_answer=None,
    ai_feedback=None,
    reviewed_at=None
):
    if score not in VALID_REVIEW_SCORES:
        raise ValueError("score must be one of: -1, 1, 2, 3, 4, 5")

    if score == FAILED_AI_SCORE and grading_mode != "ai":
        raise ValueError("score -1 is only valid for failed AI grading")

    cur.execute("""
        INSERT INTO review_history (
            user_id,
            card_id,
            reviewed_at,
            grading_mode,
            score,
            user_answer,
            ai_feedback
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        card_id,
        reviewed_at,
        grading_mode,
        score,
        user_answer,
        ai_feedback
    ))

    return cur.lastrowid

def record_user_card_state(
    cur,
    card_id,
    score,
    user_id=DEFAULT_USER_ID,
    reviewed_at=None
):
    #reviewed is always passed in, do not check it
    if score not in (1, 2, 3, 4, 5):
        raise ValueError("score must be one of: 1, 2, 3, 4, 5")

    cur.execute("""
        SELECT recent_scores_json, repetitions, current_interval, last_reviewed_at
        FROM user_card_state
        WHERE user_id = ? AND card_id = ?
    """, (user_id, card_id))

    row = cur.fetchone()
    if row:
        try:
            recent_scores = json.loads(row["recent_scores_json"])
        except json.JSONDecodeError:
            recent_scores = []

        repetitions = row["repetitions"] + 1
        current_interval = row["current_interval"]
        last_review = row["last_reviewed_at"]
    else:
        recent_scores = []
        repetitions = 1
        current_interval = 1
        last_review = None

    next_review_info = calc_next_review_info(
        score=score,
        current_interval_days=current_interval,
        reviewed_at=reviewed_at,
        last_review=last_review
    )

    interval_days = next_review_info["current_interval"]
    next_review_time = next_review_info["next_review_time"]

    recent_scores.append(score)
    recent_scores = recent_scores[-MAX_PERFORMANCE_HISTORY:]

    cur.execute("""
        INSERT INTO user_card_state (
            user_id,
            card_id,
            next_review_time,
            last_reviewed_at,
            last_performance,
            current_interval,
            repetitions,
            recent_scores_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, card_id) DO UPDATE SET
            next_review_time = excluded.next_review_time,
            last_reviewed_at = excluded.last_reviewed_at,
            last_performance = excluded.last_performance,
            current_interval = excluded.current_interval,
            repetitions = excluded.repetitions,
            recent_scores_json = excluded.recent_scores_json
    """, (
        user_id,
        card_id,
        next_review_time,
        reviewed_at,
        score,
        interval_days,
        repetitions,
        json.dumps(recent_scores)
    ))

def record_llm_call(
    purpose: str,
    provider: str,
    model: str,
    request_json: str,
    status: str,
    user_id: int | None = DEFAULT_USER_ID,
    session_id: str | None = None,
    provider_request_id: str | None = None,
    response_text: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> int:
    
    if status not in {"completed", "failed"}:
        raise ValueError("status must be one of: completed, failed")
    if not purpose.strip():
        raise ValueError("purpose cannot be empty")
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO llm_calls (
            user_id, session_id, purpose, provider, model, provider_request_id,
            request_json, response_text, input_tokens, output_tokens,
            estimated_cost_usd, status, error_message, latency_ms
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, session_id, purpose, provider, model, provider_request_id,
            request_json, response_text, input_tokens, output_tokens,
            estimated_cost_usd, status, error_message, latency_ms
        ))
        return cur.lastrowid

def link_llm_call_to_review(review_id: int, llm_call_id: int) -> None:
    with get_db() as conn:
        conn.execute("""
        INSERT INTO review_llm_calls (review_id, llm_call_id)
        VALUES (?, ?)
        """, (review_id, llm_call_id))

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
