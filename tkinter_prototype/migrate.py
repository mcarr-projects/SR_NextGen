import json
import sqlite3
from pathlib import Path

from db_lib import DB_PATH, DEFAULT_USER_ID, init_db, utc_now_iso


EXPORT_PATH = Path(__file__).parent / "migration_export.json"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(cur, table_name):
    cur.execute("""
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, (table_name,))
    return cur.fetchone() is not None


def get_table_columns(cur, table_name):
    if not table_exists(cur, table_name):
        return set()

    cur.execute(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in cur.fetchall()}


def export_all(export_path=EXPORT_PATH):
    conn = get_connection()
    cur = conn.cursor()

    try:
        data = {
            "cards": [],
            "user_card_state": [],
            "review_history": []
        }

        card_columns = get_table_columns(cur, "cards")
        has_grading_type = "grading_type" in card_columns

        grading_type_select = "c.grading_type," if has_grading_type else "'scaled' AS grading_type,"

        cur.execute(f"""
            SELECT
                c.id,
                c.question,
                c.answer,
                c.length,
                {grading_type_select}
                c.created_at,
                c.updated_at,
                COALESCE(GROUP_CONCAT(DISTINCT t.name), '') AS tags
            FROM cards c
            LEFT JOIN card_tags ct
                ON ct.card_id = c.id
            LEFT JOIN tags t
                ON t.id = ct.tag_id
            GROUP BY c.id
            ORDER BY c.id ASC
        """)

        for row in cur.fetchall():
            card = dict(row)
            tag_text = card.get("tags", "")
            card["tags"] = [tag for tag in tag_text.split(",") if tag] if tag_text else []
            data["cards"].append(card)

        state_columns = get_table_columns(cur, "user_card_state")
        if state_columns:
            columns_to_export = [
                "user_id",
                "card_id",
                "next_review_time",
                "last_reviewed_at",
                "last_performance",
                "current_interval",
                "repetitions",
                "ef",
                "lapse_count",
                "recent_scores_json",
            ]

            available_columns = [col for col in columns_to_export if col in state_columns]
            column_sql = ", ".join(available_columns)

            cur.execute(f"""
                SELECT {column_sql}
                FROM user_card_state
                ORDER BY user_id ASC, card_id ASC
            """)

            data["user_card_state"] = [dict(row) for row in cur.fetchall()]

        if table_exists(cur, "review_history"):
            cur.execute("""
                SELECT
                    id,
                    user_id,
                    card_id,
                    reviewed_at,
                    grading_mode,
                    score,
                    user_answer,
                    ai_feedback
                FROM review_history
                ORDER BY id ASC
            """)

            data["review_history"] = [dict(row) for row in cur.fetchall()]

        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(
            f"Exported {len(data['cards'])} cards, "
            f"{len(data['user_card_state'])} card states, and "
            f"{len(data['review_history'])} reviews to {export_path}"
        )

        return data

    finally:
        conn.close()


def import_all(export_path=EXPORT_PATH):
    if not export_path.exists():
        raise FileNotFoundError(f"Export file not found: {export_path}")

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_connection()
    cur = conn.cursor()

    try:
        for card in data.get("cards", []):
            card_id = card["id"]
            question = card["question"]
            answer = card["answer"]
            length = card.get("length", "short")
            grading_type = card.get("grading_type")
            created_at = card.get("created_at") or utc_now_iso()
            updated_at = card.get("updated_at") or utc_now_iso()
            tags = card.get("tags", [])

            cur.execute("""
                INSERT INTO cards (
                    id,
                    question,
                    answer,
                    length,
                    grading_type,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                question,
                answer,
                length,
                grading_type,
                created_at,
                updated_at
            ))

            for tag in tags:
                cur.execute("""
                    INSERT OR IGNORE INTO tags (name)
                    VALUES (?)
                """, (tag,))

                cur.execute("""
                    SELECT id
                    FROM tags
                    WHERE name = ?
                """, (tag,))

                tag_id = cur.fetchone()["id"]

                cur.execute("""
                    INSERT OR IGNORE INTO card_tags (
                        card_id,
                        tag_id
                    )
                    VALUES (?, ?)
                """, (
                    card_id,
                    tag_id
                ))

        existing_state_keys = set()

        for state in data.get("user_card_state", []):
            user_id = state.get("user_id", DEFAULT_USER_ID)
            card_id = state["card_id"]
            existing_state_keys.add((user_id, card_id))

            cur.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time,
                    last_reviewed_at,
                    last_performance,
                    current_interval,
                    repetitions,
                    ef,
                    lapse_count,
                    recent_scores_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                card_id,
                state.get("next_review_time") or utc_now_iso(),
                state.get("last_reviewed_at"),
                state.get("last_performance"),
                state.get("current_interval", 1),
                state.get("repetitions", 0),
                state.get("ef", 2.5),
                state.get("lapse_count", 0),
                state.get("recent_scores_json", "[]")
            ))

        for card in data.get("cards", []):
            state_key = (DEFAULT_USER_ID, card["id"])

            if state_key in existing_state_keys:
                continue

            cur.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time
                )
                VALUES (?, ?, ?)
            """, (
                DEFAULT_USER_ID,
                card["id"],
                utc_now_iso()
            ))

        for review in data.get("review_history", []):
            cur.execute("""
                INSERT INTO review_history (
                    id,
                    user_id,
                    card_id,
                    reviewed_at,
                    grading_mode,
                    score,
                    user_answer,
                    ai_feedback
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review["id"],
                review["user_id"],
                review["card_id"],
                review["reviewed_at"],
                review["grading_mode"],
                review["score"],
                review.get("user_answer"),
                review.get("ai_feedback")
            ))

        for table_name in ("cards", "review_history"):
            cur.execute(f"""
                UPDATE sqlite_sequence
                SET seq = (
                    SELECT COALESCE(MAX(id), 0)
                    FROM {table_name}
                )
                WHERE name = ?
            """, (table_name,))

        conn.commit()

        print(
            f"Imported {len(data.get('cards', []))} cards, "
            f"{len(data.get('user_card_state', []))} card states, and "
            f"{len(data.get('review_history', []))} reviews."
        )

    except Exception as e:
        conn.rollback()
        print("Import failed:", e)
        raise

    finally:
        conn.close()


def make_backup_path():
    base_backup_path = DB_PATH.with_suffix(".db.backup")

    if not base_backup_path.exists():
        return base_backup_path

    i = 1
    while True:
        backup_path = DB_PATH.with_suffix(f".db.backup{i}")
        if not backup_path.exists():
            return backup_path
        i += 1


def rebuild_db_from_export(export_path=EXPORT_PATH):
    if DB_PATH.exists():
        backup_path = make_backup_path()
        DB_PATH.replace(backup_path)
        print(f"Moved old database to {backup_path}")

    init_db()
    import_all(export_path)


def migrate_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    export_all()
    rebuild_db_from_export()
    print("Database migration complete.")


if __name__ == "__main__":
    migrate_db()