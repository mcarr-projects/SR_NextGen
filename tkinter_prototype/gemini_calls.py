import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_MODEL = "gemini-3.6-flash"


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