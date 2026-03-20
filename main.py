from pathlib import Path
import json
import shutil

from app.config_loader import load_env_and_paths, load_config, load_video_jobs
from app.script_pipeline import generate_ranked_variants
from app.audio_pipeline import generate_audio_assets
from app.caption_pipeline import build_caption_assets
from app.render_pipeline import render_final_video
from app.metadata_pipeline import export_upload_metadata
from app.utils import ensure_dir, print_header


def cleanup_failed_variants(topic_output_dir: Path) -> None:
    """
    Törli azokat a variant_* mappákat, ahol nincs final.mp4
    """
    if not topic_output_dir.exists():
        return

    removed = 0

    for item in topic_output_dir.iterdir():
        if not item.is_dir():
            continue
        if not item.name.startswith("variant_"):
            continue

        final_video = item / "final.mp4"
        if not final_video.exists():
            shutil.rmtree(item, ignore_errors=True)
            removed += 1

    print(f"Törölt hibás / nem kész variáns mappák: {removed}")


def cleanup_extra_completed_variants(topic_output_dir: Path, keep_count: int = 3) -> None:
    """
    Meghagyja csak az első keep_count darab kész variánst a ranking.json alapján.
    A többi kész variant_* mappát törli.
    """
    ranking_file = topic_output_dir / "ranking.json"
    if not ranking_file.exists():
        return

    data = json.loads(ranking_file.read_text(encoding="utf-8"))
    ranked_ids = [item["variant_id"] for item in data.get("variants", [])]

    keep_variant_dirs = set()

    for variant_id in ranked_ids[:keep_count]:
        for item in topic_output_dir.iterdir():
            if item.is_dir() and item.name.startswith(f"variant_{variant_id}_"):
                if (item / "final.mp4").exists():
                    keep_variant_dirs.add(item.resolve())

    removed = 0

    for item in topic_output_dir.iterdir():
        if not item.is_dir():
            continue
        if not item.name.startswith("variant_"):
            continue
        if not (item / "final.mp4").exists():
            continue
        if item.resolve() not in keep_variant_dirs:
            shutil.rmtree(item, ignore_errors=True)
            removed += 1

    print(f"Törölt extra kész variáns mappák: {removed}")


def main() -> None:
    paths = load_env_and_paths()
    config = load_config(paths["config_file"])
    jobs = load_video_jobs(paths["jobs_file"], paths["assets_dir"])

    print_header("Shorts automation indul")

    print(f"Feladatok száma: {len(jobs)}")
    print(f"Nyelv: {config['language']}")
    print(f"Hang: {config['voice']}")
    print(f"Top renderelt variánsok: {config['top_variants_to_render']}")

    for index, job in enumerate(jobs, start=1):
        topic = job["topic"]
        background_videos = job["background_videos"]

        print_header(f"{index}. téma")
        print(f"Téma: {topic}")
        print(f"Háttérvideók: {[p.name for p in background_videos]}")

        topic_slug = job["topic_slug"]
        topic_output_dir = paths["output_dir"] / topic_slug
        ensure_dir(topic_output_dir)

        try:
            ranked_variants = generate_ranked_variants(
                topic=topic,
                config=config,
                output_dir=topic_output_dir
            )

            selected = ranked_variants[: int(config["top_variants_to_render"])]
            print(f"Kiválasztott variánsok: {len(selected)} / {len(ranked_variants)}")

            for rank_index, variant in enumerate(selected, start=1):
                print_header(f"Render variáns #{rank_index} | score={variant.score:.2f}")

                assets = generate_audio_assets(
                    variant=variant,
                    config=config
                )

                caption_assets = build_caption_assets(
                    variant=variant,
                    audio_fast_file=assets["audio_fast_file"],
                    transcript_json_file=assets["transcript_json_file"],
                    config=config
                )

                final_video = render_final_video(
                    variant=variant,
                    config=config,
                    background_videos=background_videos,
                    audio_fast_file=assets["audio_fast_file"],
                    ass_file=caption_assets["ass_file"]
                )

                export_upload_metadata(
                    variant=variant,
                    config=config,
                    final_video=final_video
                )

                print(f"Kész: {final_video}")

            # 1) minden sikertelen / nem kész variant mappa törlése
            cleanup_failed_variants(topic_output_dir)

            # 2) opcionális: csak a top renderelt kész variánsok maradjanak meg
            cleanup_extra_completed_variants(
                topic_output_dir,
                keep_count=int(config["top_variants_to_render"])
            )

        except Exception as e:
            print(f"Hiba ennél a témánál: {topic}")
            print(str(e))

            # Hiba esetén is takarítson
            cleanup_failed_variants(topic_output_dir)

    print_header("Minden kész")


if __name__ == "__main__":
    main()