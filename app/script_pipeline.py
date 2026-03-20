from itertools import product
from pathlib import Path

from app.models import VideoVariant
from app.openai_client import get_openai_client
from app.utils import (
    clean_text,
    ensure_dir,
    estimate_speech_duration_sec,
    json_loads_safe,
    save_json,
    slugify,
    stable_hash,
    with_retry,
)


def call_text_model_json(prompt: str, model: str) -> dict:
    def _call():
        client = get_openai_client()
        response = client.responses.create(
            model=model,
            input=prompt
        )
        return json_loads_safe(response.output_text)

    return with_retry(_call)


def generate_hooks(topic: str, language: str, n: int, model: str) -> list[str]:
    if language == "hu":
        prompt = f"""
Adj vissza kizárólag JSON-t ebben a formában:
{{
  "hooks": ["...", "..."]
}}

Feladat:
Írj {n} különböző short videó hookot magyarul.

Téma: {topic}

Szabályok:
- maximum 10 szó
- erős első mondat
- különböző szögek
- legyen köztük kíváncsiság, meglepő állítás, figyelmeztetés
- természetes magyar
- ne legyen emoji
- ne legyen clickbait szagú
"""
    else:
        prompt = f"""
Return JSON only in this format:
{{
  "hooks": ["...", "..."]
}}

Task:
Write {n} different short-form video hooks.

Topic: {topic}

Rules:
- maximum 10 words
- strong first line
- different angles
- include curiosity, surprising claim, warning styles
- natural spoken English
- no emojis
"""
    data = call_text_model_json(prompt, model)
    hooks = [clean_text(h) for h in data.get("hooks", []) if clean_text(h)]
    return hooks[:n]


def generate_bodies(topic: str, language: str, n: int, model: str) -> list[dict]:
    if language == "hu":
        prompt = f"""
Adj vissza kizárólag JSON-t ebben a formában:
{{
  "variants": [
    {{
      "promise": "...",
      "points": ["...", "..."],
      "payoff": "..."
    }}
  ]
}}

Feladat:
Írj {n} különböző short videó törzset magyarul.

Téma: {topic}

Szabályok:
- promise: 1 rövid mondat
- points: pontosan 2 rövid mondat
- payoff: 1 rövid mondat
- legyen jól kimondható
- modern, természetes magyar
- rövid videóra optimalizált
- ne legyen túl sűrű
- ne legyen emoji
"""
    else:
        prompt = f"""
Return JSON only in this format:
{{
  "variants": [
    {{
      "promise": "...",
      "points": ["...", "..."],
      "payoff": "..."
    }}
  ]
}}

Task:
Write {n} short-form body variants.

Topic: {topic}

Rules:
- promise: 1 short line
- points: exactly 2 short lines
- payoff: 1 short line
- easy to narrate
- natural spoken English
- no emojis
"""
    data = call_text_model_json(prompt, model)
    variants = data.get("variants", []) or []
    cleaned = []
    for item in variants[:n]:
        promise = clean_text(item.get("promise", ""))
        points = [clean_text(p) for p in item.get("points", []) if clean_text(p)]
        payoff = clean_text(item.get("payoff", ""))
        if promise and len(points) >= 2 and payoff:
            cleaned.append({
                "promise": promise,
                "points": points[:2],
                "payoff": payoff
            })
    return cleaned


def generate_ctas(language: str, n: int, model: str) -> list[str]:
    if language == "hu":
        prompt = f"""
Adj vissza kizárólag JSON-t ebben a formában:
{{
  "ctas": ["...", "..."]
}}

Írj {n} rövid CTA-t short videó végére magyarul.

Szabályok:
- maximum 7 szó
- természetes legyen
- ne legyen erőltetett
- inkább kommentre, követésre vagy további részre ösztönözzön
- ne legyen emoji
"""
    else:
        prompt = f"""
Return JSON only in this format:
{{
  "ctas": ["...", "..."]
}}

Write {n} short CTAs for the end of a short video.

Rules:
- max 7 words
- natural
- not pushy
- encourage comment, follow, or part 2
- no emojis
"""
    data = call_text_model_json(prompt, model)
    ctas = [clean_text(c) for c in data.get("ctas", []) if clean_text(c)]
    return ctas[:n]


def polish_script(full_script: str, language: str, model: str) -> str:
    if language == "hu":
        prompt = f"""
Adj vissza kizárólag a javított szöveget.

Feladat:
Javítsd ki ezt a rövid videós magyar szkriptet.

Szabályok:
- javítsd a helyesírást, ragozást, természetességet
- ne írj teljesen új tartalmat
- maradjon tömör
- maradjon jól kimondható
- ne hosszabbítsd meg jelentősen

Szöveg:
{full_script}
"""
    else:
        prompt = f"""
Return only the corrected script.

Task:
Polish this short-form script.

Rules:
- fix grammar and awkward phrasing
- keep meaning
- keep it short and easy to narrate

Text:
{full_script}
"""

    def _call():
        client = get_openai_client()
        response = client.responses.create(
            model=model,
            input=prompt
        )
        return response.output_text.strip()

    return clean_text(with_retry(_call))


def generate_metadata(topic: str, script: str, language: str, model: str, title_max_chars: int, description_max_chars: int, hashtags_count: int) -> dict:
    if language == "hu":
        prompt = f"""
Adj vissza kizárólag JSON-t ebben a formában:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#...", "#..."]
}}

Feladat:
Készíts short videó metadata csomagot.

Téma: {topic}
Szkript:
{script}

Szabályok:
- title max {title_max_chars} karakter
- description max {description_max_chars} karakter
- pontosan {hashtags_count} hashtag
- rövid, természetes magyar
- ne legyen spam szagú
"""
    else:
        prompt = f"""
Return JSON only in this format:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#...", "#..."]
}}

Task:
Create metadata for a short-form video.

Topic: {topic}
Script:
{script}

Rules:
- title max {title_max_chars} chars
- description max {description_max_chars} chars
- exactly {hashtags_count} hashtags
- natural English
- not spammy
"""
    return call_text_model_json(prompt, model)


def score_script(script: str, hook: str, cta: str, config: dict) -> tuple[float, dict]:
    total_words = len(script.split())
    hook_words = len(hook.split())
    cta_words = len(cta.split())
    est_duration = estimate_speech_duration_sec(total_words, words_per_second=2.8)

    score = 0.0

    if hook_words <= 8:
        score += 2.0
    elif hook_words <= 10:
        score += 1.0

    if cta_words <= 6:
        score += 1.0

    if int(config["min_total_words"]) <= total_words <= int(config["max_total_words"]):
        score += 3.0

    if float(config["ideal_duration_min_sec"]) <= est_duration <= float(config["ideal_duration_max_sec"]):
        score += 3.0

    if "?" in hook:
        score += 0.5

    curiosity_words_hu = ["senki", "legtöbb", "ezért", "hiba", "titok", "valójában"]
    curiosity_words_en = ["nobody", "most", "why", "mistake", "secret", "actually"]
    pool = curiosity_words_hu if config["language"] == "hu" else curiosity_words_en
    lower_script = script.lower()

    curiosity_hits = sum(1 for w in pool if w in lower_script)
    score += min(curiosity_hits * 0.4, 2.0)

    details = {
        "total_words": total_words,
        "hook_words": hook_words,
        "cta_words": cta_words,
        "estimated_duration_sec": round(est_duration, 2),
        "curiosity_hits": curiosity_hits
    }
    return round(score, 2), details


def build_full_script(hook: str, promise: str, points: list[str], payoff: str, cta: str) -> str:
    parts = [hook, promise, *points, payoff, cta]
    return "\n".join([clean_text(p) for p in parts if clean_text(p)])


def generate_ranked_variants(topic: str, config: dict, output_dir: Path) -> list[VideoVariant]:
    ensure_dir(output_dir)

    model = config["text_model"]
    hooks = generate_hooks(topic, config["language"], int(config["hook_variants"]), model)
    bodies = generate_bodies(topic, config["language"], int(config["body_variants"]), model)
    ctas = generate_ctas(config["language"], int(config["cta_variants"]), model)

    raw_dir = output_dir / "_raw_generation"
    ensure_dir(raw_dir)
    save_json(raw_dir / "hooks.json", {"hooks": hooks})
    save_json(raw_dir / "bodies.json", {"bodies": bodies})
    save_json(raw_dir / "ctas.json", {"ctas": ctas})

    variants: list[VideoVariant] = []

    for hook, body_variant, cta in product(hooks, bodies, ctas):
        promise = body_variant["promise"]
        points = body_variant["points"]
        payoff = body_variant["payoff"]

        raw_script = build_full_script(hook, promise, points, payoff, cta)
        polished_script = polish_script(raw_script, config["language"], model)

        metadata = generate_metadata(
            topic=topic,
            script=polished_script,
            language=config["language"],
            model=model,
            title_max_chars=int(config["title_max_chars"]),
            description_max_chars=int(config["description_max_chars"]),
            hashtags_count=int(config["hashtags_count"])
        )

        title = clean_text(metadata.get("title", topic))
        description = clean_text(metadata.get("description", ""))
        hashtags = [h.strip() for h in metadata.get("hashtags", []) if h.strip()]

        score, details = score_script(polished_script, hook, cta, config)

        variant_seed = f"{topic}|{hook}|{promise}|{'|'.join(points)}|{payoff}|{cta}"
        variant_id = stable_hash(variant_seed, length=10)
        variant_dir = output_dir / f"variant_{variant_id}_{slugify(hook, 30)}"
        ensure_dir(variant_dir)

        (variant_dir / "hook.txt").write_text(hook, encoding="utf-8")
        (variant_dir / "promise.txt").write_text(promise, encoding="utf-8")
        (variant_dir / "points.txt").write_text("\n".join(points), encoding="utf-8")
        (variant_dir / "payoff.txt").write_text(payoff, encoding="utf-8")
        (variant_dir / "cta.txt").write_text(cta, encoding="utf-8")
        (variant_dir / "script.txt").write_text(polished_script, encoding="utf-8")
        save_json(variant_dir / "score.json", {"score": score, "details": details})
        save_json(variant_dir / "metadata.preview.json", {
            "title": title,
            "description": description,
            "hashtags": hashtags
        })

        variants.append(
            VideoVariant(
                topic=topic,
                hook=hook,
                promise=promise,
                points=points,
                payoff=payoff,
                cta=cta,
                full_script=polished_script,
                title=title,
                description=description,
                hashtags=hashtags,
                score=score,
                score_details=details,
                variant_id=variant_id,
                output_dir=variant_dir
            )
        )

    variants.sort(key=lambda x: x.score, reverse=True)
    save_json(output_dir / "ranking.json", {
        "variants": [
            {
                "variant_id": v.variant_id,
                "score": v.score,
                "hook": v.hook,
                "title": v.title,
                "details": v.score_details
            }
            for v in variants
        ]
    })
    return variants