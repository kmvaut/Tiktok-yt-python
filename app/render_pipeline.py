from pathlib import Path

from app.utils import autodetect_binary, run_cmd, save_json


def render_final_video(variant, config: dict, background_videos: list[Path], audio_fast_file: Path, ass_file: Path) -> Path:
    ffmpeg_exe = autodetect_binary("FFMPEG_EXE", "ffmpeg")

    if not background_videos:
        raise RuntimeError("Nincs háttérvideó megadva.")

    background_video = background_videos[0]

    ass_path = str(ass_file.resolve()).replace("\\", "/").replace(":", "\\:")

    width = int(config["target_width"])
    height = int(config["target_height"])
    fps = int(config["target_fps"])

    contrast = float(config["visual_contrast"])
    saturation = float(config["visual_saturation"])
    brightness = float(config["visual_brightness"])

    intro_overlay_duration = float(config["intro_overlay_duration"])
    intro_overlay_alpha = float(config["intro_overlay_alpha"])

    # ugyanaz az egyszerűbb és stabilabb megközelítés, mint az eredeti scriptedben
    vf_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"eq=contrast={contrast}:saturation={saturation}:brightness={brightness},"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{intro_overlay_alpha}:t=fill:enable='between(t,0,{intro_overlay_duration})',"
        f"zoompan=z='min(zoom+0.0008,1.08)':d=1:s={width}x{height}:fps={fps},"
        f"ass='{ass_path}'"
    )

    final_video = variant.output_dir / "final.mp4"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-stream_loop", "-1",
        "-i", str(background_video),
        "-i", str(audio_fast_file),
        "-vf", vf_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(final_video)
    ]
    run_cmd(cmd)

    save_json(variant.output_dir / "render_info.json", {
        "background_source": background_video.name,
        "audio_file": str(audio_fast_file),
        "ass_file": str(ass_file),
        "final_video": str(final_video)
    })

    return final_video