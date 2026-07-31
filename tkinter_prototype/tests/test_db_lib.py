import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import db_lib


DUMMY_CARD = {
    "question": "What is 2 + 2?",
    "answer": "4",
    "tags": ["Testing", "Arithmetic"],
    "length": "short",
    "grading_type": "binary",
    "grading_criteria": "The answer must equal 4.",
    "llm_grading_info": "This is dummy test data.",
    "user_id": db_lib.DEFAULT_USER_ID,
    "next_review_time": "2026-01-01T00:00:00+00:00"
}

DUMMY_REVIEW = {
    "score": 5,
    "grading_mode": "ai",
    "user_id": db_lib.DEFAULT_USER_ID,
    "user_answer": "4",
    "ai_feedback": "Correct."
}

DUMMY_LLM = {
    "purpose": "testing",
    "provider": "self",
    "model": "testing_dummy",
    "request_json": '{"student_answer": "4"}',
    "response_text": '{"score": 5, "feedback": "Correct."}',
    "input_tokens": 1,
    "output_tokens": 1,
    "status": "completed",
    "error_message": None
}


class TestDbLib(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db_lib.DB_PATH
        db_lib.DB_PATH = Path(self.temp_dir.name) / "test.db"
        db_lib.init_db()

    def tearDown(self):
        db_lib.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def add_dummy_card(self):
        result = db_lib.add_card(**DUMMY_CARD)
        self.assertTrue(result["success"], result)
        return result["card_id"]

    def test_init_db(self):
        expected_tables = {
            "cards", "tags", "card_tags", "user_card_state", "review_history",
            "llm_calls", "review_llm_calls"
        }
        expected_indexes = {
            "idx_card_tags_tag_id",
            "idx_user_card_state_user_next_review",
            "idx_review_history_user_card_reviewed"
        }

        db_lib.init_db()
        with db_lib.get_db() as conn:
            tables = {
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            indexes = {
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
                )
            }
            foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()

        self.assertEqual(tables, expected_tables)
        self.assertTrue(expected_indexes <= indexes)
        self.assertEqual(foreign_key_errors, [])

    def record_dummy_review(self):
        card_id = self.add_dummy_card()
        result = db_lib.record_card_review(card_id=card_id, **DUMMY_REVIEW)
        self.assertTrue(result["success"], result)
        return card_id, result["review_id"]

    def test_add_card(self):
        card_id = self.add_dummy_card()

        with db_lib.get_db() as conn:
            card = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
            state = conn.execute("""
                SELECT * FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (DUMMY_CARD["user_id"], card_id)).fetchone()
            tags = conn.execute("""
                SELECT t.name
                FROM tags t
                JOIN card_tags ct ON ct.tag_id = t.id
                WHERE ct.card_id = ?
                ORDER BY t.name
            """, (card_id,)).fetchall()

        self.assertIsNotNone(card)
        for field in ("question", "answer", "length", "grading_type", "grading_criteria", "llm_grading_info"):
            self.assertEqual(card[field], DUMMY_CARD[field])
        datetime.fromisoformat(card["created_at"])
        datetime.fromisoformat(card["updated_at"])

        self.assertIsNotNone(state)
        self.assertEqual(state["user_id"], DUMMY_CARD["user_id"])
        self.assertEqual(state["card_id"], card_id)
        self.assertEqual(state["next_review_time"], DUMMY_CARD["next_review_time"])
        self.assertEqual([row["name"] for row in tags], sorted(DUMMY_CARD["tags"]))

    def test_record_card_review(self):
        card_id, review_id = self.record_dummy_review()

        with db_lib.get_db() as conn:
            review = conn.execute(
                "SELECT * FROM review_history WHERE id = ?",
                (review_id,)
            ).fetchone()
            state = conn.execute("""
                SELECT * FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (DUMMY_REVIEW["user_id"], card_id)).fetchone()

        self.assertIsNotNone(review)
        self.assertEqual(review["card_id"], card_id)
        for field, value in DUMMY_REVIEW.items():
            self.assertEqual(review[field], value)
        datetime.fromisoformat(review["reviewed_at"])

        self.assertEqual(state["last_reviewed_at"], review["reviewed_at"])
        self.assertEqual(state["last_performance"], DUMMY_REVIEW["score"])
        self.assertEqual(state["repetitions"], 1)
        self.assertEqual(json.loads(state["recent_scores_json"]), [DUMMY_REVIEW["score"]])
        datetime.fromisoformat(state["next_review_time"])

    def test_record_llm_call(self):
        _, review_id = self.record_dummy_review()

        llm_call_id = db_lib.record_llm_call(**DUMMY_LLM)
        db_lib.link_llm_call_to_review(review_id, llm_call_id)

        with db_lib.get_db() as conn:
            llm_call = conn.execute(
                "SELECT * FROM llm_calls WHERE id = ?",
                (llm_call_id,)
            ).fetchone()
            link = conn.execute("""
                SELECT * FROM review_llm_calls
                WHERE review_id = ? AND llm_call_id = ?
            """, (review_id, llm_call_id)).fetchone()

        self.assertIsNotNone(llm_call)
        for field, value in DUMMY_LLM.items():
            self.assertEqual(llm_call[field], value)
        datetime.fromisoformat(llm_call["created_at"])
        self.assertIsNotNone(link)


if __name__ == "__main__":
    unittest.main()