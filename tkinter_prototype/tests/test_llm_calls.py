import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import llm_calls
from sr_models import Card


DUMMY_CARD = Card(
    question="What is 2 + 2?",
    answer="4",
    grading_type="binary",
    grading_criteria="Award full credit only when the answer is numerically equal to 4.",
    llm_grading_info="Equivalent numeric forms such as 4.0 are correct."
)


class TestAIGrading(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_path = Path(self.temp_dir.name) / "grading_prompt.txt"
        self.prompt_path.write_text("Return a JSON grade.", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_grading_prompt_contains_generic_prompt_and_payload(self):
        prompt = llm_calls.build_grading_prompt(DUMMY_CARD, "4.0", self.prompt_path)
        generic_prompt, payload_text = prompt.split("\n\nGRADING PAYLOAD\n", maxsplit=1)

        self.assertEqual(generic_prompt, "Return a JSON grade.")
        self.assertEqual(json.loads(payload_text), {
            "question": "What is 2 + 2?",
            "suggested_answer": "4",
            "user_answer": "4.0",
            "grading_type": "binary",
            "grading_criteria": DUMMY_CARD.grading_criteria,
            "llm_grading_info": DUMMY_CARD.llm_grading_info
        })

    @patch("llm_calls.call_gemini")
    def test_grade_answer_invokes_provider_and_returns_validated_grade(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": '```json\n{"score": 5, "feedback": " Correct. "}\n```',
            "llm_call_id": 17
        }

        result = llm_calls.grade_answer(
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
            prompt=llm_calls.build_grading_prompt(DUMMY_CARD, "4.0", self.prompt_path),
            purpose="grading",
            user_id=3,
            session_id="test-session",
            client=None
        )

    @patch("llm_calls.call_gemini")
    def test_grade_answer_uses_manual_fallback_when_provider_fails(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "failed",
            "response_text": None,
            "llm_call_id": 18
        }

        result = llm_calls.grade_answer(DUMMY_CARD, "4", prompt_path=self.prompt_path)

        self.assertEqual(result["score"], -1)
        self.assertEqual(result["llm_call_id"], 18)
        self.assertTrue(result["requires_manual_grading"])

    @patch("llm_calls.call_gemini")
    def test_grade_answer_uses_manual_fallback_for_invalid_grade(self, mock_call_gemini):
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": '{"score": 3, "feedback": "Partly correct."}',
            "llm_call_id": 19
        }

        result = llm_calls.grade_answer(DUMMY_CARD, "Almost 4", prompt_path=self.prompt_path)

        self.assertEqual(result["score"], -1)
        self.assertEqual(result["llm_call_id"], 19)
        self.assertTrue(result["requires_manual_grading"])

class TestCardDrafting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_path = Path(self.temp_dir.name) / "card_draft_prompt.txt"
        self.prompt_path.write_text(
            "Return proposed card drafts as JSON.",
            encoding="utf-8"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_card_draft_prompt_contains_generic_prompt_and_payload(self):
        prompt = llm_calls.build_card_draft_prompt(
            "Create questions about Python sorting.",
            2,
            self.prompt_path
        )
        generic_prompt, payload_text = prompt.split(
            "\n\nCARD DRAFT PAYLOAD\n",
            maxsplit=1
        )

        self.assertEqual(
            generic_prompt,
            "Return proposed card drafts as JSON."
        )
        self.assertEqual(json.loads(payload_text), {
            "question_input": "Create questions about Python sorting.",
            "question_count": 2
        })

    @patch("llm_calls.call_gemini")
    def test_generate_card_drafts_returns_validated_drafts(
        self,
        mock_call_gemini
    ):
        response = {
            "cards": [
                {
                    "question": "What does sorted() return?",
                    "answer": "A new sorted list.",
                    "grading_criteria": "State that it returns a new list.",
                    "tags": [" Python ", "Sorting", "python"],
                    "grading_type": "binary"
                },
                {
                    "question": "What does list.sort() return?",
                    "answer": "None.",
                    "grading_criteria": "State that the list is sorted in place.",
                    "tags": ["Python", "Lists"],
                    "grading_type": "scaled"
                }
            ]
        }
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": f"```json\n{json.dumps(response)}\n```",
            "llm_call_id": 20
        }

        result = llm_calls.generate_card_drafts(
            "Create questions about Python sorting.",
            2,
            user_id=3,
            session_id="test-session",
            prompt_path=self.prompt_path
        )

        self.assertEqual(result, {
            "cards": [
                {
                    "question": "What does sorted() return?",
                    "answer": "A new sorted list.",
                    "grading_criteria": "State that it returns a new list.",
                    "tags": ["Python", "Sorting"],
                    "grading_type": "binary"
                },
                {
                    "question": "What does list.sort() return?",
                    "answer": "None.",
                    "grading_criteria": "State that the list is sorted in place.",
                    "tags": ["Python", "Lists"],
                    "grading_type": "scaled"
                }
            ],
            "llm_call_id": 20,
            "card_draft_completed": True
        })
        mock_call_gemini.assert_called_once_with(
            prompt=llm_calls.build_card_draft_prompt(
                "Create questions about Python sorting.",
                2,
                self.prompt_path
            ),
            purpose="card_draft",
            user_id=3,
            session_id="test-session",
            client=None
        )

    @patch("llm_calls.call_gemini")
    def test_generate_card_drafts_returns_failure_when_provider_fails(
        self,
        mock_call_gemini
    ):
        mock_call_gemini.return_value = {
            "status": "failed",
            "response_text": None,
            "llm_call_id": 21
        }

        result = llm_calls.generate_card_drafts(
            "What is binary search?",
            1,
            prompt_path=self.prompt_path
        )

        self.assertEqual(result, {
            "cards": [],
            "llm_call_id": 21,
            "card_draft_completed": False,
            "error": "AI-assisted card drafting failed."
        })

    @patch("llm_calls.call_gemini")
    def test_generate_card_drafts_returns_failure_for_invalid_response(
        self,
        mock_call_gemini
    ):
        mock_call_gemini.return_value = {
            "status": "completed",
            "response_text": json.dumps({
                "cards": [
                    {
                        "question": "What is binary search?",
                        "answer": "A search algorithm.",
                        "grading_criteria": "Describe binary search.",
                        "tags": ["Algorithms"],
                        "grading_type": "binary"
                    }
                ]
            }),
            "llm_call_id": 22
        }

        result = llm_calls.generate_card_drafts(
            "Create two questions about binary search.",
            2,
            prompt_path=self.prompt_path
        )

        self.assertEqual(result, {
            "cards": [],
            "llm_call_id": 22,
            "card_draft_completed": False,
            "error": "The AI returned invalid card draft data."
        })

if __name__ == "__main__":
    unittest.main()