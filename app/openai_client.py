import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Hiányzik az OPENAI_API_KEY. "
            "Tedd a projekt gyökerében lévő .env fájlba."
        )
    return OpenAI(api_key=api_key)