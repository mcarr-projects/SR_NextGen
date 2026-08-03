import json
import os
import unittest
from uuid import uuid4

import ai_grading
import db_lib
import gemini_calls


LIVE_TESTS_ENABLED = os.getenv("RUN_LIVE_GEMINI_TESTS") == "1"
DUMMY_CARD = {
    "question": "What is 2 + 2?",
    "answer": "4",
    "grading_type": "binary",
    "grading_criteria": "Award full credit only when the answer is numerically equal to 4.",
    "llm_grading_info": "Equivalent numeric forms such as 4.0 are correct."
}


@unittest.skipUnless(LIVE_TESTS_ENABLED, "set RUN_LIVE_GEMINI_TESTS=1 to make a real Gemini API call")
class TestGeminiLive(unittest.TestCase):
    def test_live_grading_call_is_recorded_in_real_database(self):
        self.assertTrue(os.getenv("GOOGLE_API_KEY"), "GOOGLE_API_KEY is missing from the environment or .env")
        session_id = f"live-test-{uuid4()}"

        result = ai_grading.grade_answer(DUMMY_CARD, "4.0", session_id=session_id)

        self.assertFalse(result["requires_manual_grading"], result["feedback"])
        self.assertEqual(result["score"], 5)
        self.assertIsInstance(result["llm_call_id"], int)

        with db_lib.get_db() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, session_id, purpose, provider, model,
                       provider_request_id, request_json, response_text,
                       input_tokens, output_tokens, status, error_message,
                       latency_ms
                FROM llm_calls
                WHERE id = ? AND session_id = ?
                """,
                (result["llm_call_id"], session_id)
            ).fetchone()

        self.assertIsNotNone(row, "Gemini call was not recorded in llm_calls")
        self.assertEqual(row["id"], result["llm_call_id"])
        self.assertEqual(row["user_id"], db_lib.DEFAULT_USER_ID)
        self.assertEqual(row["session_id"], session_id)
        self.assertEqual(row["purpose"], "grading")
        self.assertEqual(row["provider"], gemini_calls.PROVIDER)
        self.assertEqual(row["model"], gemini_calls.GEMINI_MODEL)
        self.assertEqual(row["status"], "completed")
        self.assertIsNone(row["error_message"])
        self.assertIsNotNone(row["provider_request_id"])
        self.assertTrue(row["response_text"])
        self.assertIsNotNone(row["input_tokens"])
        self.assertGreater(row["input_tokens"], 0)
        self.assertIsNotNone(row["output_tokens"])
        self.assertGreater(row["output_tokens"], 0)
        self.assertIsNotNone(row["latency_ms"])
        self.assertGreaterEqual(row["latency_ms"], 0)

        recorded_request = json.loads(row["request_json"])
        self.assertFalse(recorded_request["store"])
        self.assertIn("GRADING PAYLOAD", recorded_request["input"])
        self.assertIn(DUMMY_CARD["question"], recorded_request["input"])
        self.assertIn('"user_answer": "4.0"', recorded_request["input"])


if __name__ == "__main__":
    unittest.main()