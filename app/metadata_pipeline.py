from pathlib import Path

from app.utils import save_json


def export_upload_metadata(variant, config: dict, final_video: Path) -> None:
    hashtags_line = " ".join(variant.hashtags)

    upload_json = {
        "topic": variant.topic,
        "variant_id": variant.variant_id,
        "language": config["language"],
        "title": variant.title,
        "description": variant.description,
        "hashtags": variant.hashtags,
        "hashtags_line": hashtags_line,
        "video_file": str(final_video.resolve()),
        "hook": variant.hook,
        "script": variant.full_script,
        "score": variant.score,
        "score_details": variant.score_details
    }

    save_json(variant.output_dir / "upload.json", upload_json)
    (variant.output_dir / "title.txt").write_text(variant.title, encoding="utf-8")
    (variant.output_dir / "description.txt").write_text(variant.description, encoding="utf-8")
    (variant.output_dir / "hashtags.txt").write_text(hashtags_line, encoding="utf-8")