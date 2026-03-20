import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.utils import ensure_dir, slugify


def load_env_and_paths() -> dict:
    load_dotenv()

    base_dir = Path(__file__).resolve().parent.parent
    assets_dir = base_dir / "assets"
    output_dir = base_dir / "output"
    config_file = base_dir / "config.json"
    jobs_file = base_dir / "videos.txt"

    ensure_dir(assets_dir)
    ensure_dir(output_dir)

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Hiányzik az OPENAI_API_KEY a .env fájlból.")

    return {
        "base_dir": base_dir,
        "assets_dir": assets_dir,
        "output_dir": output_dir,
        "config_file": config_file,
        "jobs_file": jobs_file
    }


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Hiányzik a config fájl: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))

    required_keys = [
        "language",
        "voice",
        "text_model",
        "tts_model",
        "transcription_model",
        "tts_instructions_hu",
        "tts_instructions_en",
        "caption_max_chars",
        "intro_caption_max_chars",
        "caption_font_size",
        "caption_margin_v",
        "hook_font_size",
        "hook_margin_v",
        "cta_font_size",
        "cta_margin_v",
        "speech_speed",
        "speech_volume",
        "trim_silence",
        "visual_contrast",
        "visual_saturation",
        "visual_brightness",
        "intro_overlay_duration",
        "intro_overlay_alpha",
        "target_fps",
        "target_width",
        "target_height",
        "hook_variants",
        "body_variants",
        "cta_variants",
        "top_variants_to_render",
        "min_total_words",
        "max_total_words",
        "ideal_duration_min_sec",
        "ideal_duration_max_sec",
        "scene_change_every_sec",
        "max_scenes_per_video",
        "title_max_chars",
        "description_max_chars",
        "hashtags_count"
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"Hiányzik a config.json mező: {key}")

    if config["language"] not in ["hu", "en"]:
        raise ValueError("A language csak 'hu' vagy 'en' lehet.")

    return config


def load_video_jobs(file_path: Path, assets_dir: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Hiányzik a videos.txt fájl: {file_path}")

    jobs = []
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue

        if "|" not in line:
            raise ValueError(
                f"Hibás sor a videos.txt-ben ({line_number}. sor). "
                f"Formátum: tema|video1.mp4,video2.mp4"
            )

        topic, raw_videos = line.split("|", 1)
        topic = topic.strip()
        video_names = [v.strip() for v in raw_videos.split(",") if v.strip()]

        if not topic or not video_names:
            raise ValueError(
                f"Hibás sor a videos.txt-ben ({line_number}. sor). "
                f"Hiányzik a topic vagy a videólista."
            )

        background_videos = []
        for video_name in video_names:
            video_path = assets_dir / video_name
            if not video_path.exists():
                raise FileNotFoundError(f"Hiányzik a videó: {video_path}")
            background_videos.append(video_path)

        jobs.append({
            "topic": topic,
            "topic_slug": slugify(topic),
            "background_videos": background_videos
        })

    if not jobs:
        raise RuntimeError("A videos.txt üres.")

    return jobs