import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from google import genai

from db_lib import DEFAULT_USER_ID, record_llm_call

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_MODEL = "gemini-3.6-flash"
PROVIDER = "google"


def _usage_value(response, *names):
    usage = getattr(response, "usage", None) or getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    for name in names:
        value = getattr(usage, name, None)
        if value is not None:
            return value
    return None


def call_gemini(
    prompt: str,
    purpose: str,
    user_id: int | None = DEFAULT_USER_ID,
    session_id: str | None = None,
    client=None,
    model: str = GEMINI_MODEL
) -> dict:
    request_json = json.dumps({"input": prompt, "store": False}, ensure_ascii=False)
    own_client = client is None
    started_at = perf_counter()
    response = None

    try:
        client = client or genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        response = client.interactions.create(model=model, input=prompt, store=False)
        response_text = response.output_text
        llm_call_id = record_llm_call(
            purpose=purpose,
            provider=PROVIDER,
            model=model,
            request_json=request_json,
            status="completed",
            user_id=user_id,
            session_id=session_id,
            provider_request_id=getattr(response, "id", None),
            response_text=response_text,
            input_tokens=_usage_value(response, "total_input_tokens", "prompt_token_count"),
            output_tokens=_usage_value(response, "total_output_tokens", "candidates_token_count"),
            latency_ms=round((perf_counter() - started_at) * 1000)
        )
        return {"status": "completed", "response_text": response_text, "llm_call_id": llm_call_id}
    except Exception as error:
        llm_call_id = record_llm_call(
            purpose=purpose,
            provider=PROVIDER,
            model=model,
            request_json=request_json,
            status="failed",
            user_id=user_id,
            session_id=session_id,
            provider_request_id=getattr(response, "id", None),
            response_text=getattr(response, "output_text", None),
            input_tokens=_usage_value(response, "total_input_tokens", "prompt_token_count"),
            output_tokens=_usage_value(response, "total_output_tokens", "candidates_token_count"),
            error_message=f"{type(error).__name__}: {error}",
            latency_ms=round((perf_counter() - started_at) * 1000)
        )
        return {"status": "failed", "response_text": None, "llm_call_id": llm_call_id}
    finally:
        if own_client and client is not None:
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