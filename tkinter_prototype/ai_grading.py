import json
from pathlib import Path

from db_lib import DEFAULT_USER_ID
from gemini_calls import call_gemini

GRADING_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "SR_Private" / "Prompts" / "grading_prompt.txt"
MAX_FEEDBACK = 2000


def build_grading_payload(card: dict, user_answer: str) -> dict:
    required_fields = ("question", "answer", "grading_type")
    missing_fields = [field for field in required_fields if field not in card]
    if missing_fields:
        raise ValueError(f"card is missing required fields: {', '.join(missing_fields)}")

    return {
        "question": card["question"],
        "suggested_answer": card["answer"],
        "user_answer": user_answer,
        "grading_type": card["grading_type"],
        "grading_criteria": card.get("grading_criteria"),
        "llm_grading_info": card.get("llm_grading_info")
    }


def build_grading_prompt(card: dict, user_answer: str, prompt_path: Path = GRADING_PROMPT_PATH) -> str:
    generic_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not generic_prompt:
        raise ValueError(f"grading prompt is empty: {prompt_path}")

    payload = build_grading_payload(card, user_answer)
    return f"{generic_prompt}\n\nGRADING PAYLOAD\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def parse_grade_response(response_text: str) -> dict:
    text = response_text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    result = json.loads(text)
    if not isinstance(result, dict):
        raise TypeError("grader result must be a JSON object")
    return result


def validate_grade_result(card: dict, result: dict) -> dict:
    if not isinstance(result, dict):
        raise TypeError("grader result must be a dictionary")

    score = result.get("score")
    feedback = result.get("feedback")

    if type(score) is not int or score not in (1, 2, 3, 4, 5):
        raise ValueError("Grader score must be an integer from 1 through 5")
    if card["grading_type"] == "binary" and score not in (1, 5):
        raise ValueError("Binary grader score must be either 1 or 5")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("Grader feedback must be a non-empty string")
    if len(feedback) > MAX_FEEDBACK:
        raise ValueError("Feedback exceeds maximum acceptable length")

    return {"score": score, "feedback": feedback.strip()}


def grade_answer(
    card: dict,
    user_answer: str,
    user_id: int | None = DEFAULT_USER_ID,
    session_id: str | None = None,
    client=None,
    prompt_path: Path = GRADING_PROMPT_PATH
) -> dict:
    prompt = build_grading_prompt(card, user_answer, prompt_path)
    call_result = call_gemini(
        prompt=prompt,
        purpose="grading",
        user_id=user_id,
        session_id=session_id,
        client=client
    )

    if call_result["status"] == "failed":
        return _manual_grading_result(call_result["llm_call_id"])

    try:
        grade_result = validate_grade_result(card, parse_grade_response(call_result["response_text"]))
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return _manual_grading_result(call_result["llm_call_id"])

    return {**grade_result, "llm_call_id": call_result["llm_call_id"], "requires_manual_grading": False}


def _manual_grading_result(llm_call_id: int) -> dict:
    return {
        "score": -1,
        "feedback": "AI grading failed. This answer requires manual grading.",
        "llm_call_id": llm_call_id,
        "requires_manual_grading": True
    }