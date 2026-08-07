import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import db_lib
import sqlite3
from unittest.mock import patch
from contextlib import closing

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

class TestGetDb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_successful_context_commits_changes(self):
        with db_lib.get_db() as cur:
            cur.execute("""
                CREATE TABLE test_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            cur.execute(
                "INSERT INTO test_items (name) VALUES (?)",
                ("committed item",)
            )

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT name FROM test_items"
            ).fetchone()

        self.assertEqual(row, ("committed item",))

    def test_exception_rolls_back_changes(self):
        with db_lib.get_db() as cur:
            cur.execute("""
                CREATE TABLE test_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)

        with self.assertRaises(RuntimeError):
            with db_lib.get_db() as cur:
                cur.execute(
                    "INSERT INTO test_items (name) VALUES (?)",
                    ("rolled-back item",)
                )
                raise RuntimeError("Deliberate test exception")

        with closing(sqlite3.connect(self.db_path)) as conn:
            row_count = conn.execute(
                "SELECT COUNT(*) FROM test_items"
            ).fetchone()[0]

        self.assertEqual(row_count, 0)

    def test_foreign_key_enforcement_is_enabled(self):
        with db_lib.get_db() as cur:
            cur.execute("""
                CREATE TABLE parents (
                    id INTEGER PRIMARY KEY
                )
            """)
            cur.execute("""
                CREATE TABLE children (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES parents(id)
                )
            """)

        with self.assertRaises(sqlite3.IntegrityError):
            with db_lib.get_db() as cur:
                cur.execute(
                    "INSERT INTO children (parent_id) VALUES (?)",
                    (999,)
                )


if __name__ == "__main__":
    unittest.main()