import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from openai import OpenAI

from db_lib import DEFAULT_USER_ID, record_llm_call

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OAI_MODEL = "gpt-6-luna"
PROVIDER = "oai"
REASONING_EFFORT = "low"

def _usage_value(response, name):
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return getattr(usage,name,None)

def call_oai(
        prompt: str,
        purpose: str,
        user_id: int | None = DEFAULT_USER_ID,
        session_id: str | None = None,
        client=None,
        model: str = OAI_MODEL
) -> dict:
    request = {
        "input": prompt,
        "store": False,
        "reasoning": {"effort": REASONING_EFFORT}
    }
    request_json = json.dumps(request, ensure_ascii=False)
    own_client = client is None
    started_at = perf_counter()
    response = None

    try:
        client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.responses.create(model=model, **request)
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
            input_tokens=_usage_value(response, "input_tokens"),
            output_tokens=_usage_value(response, "output_tokens"),
            latency_ms=round((perf_counter() - started_at) * 1000)
        )
        return {
            "status": "completed",
            "response_text": response_text,
            "llm_call_id": llm_call_id
        }

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
            input_tokens=_usage_value(response, "input_tokens"),
            output_tokens=_usage_value(response, "output_tokens"),
            error_message=f"{type(error).__name__}: {error}",
            latency_ms=round((perf_counter() - started_at) * 1000)
        )
        return {
            "status": "failed",
            "response_text": None,
            "llm_call_id": llm_call_id
        }

    finally:
        if own_client and client is not None:
            client.close()