import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import db_lib
import sqlite3
from unittest.mock import patch
from contextlib import closing
from sr_models import Card, ReviewItem, Deck, UserCardState

DUMMY_TIME = "2026-01-01T00:00:00+00:00"
NEXT_REVIEW_TIME = "2026-01-05T00:00:00+00:00"
OTHER_USER_ID = 2

DUMMY_CARD = {
    "question": "What is 2 + 2?",
    "answer": "4",
    "tags": ["Testing", "Arithmetic"],
    "length": "short",
    "grading_type": "binary",
    "grading_criteria": "The answer must equal 4.",
    "llm_grading_info": "This is dummy test data.",
    "user_id": db_lib.DEFAULT_USER_ID,
    "next_review_time": DUMMY_TIME
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

def make_dummy_card(**overrides):
    card_data = {
        key: DUMMY_CARD[key]
        for key in (
            "question",
            "answer",
            "tags",
            "length",
            "grading_type",
            "grading_criteria",
            "llm_grading_info"
        )
    }
    card_data.update(overrides)
    return Card(**card_data)

def create_test_user(
    user_id=OTHER_USER_ID,
    username="other-user",
    role="user"
):
    with db_lib.get_db() as conn:
        conn.execute("""
            INSERT INTO prototype_users (
                id,
                username,
                role
            )
            VALUES (?, ?, ?)
        """, (user_id, username, role))

def make_dummy_deck(**overrides):
    deck_data = {
        "name": "Testing Deck",
        "owner_user_id": OTHER_USER_ID
    }
    deck_data.update(overrides)
    return Deck(**deck_data)

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

class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_init_db_creates_usable_database(self):
        db_lib.init_db()

        with db_lib.get_db() as conn:
            card_id = conn.execute("""
                INSERT INTO cards (question, answer, grading_type)
                VALUES (?, ?, ?)
            """, (
                DUMMY_CARD["question"],
                DUMMY_CARD["answer"],
                DUMMY_CARD["grading_type"]
            )).lastrowid

            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time
                )
                VALUES (?, ?, ?)
            """, (
                DUMMY_CARD["user_id"],
                card_id,
                DUMMY_CARD["next_review_time"]
            ))

            review_id = conn.execute("""
                INSERT INTO review_history (
                    user_id,
                    card_id,
                    reviewed_at,
                    grading_mode,
                    score
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                DUMMY_REVIEW["user_id"],
                card_id,
                DUMMY_TIME,
                DUMMY_REVIEW["grading_mode"],
                DUMMY_REVIEW["score"]
            )).lastrowid

            llm_call_id = conn.execute("""
                INSERT INTO llm_calls (
                    purpose,
                    provider,
                    model,
                    request_json,
                    status
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                DUMMY_LLM["purpose"],
                DUMMY_LLM["provider"],
                DUMMY_LLM["model"],
                DUMMY_LLM["request_json"],
                "completed"
            )).lastrowid

            conn.execute("""
                INSERT INTO review_llm_calls (review_id, llm_call_id)
                VALUES (?, ?)
            """, (review_id, llm_call_id))

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    cards.question,
                    review_history.score,
                    llm_calls.provider
                FROM cards
                JOIN review_history
                    ON review_history.card_id = cards.id
                JOIN review_llm_calls
                    ON review_llm_calls.review_id = review_history.id
                JOIN llm_calls
                    ON llm_calls.id = review_llm_calls.llm_call_id
                WHERE cards.id = ?
            """, (card_id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (
                DUMMY_CARD["question"],
                DUMMY_REVIEW["score"],
                DUMMY_LLM["provider"]
            )
        )

    def test_init_db_is_idempotent(self):
        db_lib.init_db()

        with db_lib.get_db() as conn:
            conn.execute("""
                INSERT INTO cards (question, answer, grading_type)
                VALUES (?, ?, ?)
            """, (
                DUMMY_CARD["question"],
                DUMMY_CARD["answer"],
                DUMMY_CARD["grading_type"]
            ))

        db_lib.init_db()

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT question, answer
                FROM cards
            """).fetchone()

        self.assertEqual(
            tuple(row),
            (
                DUMMY_CARD["question"],
                DUMMY_CARD["answer"]
            )
        )

class TestAddCard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_add_card_saves_card_and_tags_without_state(self):
        card = make_dummy_card()

        result = db_lib.add_card(card)

        self.assertIs(result, card)
        self.assertIsNotNone(card.id)
        self.assertIsNotNone(card.created_at)
        self.assertIsNotNone(card.updated_at)

        with db_lib.get_db() as conn:
            card_row = conn.execute("""
                SELECT
                    question,
                    answer,
                    length,
                    grading_type,
                    grading_criteria,
                    llm_grading_info,
                    created_at,
                    updated_at
                FROM cards
                WHERE id = ?
            """, (card.id,)).fetchone()

            tag_rows = conn.execute("""
                SELECT tags.name
                FROM tags
                JOIN card_tags ON card_tags.tag_id = tags.id
                WHERE card_tags.card_id = ?
            """, (card.id,)).fetchall()

            state_row = conn.execute("""
                SELECT *
                FROM user_card_state
                WHERE card_id = ?
            """, (card.id,)).fetchone()

        self.assertEqual(
            tuple(card_row),
            (
                DUMMY_CARD["question"],
                DUMMY_CARD["answer"],
                DUMMY_CARD["length"],
                DUMMY_CARD["grading_type"],
                DUMMY_CARD["grading_criteria"],
                DUMMY_CARD["llm_grading_info"],
                card.created_at,
                card.updated_at
            )
        )
        self.assertEqual(
            {row["name"] for row in tag_rows},
            set(DUMMY_CARD["tags"])
        )
        self.assertIsNone(state_row)

    def test_add_card_reuses_existing_tags(self):
        shared_tag = DUMMY_CARD["tags"][0]
        first_card = make_dummy_card(tags=[shared_tag])
        second_card = make_dummy_card(
            question="What is 3 + 3?",
            answer="6",
            tags=[shared_tag]
        )

        db_lib.add_card(first_card)
        db_lib.add_card(second_card)

        with db_lib.get_db() as conn:
            tag_count = conn.execute("""
                SELECT COUNT(*)
                FROM tags
                WHERE name = ?
            """, (shared_tag,)).fetchone()[0]

            linked_card_rows = conn.execute("""
                SELECT card_tags.card_id
                FROM card_tags
                JOIN tags ON tags.id = card_tags.tag_id
                WHERE tags.name = ?
            """, (shared_tag,)).fetchall()

        self.assertEqual(tag_count, 1)
        self.assertEqual(
            {row["card_id"] for row in linked_card_rows},
            {first_card.id, second_card.id}
        )

    def test_add_card_rejects_non_card(self):
        with self.assertRaises(TypeError):
            db_lib.add_card(DUMMY_CARD)

        with db_lib.get_db() as conn:
            card_count = conn.execute(
                "SELECT COUNT(*) FROM cards"
            ).fetchone()[0]

        self.assertEqual(card_count, 0)

class TestGetCardsByTags(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_get_cards_by_tags_all_returns_complete_cards_in_card_id_order(self):
        first_card = make_dummy_card()
        second_card = make_dummy_card(
            question="What is 3 + 3?",
            answer="6",
            tags=["Testing"]
        )

        db_lib.add_card(first_card)
        db_lib.add_card(second_card)

        results = db_lib.get_cards_by_tags(["ALL"])

        self.assertEqual(len(results), 2)
        self.assertTrue(
            all(isinstance(card, Card) for card in results)
        )
        self.assertEqual(
            [card.id for card in results],
            [first_card.id, second_card.id]
        )

        first_result = results[0]

        self.assertEqual(
            (
                first_result.question,
                first_result.answer,
                first_result.length,
                first_result.grading_type,
                first_result.grading_criteria,
                first_result.llm_grading_info,
                first_result.created_at,
                first_result.updated_at
            ),
            (
                DUMMY_CARD["question"],
                DUMMY_CARD["answer"],
                DUMMY_CARD["length"],
                DUMMY_CARD["grading_type"],
                DUMMY_CARD["grading_criteria"],
                DUMMY_CARD["llm_grading_info"],
                first_card.created_at,
                first_card.updated_at
            )
        )
        self.assertEqual(
            set(first_result.tags),
            set(DUMMY_CARD["tags"])
        )

    def test_get_cards_by_tags_filters_by_all_requested_tags(self):
        both_tags_card = make_dummy_card()
        single_tag_card = make_dummy_card(
            question="What is 3 + 3?",
            answer="6",
            tags=["Testing"]
        )
        unrelated_card = make_dummy_card(
            question="What is the capital of France?",
            answer="Paris",
            tags=["Geography"]
        )

        for card in (
            both_tags_card,
            single_tag_card,
            unrelated_card
        ):
            db_lib.add_card(card)

        single_tag_results = db_lib.get_cards_by_tags(["Testing"])
        both_tag_results = db_lib.get_cards_by_tags(
            ["Testing", "Arithmetic"]
        )
        unknown_tag_results = db_lib.get_cards_by_tags(["Unknown"])

        self.assertEqual(
            [card.id for card in single_tag_results],
            [both_tags_card.id, single_tag_card.id]
        )
        self.assertEqual(
            [card.id for card in both_tag_results],
            [both_tags_card.id]
        )
        self.assertEqual(unknown_tag_results, [])

    def test_get_cards_by_tags_validates_tags(self):
        card = make_dummy_card(tags=["Testing"])
        db_lib.add_card(card)

        invalid_inputs = (
            ("Testing", TypeError),
            (("Testing",), TypeError),
            (None, TypeError),
            ([], ValueError),
            (["Testing", 5], TypeError),
            (["ALL", "Testing"], ValueError)
        )

        for tags, expected_error in invalid_inputs:
            with self.subTest(tags=tags):
                with self.assertRaises(expected_error):
                    db_lib.get_cards_by_tags(tags)

        single_result = db_lib.get_cards_by_tags(["Testing"])
        duplicate_result = db_lib.get_cards_by_tags(
            ["Testing", "Testing"]
        )

        self.assertEqual(
            [card.id for card in duplicate_result],
            [card.id for card in single_result]
        )

    def test_get_cards_by_tags_excludes_deprecated_cards(self):
        active_card = make_dummy_card()
        deprecated_card = make_dummy_card(
            question="What is 3 + 3?",
            answer="6"
        )

        db_lib.add_card(active_card)
        db_lib.add_card(deprecated_card)

        with db_lib.get_db() as conn:
            conn.execute("""
                UPDATE cards
                SET is_deprecated = 1
                WHERE id = ?
            """, (deprecated_card.id,))

        all_results = db_lib.get_cards_by_tags(["ALL"])
        tag_results = db_lib.get_cards_by_tags(["Testing"])

        self.assertEqual(
            [card.id for card in all_results],
            [active_card.id]
        )
        self.assertEqual(
            [card.id for card in tag_results],
            [active_card.id]
        )

class TestGetUserCardStates(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

        self.first_card = make_dummy_card()
        self.second_card = make_dummy_card(
            question="What is 3 + 3?",
            answer="6"
        )

        db_lib.add_card(self.first_card)
        db_lib.add_card(self.second_card)

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_get_user_card_states_returns_states_keyed_by_card_id(self):
        with db_lib.get_db() as conn:
            conn.execute("""
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
                OTHER_USER_ID,
                self.first_card.id,
                NEXT_REVIEW_TIME,
                DUMMY_TIME,
                5,
                4,
                3,
                2.2,
                1,
                json.dumps([3, 4, 5])
            ))

        results = db_lib.get_user_card_states(OTHER_USER_ID)

        self.assertEqual(
            list(results),
            [self.first_card.id]
        )

        state = results[self.first_card.id]

        self.assertIsInstance(state, UserCardState)
        self.assertEqual(
            (
                state.user_id,
                state.card_id,
                state.next_review_time,
                state.last_reviewed_at,
                state.last_performance,
                state.current_interval,
                state.repetitions,
                state.ef,
                state.lapse_count,
                state.recent_scores
            ),
            (
                OTHER_USER_ID,
                self.first_card.id,
                NEXT_REVIEW_TIME,
                DUMMY_TIME,
                5,
                4,
                3,
                2.2,
                1,
                [3, 4, 5]
            )
        )

    def test_get_user_card_states_isolates_users(self):
        with db_lib.get_db() as conn:
            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time
                )
                VALUES (?, ?, ?)
            """, (
                db_lib.DEFAULT_USER_ID,
                self.first_card.id,
                DUMMY_TIME
            ))

            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time
                )
                VALUES (?, ?, ?)
            """, (
                OTHER_USER_ID,
                self.second_card.id,
                NEXT_REVIEW_TIME
            ))

        default_states = db_lib.get_user_card_states(
            db_lib.DEFAULT_USER_ID
        )
        other_states = db_lib.get_user_card_states(OTHER_USER_ID)

        self.assertEqual(
            set(default_states),
            {self.first_card.id}
        )
        self.assertEqual(
            set(other_states),
            {self.second_card.id}
        )

    def test_get_user_card_states_rejects_malformed_recent_scores(self):
        with db_lib.get_db() as conn:
            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time,
                    recent_scores_json
                )
                VALUES (?, ?, ?, ?)
            """, (
                OTHER_USER_ID,
                self.first_card.id,
                DUMMY_TIME,
                "not valid JSON"
            ))

        with self.assertRaisesRegex(
            ValueError,
            rf"invalid recent_scores_json for card {self.first_card.id}"
        ):
            db_lib.get_user_card_states(OTHER_USER_ID)

    def test_get_user_card_states_returns_empty_dict_when_no_state_exists(self):
        self.assertEqual(
            db_lib.get_user_card_states(OTHER_USER_ID),
            {}
        )

class TestGetAllTags(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_get_all_tags_returns_all_tags_sorted(self):
        first_card = make_dummy_card(
            tags=["Testing", "arithmetic"]
        )
        second_card = make_dummy_card(
            question="What is the capital of France?",
            answer="Paris",
            tags=["Geography", "Testing"]
        )

        db_lib.add_card(first_card)
        db_lib.add_card(second_card)

        self.assertEqual(
            db_lib.get_all_tags(),
            ["Arithmetic", "Geography", "Testing"]
        )

    def test_get_all_tags_returns_empty_list_when_no_tags_exist(self):
        self.assertEqual(db_lib.get_all_tags(), [])

class TestRecordCardReview(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_record_card_review_records_successful_review(self):
        card = make_dummy_card()
        db_lib.add_card(card)
        review_item = ReviewItem(
            card=card,
            state=UserCardState(
                user_id=OTHER_USER_ID,
                card_id=card.id,
                next_review_time=DUMMY_TIME
            )
        )

        with patch.object(
            db_lib,
            "utc_now_iso",
            return_value=DUMMY_TIME
        ), patch.object(
            db_lib,
            "calc_next_review_info",
            return_value={
                "current_interval": 4,
                "next_review_time": NEXT_REVIEW_TIME
            }
        ):
            result = db_lib.record_card_review(
                review_item=review_item,
                score=DUMMY_REVIEW["score"],
                grading_mode=DUMMY_REVIEW["grading_mode"],
                user_answer=DUMMY_REVIEW["user_answer"],
                ai_feedback=DUMMY_REVIEW["ai_feedback"]
            )

        self.assertTrue(result["success"])
        self.assertFalse(result["requires_manual_grading"])
        self.assertIsInstance(result["review_id"], int)

        with db_lib.get_db() as conn:
            history_row = conn.execute("""
                SELECT user_id, card_id, score
                FROM review_history
                WHERE id = ?
            """, (result["review_id"],)).fetchone()

            state_row = conn.execute("""
                SELECT
                    next_review_time,
                    last_performance,
                    current_interval,
                    repetitions
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (OTHER_USER_ID, card.id)).fetchone()

        self.assertEqual(
            tuple(history_row),
            (
                OTHER_USER_ID,
                card.id,
                DUMMY_REVIEW["score"]
            )
        )
        self.assertEqual(
            tuple(state_row),
            (
                NEXT_REVIEW_TIME,
                DUMMY_REVIEW["score"],
                4,
                1
            )
        )

    def test_record_card_review_records_failed_ai_and_links_llm_call(self):
        card = make_dummy_card()
        db_lib.add_card(card)
        review_item = ReviewItem(
            card=card,
            state=UserCardState(
                user_id=db_lib.DEFAULT_USER_ID,
                card_id=card.id,
                next_review_time=DUMMY_TIME
            )
        )
        llm_call_id = db_lib.record_llm_call(**DUMMY_LLM)

        with db_lib.get_db() as conn:
            state_before = tuple(conn.execute("""
                SELECT *
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                db_lib.DEFAULT_USER_ID,
                card.id
            )).fetchone())

        with patch.object(
            db_lib,
            "utc_now_iso",
            return_value=DUMMY_TIME
        ):
            result = db_lib.record_card_review(
                review_item=review_item,
                score=db_lib.FAILED_AI_SCORE,
                grading_mode="ai",
                llm_call_id=llm_call_id
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["requires_manual_grading"])

        with db_lib.get_db() as conn:
            history_row = conn.execute("""
                SELECT user_id, card_id, score
                FROM review_history
                WHERE id = ?
            """, (result["review_id"],)).fetchone()

            link_row = conn.execute("""
                SELECT review_id, llm_call_id
                FROM review_llm_calls
                WHERE review_id = ?
            """, (result["review_id"],)).fetchone()

            state_after = tuple(conn.execute("""
                SELECT *
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                db_lib.DEFAULT_USER_ID,
                card.id
            )).fetchone())

        self.assertEqual(
            tuple(history_row),
            (
                db_lib.DEFAULT_USER_ID,
                card.id,
                db_lib.FAILED_AI_SCORE
            )
        )
        self.assertEqual(
            tuple(link_row),
            (result["review_id"], llm_call_id)
        )
        self.assertEqual(state_after, state_before)

    def test_record_card_review_rejects_non_review_item(self):
        with self.assertRaises(TypeError):
            db_lib.record_card_review(
                review_item=make_dummy_card(),
                score=5,
                grading_mode="manual"
            )

class TestRecordReviewHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

        self.card = make_dummy_card()
        db_lib.add_card(self.card)

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_record_review_history_saves_review_and_returns_id(self):
        with db_lib.get_db() as conn:
            review_id = db_lib.record_review_history(
                conn.cursor(),
                card_id=self.card.id,
                score=DUMMY_REVIEW["score"],
                grading_mode=DUMMY_REVIEW["grading_mode"],
                user_id=OTHER_USER_ID,
                user_answer=DUMMY_REVIEW["user_answer"],
                ai_feedback=DUMMY_REVIEW["ai_feedback"],
                reviewed_at=DUMMY_TIME
            )

        self.assertIsInstance(review_id, int)

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    user_id,
                    card_id,
                    reviewed_at,
                    grading_mode,
                    score,
                    user_answer,
                    ai_feedback
                FROM review_history
                WHERE id = ?
            """, (review_id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (
                OTHER_USER_ID,
                self.card.id,
                DUMMY_TIME,
                DUMMY_REVIEW["grading_mode"],
                DUMMY_REVIEW["score"],
                DUMMY_REVIEW["user_answer"],
                DUMMY_REVIEW["ai_feedback"]
            )
        )

    def test_record_review_history_accepts_failed_ai_score(self):
        with db_lib.get_db() as conn:
            review_id = db_lib.record_review_history(
                conn.cursor(),
                card_id=self.card.id,
                score=db_lib.FAILED_AI_SCORE,
                grading_mode="ai",
                user_id=OTHER_USER_ID,
                reviewed_at=DUMMY_TIME
            )

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT score, grading_mode
                FROM review_history
                WHERE id = ?
            """, (review_id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (db_lib.FAILED_AI_SCORE, "ai")
        )

    def test_record_review_history_rejects_invalid_inputs(self):
        invalid_inputs = (
            (0, "manual", ValueError),
            (6, "manual", ValueError),
            ("5", "manual", TypeError),
            (db_lib.FAILED_AI_SCORE, "manual", ValueError),
            (5, "automatic", ValueError)
        )

        with db_lib.get_db() as conn:
            cur = conn.cursor()

            for score, grading_mode, expected_error in invalid_inputs:
                with self.subTest(
                    score=score,
                    grading_mode=grading_mode
                ):
                    with self.assertRaises(expected_error):
                        db_lib.record_review_history(
                            cur,
                            card_id=self.card.id,
                            score=score,
                            grading_mode=grading_mode,
                            user_id=OTHER_USER_ID,
                            reviewed_at=DUMMY_TIME
                        )

            history_count = conn.execute(
                "SELECT COUNT(*) FROM review_history"
            ).fetchone()[0]

        self.assertEqual(history_count, 0)

class TestRecordUserCardState(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

        self.card = make_dummy_card()
        db_lib.add_card(self.card)

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_record_user_card_state_creates_initial_state(self):
        with patch.object(
            db_lib,
            "calc_next_review_info",
            return_value={
                "current_interval": 4,
                "next_review_time": NEXT_REVIEW_TIME
            }
        ):
            with db_lib.get_db() as conn:
                db_lib.record_user_card_state(
                    conn.cursor(),
                    card_id=self.card.id,
                    score=DUMMY_REVIEW["score"],
                    user_id=OTHER_USER_ID,
                    reviewed_at=DUMMY_TIME
                )

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    next_review_time,
                    last_reviewed_at,
                    last_performance,
                    current_interval,
                    repetitions,
                    recent_scores_json
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                OTHER_USER_ID,
                self.card.id
            )).fetchone()

        self.assertEqual(
            (
                row["next_review_time"],
                row["last_reviewed_at"],
                row["last_performance"],
                row["current_interval"],
                row["repetitions"],
                json.loads(row["recent_scores_json"])
            ),
            (
                NEXT_REVIEW_TIME,
                DUMMY_TIME,
                DUMMY_REVIEW["score"],
                4,
                1,
                [DUMMY_REVIEW["score"]]
            )
        )

    def test_record_user_card_state_updates_scheduling_state(self):
        previous_review_time = "2025-12-01T00:00:00+00:00"

        with db_lib.get_db() as conn:
            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time,
                    last_reviewed_at,
                    current_interval,
                    repetitions,
                    recent_scores_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                OTHER_USER_ID,
                self.card.id,
                DUMMY_TIME,
                previous_review_time,
                7,
                2,
                json.dumps([3, 4])
            ))

        with patch.object(
            db_lib,
            "calc_next_review_info",
            return_value={
                "current_interval": 14,
                "next_review_time": NEXT_REVIEW_TIME
            }
        ):
            with db_lib.get_db() as conn:
                db_lib.record_user_card_state(
                    conn.cursor(),
                    card_id=self.card.id,
                    score=DUMMY_REVIEW["score"],
                    user_id=OTHER_USER_ID,
                    reviewed_at=DUMMY_TIME
                )

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    next_review_time,
                    last_reviewed_at,
                    last_performance,
                    current_interval,
                    repetitions,
                    recent_scores_json
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                OTHER_USER_ID,
                self.card.id
            )).fetchone()

        self.assertEqual(
            (
                row["next_review_time"],
                row["last_reviewed_at"],
                row["last_performance"],
                row["current_interval"],
                row["repetitions"],
                json.loads(row["recent_scores_json"])
            ),
            (
                NEXT_REVIEW_TIME,
                DUMMY_TIME,
                DUMMY_REVIEW["score"],
                14,
                3,
                [3, 4, DUMMY_REVIEW["score"]]
            )
        )

    def test_record_user_card_state_limits_recent_scores(self):
        existing_scores = [
            (index % 5) + 1
            for index in range(db_lib.MAX_PERFORMANCE_HISTORY)
        ]

        with db_lib.get_db() as conn:
            conn.execute("""
                INSERT INTO user_card_state (
                    user_id,
                    card_id,
                    next_review_time,
                    recent_scores_json
                )
                VALUES (?, ?, ?, ?)
            """, (
                OTHER_USER_ID,
                self.card.id,
                DUMMY_TIME,
                json.dumps(existing_scores)
            ))

        new_score = 5

        with patch.object(
            db_lib,
            "calc_next_review_info",
            return_value={
                "current_interval": 4,
                "next_review_time": NEXT_REVIEW_TIME
            }
        ):
            with db_lib.get_db() as conn:
                db_lib.record_user_card_state(
                    conn.cursor(),
                    card_id=self.card.id,
                    score=new_score,
                    user_id=OTHER_USER_ID,
                    reviewed_at=DUMMY_TIME
                )

        with db_lib.get_db() as conn:
            stored_scores = json.loads(conn.execute("""
                SELECT recent_scores_json
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                OTHER_USER_ID,
                self.card.id
            )).fetchone()[0])

        self.assertEqual(
            stored_scores,
            (existing_scores + [new_score])[
                -db_lib.MAX_PERFORMANCE_HISTORY:
            ]
        )

    def test_record_user_card_state_rejects_invalid_score(self):
        for score in (0, 6, db_lib.FAILED_AI_SCORE):
            with self.subTest(score=score):
                with db_lib.get_db() as conn:
                    with self.assertRaises(ValueError):
                        db_lib.record_user_card_state(
                            conn.cursor(),
                            card_id=self.card.id,
                            score=score,
                            user_id=OTHER_USER_ID,
                            reviewed_at=DUMMY_TIME
                        )

        with db_lib.get_db() as conn:
            state = conn.execute("""
                SELECT *
                FROM user_card_state
                WHERE user_id = ? AND card_id = ?
            """, (
                OTHER_USER_ID,
                self.card.id
            )).fetchone()

        self.assertIsNone(state)

class TestRecordLlmCall(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_record_llm_call_stores_supplied_fields(self):
        call_data = {
            "user_id": OTHER_USER_ID,
            "session_id": "test-session",
            "purpose": DUMMY_LLM["purpose"],
            "provider": DUMMY_LLM["provider"],
            "model": DUMMY_LLM["model"],
            "provider_request_id": "test-request-id",
            "request_json": DUMMY_LLM["request_json"],
            "response_text": DUMMY_LLM["response_text"],
            "input_tokens": DUMMY_LLM["input_tokens"],
            "output_tokens": DUMMY_LLM["output_tokens"],
            "estimated_cost_usd": 0.001,
            "status": DUMMY_LLM["status"],
            "error_message": "Test error message",
            "latency_ms": 250
        }

        llm_call_id = db_lib.record_llm_call(**call_data)

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
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
                WHERE id = ?
            """, (llm_call_id,)).fetchone()

        self.assertIsInstance(llm_call_id, int)
        self.assertEqual(
            tuple(row[:-1]),
            tuple(call_data.values())
        )
        self.assertIsNotNone(row["created_at"])

    def test_record_llm_call_stores_omitted_optional_fields_as_null(self):
        llm_call_id = db_lib.record_llm_call(
            purpose=DUMMY_LLM["purpose"],
            provider=DUMMY_LLM["provider"],
            model=DUMMY_LLM["model"],
            request_json=DUMMY_LLM["request_json"],
            status=DUMMY_LLM["status"]
        )

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    user_id,
                    session_id,
                    provider_request_id,
                    response_text,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    error_message,
                    latency_ms
                FROM llm_calls
                WHERE id = ?
            """, (llm_call_id,)).fetchone()

        self.assertEqual(row["user_id"], db_lib.DEFAULT_USER_ID)
        self.assertEqual(tuple(row[1:]), (None,) * 8)

    def test_record_llm_call_rejects_invalid_inputs(self):
        invalid_inputs = (
            (DUMMY_LLM["purpose"], "pending"),
            ("", DUMMY_LLM["status"]),
            ("   ", DUMMY_LLM["status"])
        )

        for purpose, status in invalid_inputs:
            with self.subTest(purpose=purpose, status=status):
                with self.assertRaises(ValueError):
                    db_lib.record_llm_call(
                        purpose=purpose,
                        provider=DUMMY_LLM["provider"],
                        model=DUMMY_LLM["model"],
                        request_json=DUMMY_LLM["request_json"],
                        status=status
                    )

        with db_lib.get_db() as conn:
            call_count = conn.execute(
                "SELECT COUNT(*) FROM llm_calls"
            ).fetchone()[0]

        self.assertEqual(call_count, 0)

class TestLinkLlmCallToReview(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

        self.card = make_dummy_card()
        db_lib.add_card(self.card)

        with db_lib.get_db() as conn:
            cur = conn.cursor()
            self.first_review_id = db_lib.record_review_history(
                cur,
                card_id=self.card.id,
                score=DUMMY_REVIEW["score"],
                grading_mode=DUMMY_REVIEW["grading_mode"],
                user_id=OTHER_USER_ID,
                reviewed_at=DUMMY_TIME
            )
            self.second_review_id = db_lib.record_review_history(
                cur,
                card_id=self.card.id,
                score=DUMMY_REVIEW["score"],
                grading_mode=DUMMY_REVIEW["grading_mode"],
                user_id=OTHER_USER_ID,
                reviewed_at=NEXT_REVIEW_TIME
            )

        self.llm_call_id = db_lib.record_llm_call(
            user_id=OTHER_USER_ID,
            **DUMMY_LLM
        )

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_link_llm_call_to_review_creates_relationship(self):
        db_lib.link_llm_call_to_review(
            self.first_review_id,
            self.llm_call_id
        )

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT review_id, llm_call_id
                FROM review_llm_calls
                WHERE llm_call_id = ?
            """, (self.llm_call_id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (self.first_review_id, self.llm_call_id)
        )

    def test_link_llm_call_to_review_propagates_integrity_errors(self):
        invalid_links = (
            (self.first_review_id, 999999),
            (999999, self.llm_call_id)
        )

        for review_id, llm_call_id in invalid_links:
            with self.subTest(
                review_id=review_id,
                llm_call_id=llm_call_id
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    db_lib.link_llm_call_to_review(
                        review_id,
                        llm_call_id
                    )

        db_lib.link_llm_call_to_review(
            self.first_review_id,
            self.llm_call_id
        )

        with self.assertRaises(sqlite3.IntegrityError):
            db_lib.link_llm_call_to_review(
                self.second_review_id,
                self.llm_call_id
            )

        with db_lib.get_db() as conn:
            rows = conn.execute("""
                SELECT review_id, llm_call_id
                FROM review_llm_calls
            """).fetchall()

        self.assertEqual(
            [tuple(row) for row in rows],
            [(self.first_review_id, self.llm_call_id)]
        )

class TestDeprecateCard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()

        self.card = make_dummy_card()
        db_lib.add_card(self.card)

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_deprecate_card_updates_card_and_records_deprecation(self):
        with patch.object(
            db_lib,
            "utc_now_iso",
            return_value=DUMMY_TIME
        ):
            db_lib.deprecate_card(self.card.id)

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    cards.is_deprecated,
                    cards.updated_at,
                    card_deprecations.card_id,
                    card_deprecations.deprecated_at
                FROM cards
                JOIN card_deprecations
                    ON card_deprecations.card_id = cards.id
                WHERE cards.id = ?
            """, (self.card.id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (
                1,
                DUMMY_TIME,
                self.card.id,
                DUMMY_TIME
            )
        )

    def test_deprecate_card_rejects_missing_or_already_deprecated_card(self):
        with self.assertRaises(ValueError):
            db_lib.deprecate_card(999999)

        with patch.object(
            db_lib,
            "utc_now_iso",
            return_value=DUMMY_TIME
        ):
            db_lib.deprecate_card(self.card.id)

        with patch.object(
            db_lib,
            "utc_now_iso",
            return_value=NEXT_REVIEW_TIME
        ):
            with self.assertRaises(ValueError):
                db_lib.deprecate_card(self.card.id)

        with db_lib.get_db() as conn:
            card_row = conn.execute("""
                SELECT updated_at
                FROM cards
                WHERE id = ?
            """, (self.card.id,)).fetchone()

            deprecation_rows = conn.execute("""
                SELECT deprecated_at
                FROM card_deprecations
                WHERE card_id = ?
            """, (self.card.id,)).fetchall()

        self.assertEqual(card_row["updated_at"], DUMMY_TIME)
        self.assertEqual(
            [row["deprecated_at"] for row in deprecation_rows],
            [DUMMY_TIME]
        )

    def test_deprecate_card_rejects_invalid_card_id(self):
        for card_id in (0, -1, "1", None):
            with self.subTest(card_id=card_id):
                with self.assertRaises(ValueError):
                    db_lib.deprecate_card(card_id)

        with db_lib.get_db() as conn:
            is_deprecated = conn.execute("""
                SELECT is_deprecated
                FROM cards
                WHERE id = ?
            """, (self.card.id,)).fetchone()[0]

            deprecation_count = conn.execute(
                "SELECT COUNT(*) FROM card_deprecations"
            ).fetchone()[0]

        self.assertEqual(is_deprecated, 0)
        self.assertEqual(deprecation_count, 0)

class TestAddDeck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_add_deck_saves_deck_and_returns_same_object(self):
        deck = make_dummy_deck()

        result = db_lib.add_deck(deck)

        self.assertIs(result, deck)
        self.assertIsNotNone(deck.id)
        self.assertIsNotNone(deck.created_at)
        self.assertIsNotNone(deck.updated_at)

        with db_lib.get_db() as conn:
            row = conn.execute("""
                SELECT
                    owner_user_id,
                    name,
                    deck_type,
                    source_deck_id,
                    is_published,
                    created_at,
                    updated_at
                FROM decks
                WHERE id = ?
            """, (deck.id,)).fetchone()

        self.assertEqual(
            tuple(row),
            (
                OTHER_USER_ID,
                "Testing Deck",
                "personal",
                None,
                0,
                deck.created_at,
                deck.updated_at
            )
        )

    def test_add_deck_rejects_non_deck(self):
        with self.assertRaises(TypeError):
            db_lib.add_deck({"name": "Testing Deck"})

        with db_lib.get_db() as conn:
            deck_count = conn.execute(
                "SELECT COUNT(*) FROM decks"
            ).fetchone()[0]

        self.assertEqual(deck_count, 0)

    def test_add_deck_propagates_integrity_errors(self):
        first_deck = make_dummy_deck()
        duplicate_deck = make_dummy_deck()

        db_lib.add_deck(first_deck)

        with self.assertRaises(sqlite3.IntegrityError):
            db_lib.add_deck(duplicate_deck)

        missing_user_deck = make_dummy_deck(
            name="Missing User Deck",
            owner_user_id=999999
        )

        with self.assertRaises(sqlite3.IntegrityError):
            db_lib.add_deck(missing_user_deck)

        with db_lib.get_db() as conn:
            deck_count = conn.execute(
                "SELECT COUNT(*) FROM decks"
            ).fetchone()[0]

        self.assertEqual(deck_count, 1)

class TestGetDecks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(db_lib, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db_lib.init_db()
        create_test_user()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_get_decks_returns_all_decks_sorted(self):
        first_deck = db_lib.add_deck(
            make_dummy_deck(name="zebra", owner_user_id=db_lib.DEFAULT_USER_ID)
        )
        second_deck = db_lib.add_deck(
            make_dummy_deck(name="Algorithms", owner_user_id=OTHER_USER_ID)
        )
        third_deck = db_lib.add_deck(
            make_dummy_deck(name="python", owner_user_id=db_lib.DEFAULT_USER_ID)
        )

        results = db_lib.get_decks()

        self.assertTrue(
            all(isinstance(deck, Deck) for deck in results)
        )
        self.assertEqual(
            [deck.id for deck in results],
            [
                second_deck.id,
                third_deck.id,
                first_deck.id
            ]
        )

    def test_get_decks_filters_by_user(self):
        default_deck = Deck(
            name="Default Deck",
            owner_user_id=db_lib.DEFAULT_USER_ID
        )
        other_deck = Deck(
            name="Other Deck",
            owner_user_id=OTHER_USER_ID
        )

        db_lib.add_deck(default_deck)
        db_lib.add_deck(other_deck)

        results = db_lib.get_decks(
            user_id=OTHER_USER_ID
        )

        self.assertEqual(len(results), 1)

        result = results[0]

        self.assertEqual(
            (
                result.id,
                result.owner_user_id,
                result.name,
                result.deck_type,
                result.source_deck_id,
                result.is_published,
                result.created_at,
                result.updated_at
            ),
            (
                other_deck.id,
                OTHER_USER_ID,
                "Other Deck",
                "personal",
                None,
                False,
                other_deck.created_at,
                other_deck.updated_at
            )
        )

    def test_get_decks_returns_empty_list_when_no_decks_match(self):
        deck = Deck(
            name="Default Deck",
            owner_user_id=db_lib.DEFAULT_USER_ID
        )
        db_lib.add_deck(deck)

        results = db_lib.get_decks(
            user_id=OTHER_USER_ID
        )

        self.assertEqual(results, [])

if __name__ == "__main__":
    unittest.main()