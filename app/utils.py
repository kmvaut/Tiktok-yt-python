import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-") or "video"


def stable_hash(text: str, length: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def clean_text(text: str) -> str:
    text = text.replace("*", "")
    text = re.sub(r"[🚀✨🌌🤯😱🔥😂🤣🎯💥📈📉✅❌]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def json_loads_safe(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def with_retry(fn: Callable[[], Any], retries: int = 3, base_sleep: float = 1.5) -> Any:
    last_error = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                sleep_for = base_sleep * (2 ** attempt)
                print(f"Retry {attempt + 1}/{retries - 1} | várakozás: {sleep_for:.1f}s | hiba: {e}")
                time.sleep(sleep_for)
    raise last_error


def autodetect_binary(env_name: str, fallback_name: str) -> str:
    env_value = os.getenv(env_name)
    if env_value and Path(env_value).exists():
        return env_value

    found = shutil.which(fallback_name)
    if found:
        return found

    raise FileNotFoundError(
        f"Nem található a bináris: {fallback_name}. "
        f"Add meg .env-ben: {env_name}=..."
    )


def run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def seconds_to_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass_text(text: str) -> str:
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    return text


def estimate_speech_duration_sec(word_count: int, words_per_second: float = 2.8) -> float:
    return max(1.0, word_count / words_per_second)


def random_choice_cycle(items: list[Any], count: int) -> list[Any]:
    if not items:
        return []
    if len(items) >= count:
        return random.sample(items, count)
    out = []
    while len(out) < count:
        shuffled = items[:]
        random.shuffle(shuffled)
        out.extend(shuffled)
    return out[:count]


def smart_split_sentences(script: str) -> list[str]:
    lines = [line.strip() for line in script.splitlines() if line.strip()]
    if lines:
        return lines
    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_words_for_captions(
    words: list[str],
    min_words: int = 3,
    max_words: int = 7
) -> list[list[str]]:
    chunks = []
    current = []

    short_connectors = {
        "a", "az", "és", "vagy", "de", "hogy", "is", "ha", "mert", "ami", "aki",
        "to", "the", "and", "or", "but", "if", "that", "is"
    }

    for idx, word in enumerate(words):
        current.append(word)

        ends_sentence = bool(re.search(r"[.!?]$", word))
        enough_words = len(current) >= min_words
        too_many = len(current) >= max_words

        next_word = words[idx + 1].lower() if idx + 1 < len(words) else ""
        bad_break = next_word in short_connectors

        if enough_words and ends_sentence:
            chunks.append(current)
            current = []
            continue

        if too_many and not bad_break:
            chunks.append(current)
            current = []

    if current:
        if len(current) <= 2 and chunks:
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    return chunks


def wrap_caption_text(text: str, max_chars: int = 13, max_lines: int = 2) -> str:
    words = text.split()
    if not words:
        return text

    lines = []
    current_line = ""

    for word in words:
        candidate = word if not current_line else f"{current_line} {word}"

        if len(candidate) <= max_chars:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    if len(lines) > max_lines:
        merged = []
        current = ""

        for line in lines:
            candidate = line if not current else f"{current} {line}"
            if len(candidate) <= max_chars * max_lines:
                current = candidate
            else:
                if current:
                    merged.append(current)
                current = line

        if current:
            merged.append(current)

        lines = merged

    # ha még mindig több mint 2 sor lenne, akkor vágjuk 2 kiegyensúlyozott sorra
    if len(lines) > max_lines:
        words = text.split()
        best_split = 1
        best_score = None

        for i in range(1, len(words)):
            line1 = " ".join(words[:i])
            line2 = " ".join(words[i:])

            len1 = len(line1)
            len2 = len(line2)

            overflow_penalty = max(0, len1 - max_chars) * 10 + max(0, len2 - max_chars) * 10
            balance_penalty = abs(len1 - len2)
            max_len_penalty = max(len1, len2)

            score = overflow_penalty + balance_penalty + max_len_penalty

            if best_score is None or score < best_score:
                best_score = score
                best_split = i

        lines = [
            " ".join(words[:best_split]),
            " ".join(words[best_split:])
        ]

    return r"\N".join(lines[:max_lines])


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")