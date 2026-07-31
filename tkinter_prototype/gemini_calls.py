import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from google import genai

from ai_grading import validate_grade_result
from db_lib import DEFAULT_USER_ID, record_llm_call

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_MODEL = "gemini-3.6-flash"
GRADING_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "SR_Private" / "Prompts" / "grading_prompt.txt"
PROVIDER = "google"


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


def build_grading_prompt(payload: dict, prompt_path: Path = GRADING_PROMPT_PATH) -> str:
    general_prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not general_prompt:
        raise ValueError(f"grading prompt is empty: {prompt_path}")

    return f"{general_prompt}\n\nGRADING PAYLOAD\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def parse_grade_response(response_text: str) -> dict:
    text = response_text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    result = json.loads(text)
    if not isinstance(result, dict):
        raise TypeError("Gemini grading response must be a JSON object")
    return result


def _usage_value(response, *names):
    usage = getattr(response, "usage", None) or getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    for name in names:
        value = getattr(usage, name, None)
        if value is not None:
            return value
    return None


def grade_answer(
    card: dict,
    user_answer: str,
    user_id: int | None = DEFAULT_USER_ID,
    session_id: str | None = None,
    client=None,
    prompt_path: Path = GRADING_PROMPT_PATH
) -> dict:
    payload = build_grading_payload(card, user_answer)
    request_json = json.dumps(payload, ensure_ascii=False)
    prompt = build_grading_prompt(payload, prompt_path)
    own_client = client is None
    client = client or genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    started_at = perf_counter()
    response = None

    try:
        response = client.interactions.create(model=GEMINI_MODEL, input=prompt, store=False)
        grade_result = validate_grade_result(card, parse_grade_response(response.output_text))
        latency_ms = round((perf_counter() - started_at) * 1000)
        llm_call_id = record_llm_call(
            purpose="grading",
            provider=PROVIDER,
            model=GEMINI_MODEL,
            request_json=request_json,
            status="completed",
            user_id=user_id,
            session_id=session_id,
            provider_request_id=getattr(response, "id", None),
            response_text=response.output_text,
            input_tokens=_usage_value(response, "total_input_tokens", "prompt_token_count"),
            output_tokens=_usage_value(response, "total_output_tokens", "candidates_token_count"),
            latency_ms=latency_ms
        )
        return {**grade_result, "llm_call_id": llm_call_id, "requires_manual_grading": False}
    except Exception as error:
        latency_ms = round((perf_counter() - started_at) * 1000)
        llm_call_id = record_llm_call(
            purpose="grading",
            provider=PROVIDER,
            model=GEMINI_MODEL,
            request_json=request_json,
            status="failed",
            user_id=user_id,
            session_id=session_id,
            provider_request_id=getattr(response, "id", None),
            response_text=getattr(response, "output_text", None),
            input_tokens=_usage_value(response, "total_input_tokens", "prompt_token_count"),
            output_tokens=_usage_value(response, "total_output_tokens", "candidates_token_count"),
            error_message=f"{type(error).__name__}: {error}",
            latency_ms=latency_ms
        )
        return {
            "score": -1,
            "feedback": "AI grading failed. This answer requires manual grading.",
            "llm_call_id": llm_call_id,
            "requires_manual_grading": True
        }
    finally:
        if own_client:
            client.close()


def GeminiTest():
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    try:
        response = client.interactions.create(
            model=GEMINI_MODEL,
            input="Reply with exactly: Gemini API connection successful."
        )
        print(response.output_text)
        return response.output_text
    finally:
        client.close()


if __name__ == "__main__":
    GeminiTest()