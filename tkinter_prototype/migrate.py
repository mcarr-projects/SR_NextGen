import json
import sqlite3
from pathlib import Path

from db_lib import DB_PATH, DEFAULT_USER_ID, init_db, utc_now_iso


EXPORT_PATH = Path(__file__).parent / "migration_export.json"


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
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


def export_all(source_db_path=DB_PATH, export_path=EXPORT_PATH):
    source_db_path = Path(source_db_path)

    if not source_db_path.exists():
        raise FileNotFoundError(f"Source database file not found: {source_db_path}")

    conn = get_connection(source_db_path)
    cur = conn.cursor()

    try:
        data = {
            "cards": [],
            "user_card_state": [],
            "review_history": [],
            "llm_calls": [],
            "review_llm_calls": []
        }

        card_columns = get_table_columns(cur, "cards")
        has_grading_type = "grading_type" in card_columns
        has_grading_criteria = "grading_criteria" in card_columns
        has_llm_grading_info = "llm_grading_info" in card_columns
        
        grading_type_select = "c.grading_type," if has_grading_type else "'scaled' AS grading_type,"
        grading_criteria_select = ("c.grading_criteria," if has_grading_criteria 
                                   else "NULL AS grading_criteria,")
        llm_grading_info_select = ("c.llm_grading_info," if has_llm_grading_info
                                   else "NULL AS llm_grading_info,")
        


        cur.execute(f"""
            SELECT
                c.id,
                c.question,
                c.answer,
                c.length,
                {grading_type_select}
                {grading_criteria_select}
                {llm_grading_info_select}
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

        if table_exists(cur, "llm_calls"):
            cur.execute("""
                SELECT
                    id,
                    user_id,
                    session_id,
                    purpose,
                    provider,
                    model,
                    provider_request_id,
                    request_json,
                    response_text,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    status,
                    error_message,
                    latency_ms,
                    created_at
                FROM llm_calls
                ORDER BY id ASC
            """)

            data["llm_calls"] = [dict(row) for row in cur.fetchall()]

        if table_exists(cur, "review_llm_calls"):
            cur.execute("""
                SELECT review_id, llm_call_id
                FROM review_llm_calls
                ORDER BY review_id ASC, llm_call_id ASC
            """)

            data["review_llm_calls"] = [dict(row) for row in cur.fetchall()]

        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(
            f"Exported {len(data['cards'])} cards, "
            f"{len(data['user_card_state'])} card states, and "
            f"{len(data['review_history'])} reviews, "
            f"{len(data['llm_calls'])} LLM calls, and "
            f"{len(data['review_llm_calls'])} review/LLM links from "
            f"{source_db_path} to {export_path}"
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
            grading_criteria = card.get("grading_criteria")
            llm_grading_info = card.get("llm_grading_info")

            cur.execute("""
                INSERT INTO cards (
                    id,
                    question,
                    answer,
                    length,
                    grading_type,
                    grading_criteria,
                    llm_grading_info,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                question,
                answer,
                length,
                grading_type,
                grading_criteria,
                llm_grading_info,
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

        for llm_call in data.get("llm_calls", []):
            cur.execute("""
                INSERT INTO llm_calls (
                    id,
                    user_id,
                    session_id,
                    purpose,
                    provider,
                    model,
                    provider_request_id,
                    request_json,
                    response_text,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    status,
                    error_message,
                    latency_ms,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                llm_call["id"],
                llm_call.get("user_id"),
                llm_call.get("session_id"),
                llm_call["purpose"],
                llm_call["provider"],
                llm_call["model"],
                llm_call.get("provider_request_id"),
                llm_call["request_json"],
                llm_call.get("response_text"),
                llm_call.get("input_tokens"),
                llm_call.get("output_tokens"),
                llm_call.get("estimated_cost_usd"),
                llm_call["status"],
                llm_call.get("error_message"),
                llm_call.get("latency_ms"),
                llm_call.get("created_at") or utc_now_iso()
            ))

        for link in data.get("review_llm_calls", []):
            cur.execute("""
                INSERT INTO review_llm_calls (review_id, llm_call_id)
                VALUES (?, ?)
            """, (link["review_id"], link["llm_call_id"]))

        for table_name in ("cards", "review_history", "llm_calls"):
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
            f"{len(data.get('review_history', []))} reviews, "
            f"{len(data.get('llm_calls', []))} LLM calls, and "
            f"{len(data.get('review_llm_calls', []))} review/LLM links."
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


def migrate_db(source_db_path=DB_PATH):
    export_all(source_db_path)
    rebuild_db_from_export()
    print("Database migration complete.")


def select_source_db():
    while True:
        use_default = input(f"Migrate the current default database, {DB_PATH.name}? (y/n): ").strip().lower()
        if use_default in {"y", "yes"}:
            return DB_PATH
        if use_default in {"n", "no"}:
            break
        print("Please enter y or n.")

    while True:
        filename = input("Enter the filename of a database in the current working directory: ").strip()
        source_db_path = Path.cwd() / filename

        if not filename:
            print("Please enter a filename.")
        elif Path(filename).name != filename:
            print("Please enter only a filename, not a path.")
        elif not source_db_path.is_file():
            print(f"Database file not found: {source_db_path}")
        elif source_db_path.resolve() == DB_PATH.resolve():
            print(f"That is the default database. Choose y at the first prompt to migrate {DB_PATH.name}.")
        else:
            print(f"Using source database: {source_db_path}")
            return source_db_path


if __name__ == "__main__":
    migrate_db(select_source_db())
