import json
import sqlite3
from pathlib import Path

from db_lib import DB_PATH, DEFAULT_USER_ID, init_db, utc_now_iso


EXPORT_PATH = Path(__file__).parent / "cards_export.json"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def export_cards(export_path=EXPORT_PATH):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                c.id,
                c.question,
                c.answer,
                c.length,
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

        cards = []

        for row in cur.fetchall():
            card = dict(row)

            tag_text = card.get("tags", "")
            card["tags"] = [tag for tag in tag_text.split(",") if tag] if tag_text else []

            cards.append(card)

        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)

        print(f"Exported {len(cards)} cards to {export_path}")
        return cards

    finally:
        conn.close()


def import_cards_preserve_ids(export_path=EXPORT_PATH):
    if not export_path.exists():
        raise FileNotFoundError(f"Export file not found: {export_path}")

    with open(export_path, "r", encoding="utf-8") as f:
        cards = json.load(f)

    conn = get_connection()
    cur = conn.cursor()

    imported = 0

    try:
        for card in cards:
            card_id = card["id"]
            question = card["question"]
            answer = card["answer"]
            length = card.get("length", "short")
            created_at = card.get("created_at") or utc_now_iso()
            updated_at = card.get("updated_at") or utc_now_iso()
            tags = card.get("tags", [])

            cur.execute("""
                INSERT INTO cards (
                    id,
                    question,
                    answer,
                    length,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                card_id,
                question,
                answer,
                length,
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

                tag_row = cur.fetchone()
                assert tag_row is not None, "tag insert/select failed"

                tag_id = tag_row["id"]

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

            cur.execute("""
                INSERT OR IGNORE INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time
                )
                VALUES (?, ?, ?)
            """, (
                DEFAULT_USER_ID,
                card_id,
                utc_now_iso()
            ))

            imported += 1

        # Make sure future autoincrement IDs continue after the highest imported card ID.
        cur.execute("""
            UPDATE sqlite_sequence
            SET seq = (
                SELECT COALESCE(MAX(id), 0)
                FROM cards
            )
            WHERE name = 'cards'
        """)

        conn.commit()
        print(f"Imported {imported} cards with preserved IDs.")

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
    import_cards_preserve_ids(export_path)


def migrate_cards():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    export_cards()
    rebuild_db_from_export()
    print("Card migration complete.")


if __name__ == "__main__":
    migrate_cards()