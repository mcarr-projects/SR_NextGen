import json
from pathlib import Path

from db_lib import DEFAULT_USER_ID
from gemini_calls import call_gemini
from sr_models import Card

GRADING_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "SR_Private" / "Prompts" / "grading_prompt.txt"
MAX_FEEDBACK = 2000
CARD_DRAFT_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "SR_Private"
    / "Prompts"
    / "card_draft_prompt.txt"
)


def build_grading_payload(card: Card, user_answer: str) -> dict:
    if not isinstance(card, Card):
        raise TypeError("card must be a Card")

    return {
        "question": card.question,
        "suggested_answer": card.answer,
        "user_answer": user_answer,
        "grading_type": card.grading_type,
        "grading_criteria": card.grading_criteria,
        "llm_grading_info": card.llm_grading_info
    }


def build_grading_prompt(card: Card, user_answer: str, prompt_path: Path = GRADING_PROMPT_PATH) -> str:
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


def validate_grade_result(card: Card, result: dict) -> dict:
    if not isinstance(result, dict):
        raise TypeError("grader result must be a dictionary")

    score = result.get("score")
    feedback = result.get("feedback")

    if type(score) is not int or score not in (1, 2, 3, 4, 5):
        raise ValueError("Grader score must be an integer from 1 through 5")
    if card.grading_type == "binary" and score not in (1, 5):
        raise ValueError("Binary grader score must be either 1 or 5")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ValueError("Grader feedback must be a non-empty string")
    if len(feedback) > MAX_FEEDBACK:
        raise ValueError("Feedback exceeds maximum acceptable length")

    return {"score": score, "feedback": feedback.strip()}


def grade_answer(
    card: Card,
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



def build_card_draft_payload(question_input: str, question_count: int) -> dict:
    if not isinstance(question_input, str) or not question_input.strip():
        raise ValueError("question input must be a non-empty string")
    if type(question_count) is not int or question_count < 1:
        raise ValueError("question count must be a positive integer")

    return {
        "question_input": question_input.strip(),
        "question_count": question_count
    }


def build_card_draft_prompt(
    question_input: str,
    question_count: int,
    prompt_path: Path = CARD_DRAFT_PROMPT_PATH
) -> str:
    generic_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not generic_prompt:
        raise ValueError(f"card draft prompt is empty: {prompt_path}")

    payload = build_card_draft_payload(question_input, question_count)
    return (
        f"{generic_prompt}\n\n"
        f"CARD DRAFT PAYLOAD\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_card_draft_response(response_text: str) -> dict:
    if not isinstance(response_text, str):
        raise TypeError("card draft response must be a string")

    text = response_text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    result = json.loads(text)
    if not isinstance(result, dict):
        raise TypeError("card draft result must be a JSON object")

    return result


def validate_card_draft_result(question_count: int, result: dict) -> dict:
    if not isinstance(result, dict):
        raise TypeError("card draft result must be a dictionary")

    cards = result.get("cards")
    if not isinstance(cards, list):
        raise TypeError("card draft result must contain a cards list")
    if len(cards) != question_count:
        raise ValueError(
            f"card draft result must contain exactly {question_count} cards"
        )

    validated_cards = []

    for card in cards:
        if not isinstance(card, dict):
            raise TypeError("each proposed card must be a dictionary")

        question = card.get("question")
        answer = card.get("answer")
        grading_criteria = card.get("grading_criteria")
        tags = card.get("tags")
        grading_type = card.get("grading_type")

        if not isinstance(question, str) or not question.strip():
            raise ValueError("each proposed card must have a non-empty question")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("each proposed card must have a non-empty answer")
        if not isinstance(grading_criteria, str) or not grading_criteria.strip():
            raise ValueError(
                "each proposed card must have non-empty grading criteria"
            )
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise ValueError("each proposed card must have a list of valid tags")
        if grading_type not in ("scaled", "binary"):
            raise ValueError(
                "each proposed card must use scaled or binary grading"
            )

        cleaned_tags = []
        seen_tags = set()

        for tag in tags:
            cleaned_tag = tag.strip()
            tag_key = cleaned_tag.casefold()

            if tag_key not in seen_tags:
                cleaned_tags.append(cleaned_tag)
                seen_tags.add(tag_key)

        validated_cards.append({
            "question": question.strip(),
            "answer": answer.strip(),
            "grading_criteria": grading_criteria.strip(),
            "tags": cleaned_tags,
            "grading_type": grading_type
        })

    return {"cards": validated_cards}

def generate_card_drafts(
    question_input: str,
    question_count: int,
    user_id: int | None = DEFAULT_USER_ID,
    session_id: str | None = None,
    client=None,
    prompt_path: Path = CARD_DRAFT_PROMPT_PATH
) -> dict:
    prompt = build_card_draft_prompt(
        question_input,
        question_count,
        prompt_path
    )
    call_result = call_gemini(
        prompt=prompt,
        purpose="card_draft",
        user_id=user_id,
        session_id=session_id,
        client=client
    )

    if call_result["status"] == "failed":
        return _card_draft_failure_result(
            call_result["llm_call_id"],
            "AI-assisted card drafting failed."
        )

    try:
        result = parse_card_draft_response(call_result["response_text"])
        result = validate_card_draft_result(question_count, result)
    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return _card_draft_failure_result(
            call_result["llm_call_id"],
            "The AI returned invalid card draft data."
        )

    return {
        **result,
        "llm_call_id": call_result["llm_call_id"],
        "card_draft_completed": True
    }

def _card_draft_failure_result(llm_call_id: int, error: str) -> dict:
    return {
        "cards": [],
        "llm_call_id": llm_call_id,
        "card_draft_completed": False,
        "error": error
    }

