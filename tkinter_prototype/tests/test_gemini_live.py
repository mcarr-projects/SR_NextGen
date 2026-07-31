import os
import unittest
from uuid import uuid4

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

        result = gemini_calls.grade_answer(DUMMY_CARD, "4.0", session_id=session_id)

        self.assertFalse(result["requires_manual_grading"], result["feedback"])
        self.assertEqual(result["score"], 5)
        self.assertIsInstance(result["llm_call_id"], int)

        with db_lib.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM llm_calls WHERE id = ? AND session_id = ?",
                (result["llm_call_id"], session_id)
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["purpose"], "grading")
        self.assertEqual(row["provider"], gemini_calls.PROVIDER)
        self.assertEqual(row["model"], gemini_calls.GEMINI_MODEL)
        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["provider_request_id"])
        self.assertIsNotNone(row["response_text"])
        self.assertIsNotNone(row["input_tokens"])
        self.assertGreater(row["input_tokens"], 0)
        self.assertIsNotNone(row["output_tokens"])
        self.assertGreater(row["output_tokens"], 0)
        
if __name__ == "__main__":
    unittest.main()