import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from sr_models import Card, ReviewItem, UserCardState, validate_score

DB_PATH = Path(__file__).parent / "spacedrep.db"
PRIVATE_PATH = Path(__file__).resolve().parent.parent.parent / "SR_Private"

if str(PRIVATE_PATH) not in sys.path:
    sys.path.insert(0, str(PRIVATE_PATH))

from review_scheduling import calc_next_review_info

DEFAULT_USER_ID = 1
MAX_PERFORMANCE_HISTORY = 100
FAILED_AI_SCORE = -1

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

def validate_next_review_time(next_review_time: str) -> str:
    if not isinstance(next_review_time, str):
        raise TypeError("next_review_time must be an ISO datetime string")

    try:
        parsed_time = parse_iso_datetime(next_review_time)
    except ValueError as error:
        raise ValueError(
            "next_review_time must be a valid ISO datetime string"
        ) from error

    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise ValueError("next_review_time must include timezone information")

    return parsed_time.astimezone(timezone.utc).isoformat()

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def parse_iso_datetime(dt_text):
    return datetime.fromisoformat(dt_text)

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
            is_deprecated INTEGER NOT NULL DEFAULT 0
                CHECK (is_deprecated IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS card_deprecations (
            card_id INTEGER PRIMARY KEY,
            deprecated_at TEXT NOT NULL,
            FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
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
        
def add_card(
    card: Card,
    user_id: int = DEFAULT_USER_ID,
    next_review_time: str | None = None
) -> Card:
    if not isinstance(card, Card):
        raise TypeError("card must be a Card")

    card.validate_for_creation()

    if next_review_time is None:
        next_review_time = utc_now_iso()

    next_review_time = validate_next_review_time(next_review_time)

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO cards (
                question,
                answer,
                length,
                grading_type,
                grading_criteria,
                llm_grading_info
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            card.question,
            card.answer,
            card.length,
            card.grading_type,
            card.grading_criteria,
            card.llm_grading_info
        ))

        card_id = cur.lastrowid

        for tag in card.tags:
            cur.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                (tag,)
            )
            cur.execute(
                "SELECT id FROM tags WHERE name = ?",
                (tag,)
            )
            tag_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT OR IGNORE INTO card_tags (card_id, tag_id)
                VALUES (?, ?)
            """, (card_id, tag_id))

        cur.execute("""
            INSERT INTO user_card_state (
                user_id,
                card_id,
                next_review_time
            )
            VALUES (?, ?, ?)
        """, (user_id, card_id, next_review_time))

        cur.execute("""
            SELECT created_at, updated_at
            FROM cards
            WHERE id = ?
        """, (card_id,))
        timestamp_row = cur.fetchone()

    card.id = card_id
    card.created_at = timestamp_row["created_at"]
    card.updated_at = timestamp_row["updated_at"]
    return card

def get_cards(
    tags: list[str],
    user_id: int = DEFAULT_USER_ID
) -> list[ReviewItem]:
    if not isinstance(tags, list):
        raise TypeError("tags must be a list; use ['ALL'] to fetch all cards")

    if not tags:
        raise ValueError(
            "tags must be a non-empty list; use ['ALL'] to fetch all cards"
        )

    if any(not isinstance(tag, str) for tag in tags):
        raise TypeError("each tag must be a string")

    tags = list(dict.fromkeys(tags))

    if "ALL" in tags and tags != ["ALL"]:
        raise ValueError("use ['ALL'] by itself, not mixed with other tags")

    with get_db() as conn:
        cur = conn.cursor()

        if tags == ["ALL"]:
            cur.execute("""
                SELECT id
                FROM cards
                WHERE is_deprecated = 0
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
                AND c.is_deprecated = 0
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
                c.is_deprecated,
                ucs.user_id,
                ucs.next_review_time,
                ucs.last_reviewed_at,
                ucs.last_performance,
                ucs.current_interval,
                ucs.repetitions,
                ucs.ef,
                ucs.lapse_count,
                ucs.recent_scores_json,
                COALESCE(
                    GROUP_CONCAT(DISTINCT t.name),
                    ''
                ) AS tags
            FROM cards c
            JOIN user_card_state ucs
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

        return [row_to_review_item(row) for row in cur.fetchall()]

def row_to_review_item(row: sqlite3.Row) -> ReviewItem:
    tags = [
        tag
        for tag in row["tags"].split(",")
        if tag
    ]

    try:
        recent_scores = json.loads(row["recent_scores_json"])
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"invalid recent_scores_json for card {row['id']}"
        ) from error

    card = Card(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        length=row["length"],
        grading_type=row["grading_type"],
        grading_criteria=row["grading_criteria"],
        llm_grading_info=row["llm_grading_info"],
        tags=tags,
        is_deprecated=bool(row["is_deprecated"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )

    state = UserCardState(
        user_id=row["user_id"],
        card_id=row["id"],
        next_review_time=row["next_review_time"],
        last_reviewed_at=row["last_reviewed_at"],
        last_performance=row["last_performance"],
        current_interval=row["current_interval"],
        repetitions=row["repetitions"],
        ef=row["ef"],
        lapse_count=row["lapse_count"],
        recent_scores=recent_scores
    )

    return ReviewItem(card=card, state=state)

def get_all_tags() -> list[str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM tags ORDER BY name COLLATE NOCASE ASC"
        )
        return [row["name"] for row in cur.fetchall()]

def record_card_review(
    review_item: ReviewItem,
    score: int,
    grading_mode: str,
    user_answer: str | None = None,
    ai_feedback: str | None = None,
    llm_call_id: int | None = None
):
    if not isinstance(review_item, ReviewItem):
        raise TypeError("review_item must be a ReviewItem")

    reviewed_at = utc_now_iso()

    with get_db() as conn:
        cur = conn.cursor()

        review_id = record_review_history(
            cur=cur,
            card_id=review_item.id,
            score=score,
            grading_mode=grading_mode,
            user_id=review_item.user_id,
            user_answer=user_answer,
            ai_feedback=ai_feedback,
            reviewed_at=reviewed_at
        )

        if llm_call_id is not None:
            cur.execute("""
                INSERT INTO review_llm_calls (
                    review_id,
                    llm_call_id
                )
                VALUES (?, ?)
            """, (review_id, llm_call_id))

        if score != FAILED_AI_SCORE:
            record_user_card_state(
                cur=cur,
                card_id=review_item.id,
                score=score,
                user_id=review_item.user_id,
                reviewed_at=reviewed_at
            )

    return {
        "success": True,
        "review_id": review_id,
        "requires_manual_grading": score == FAILED_AI_SCORE
    }

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
    validate_score(score, allow_failed_ai=True)

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
    #reviewed_at is always passed internally, do not check it
    validate_score(score)

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
    next_review_time = validate_next_review_time(next_review_info["next_review_time"])

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

def deprecate_card(card_id: int) -> None:
    if not isinstance(card_id, int) or card_id <= 0:
        raise ValueError("card_id must be a positive integer")

    deprecated_at = utc_now_iso()

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            UPDATE cards
            SET is_deprecated = 1,
                updated_at = ?
            WHERE id = ?
              AND is_deprecated = 0
        """, (deprecated_at, card_id))

        if cur.rowcount == 0:
            cur.execute(
                "SELECT is_deprecated FROM cards WHERE id = ?",
                (card_id,)
            )
            row = cur.fetchone()

            if row is None:
                raise ValueError(f"card {card_id} does not exist")
            raise ValueError(f"card {card_id} is already deprecated")

        cur.execute("""
            INSERT INTO card_deprecations (
                card_id,
                deprecated_at
            )
            VALUES (?, ?)
        """, (card_id, deprecated_at))

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
