import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_grading


DUMMY_CARD = {
    "question": "What is 2 + 2?",
    "answer": "4",
    "grading_type": "binary",
    "grading_criteria": "Award full credit only when the answer is numerically equal to 4.",
    "llm_grading_info": "Equivalent numeric forms such as 4.0 are correct."
}


class TestAIGrading(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_path = Path(self.temp_dir.name) / "grading_prompt.txt"
        self.prompt_path.write_text("Return a JSON grade.", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_grading_prompt_contains_generic_prompt_and_payload(self):
        prompt = ai_grading.build_grading_prompt(DUMMY_CARD, "4.0", self.prompt_path)
        generic_prompt, payload_text = prompt.split("\n\nGRADING PAYLOAD\n", maxsplit=1)

        self.assertEqual(generic_prompt, "Return a JSON grade.")
        self.assertEqual(json.loads(payload_text), {
            "question": "What is 2 + 2?",
            "suggested_answer": "4",
            "user_answer": "4.0",
            "grading_type": "binary",
            "grading_criteria": DUMMY_CARD["grading_criteria"],
            "llm_grading_info": DUMMY_CARD["llm_grading_info"]
        })

    @patch("ai_grading.call_gemini")
    def test_grade_answer_invokes_provider_and_returns_validated_grade(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": '```json\n{"score": 5, "feedback": " Correct. "}\n```',
            "llm_call_id": 17
        }

        result = ai_grading.grade_answer(
            DUMMY_CARD,
            "4.0",
            user_id=3,
            session_id="test-session",
            prompt_path=self.prompt_path
        )

        self.assertEqual(result, {
            "score": 5,
            "feedback": "Correct.",
            "llm_call_id": 17,
            "requires_manual_grading": False
        })
        mock_call_gemini.assert_called_once_with(
            prompt=ai_grading.build_grading_prompt(DUMMY_CARD, "4.0", self.prompt_path),
            purpose="grading",
            user_id=3,
            session_id="test-session",
            client=None
        )

    @patch("ai_grading.call_gemini")
    def test_grade_answer_uses_manual_fallback_when_provider_fails(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "failed",
            "response_text": None,
            "llm_call_id": 18
        }

        result = ai_grading.grade_answer(DUMMY_CARD, "4", prompt_path=self.prompt_path)

        self.assertEqual(result["score"], -1)
        self.assertEqual(result["llm_call_id"], 18)
        self.assertTrue(result["requires_manual_grading"])

    @patch("ai_grading.call_gemini")
    def test_grade_answer_uses_manual_fallback_for_invalid_grade(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": '{"score": 3, "feedback": "Partly correct."}',
            "llm_call_id": 19
        }

        result = ai_grading.grade_answer(DUMMY_CARD, "Almost 4", prompt_path=self.prompt_path)

        self.assertEqual(result["score"], -1)
        self.assertEqual(result["llm_call_id"], 19)
        self.assertTrue(result["requires_manual_grading"])


if __name__ == "__main__":
    unittest.main()
