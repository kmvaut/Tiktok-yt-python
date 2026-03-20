from pathlib import Path

from app.openai_client import get_openai_client
from app.utils import autodetect_binary, run_cmd, save_json, with_retry


def generate_voice(script: str, output_file: Path, model: str, voice: str, instructions: str) -> None:
    def _call():
        client = get_openai_client()
        audio = client.audio.speech.create(
            model=model,
            voice=voice,
            input=script,
            instructions=instructions
        )
        with open(output_file, "wb") as f:
            f.write(audio.read())

    with_retry(_call)


def process_audio(
    ffmpeg_exe: str,
    input_file: Path,
    output_file: Path,
    speed: float,
    volume: float,
    trim_silence: bool
) -> None:
    af_parts = []

    # FONTOS:
    # most direkt NEM használunk silenceremove-ot,
    # mert ez vágta le 1 sec-re a videókat
    af_parts.append(f"atempo={speed}")
    af_parts.append(f"volume={volume}")

    af_filter = ",".join(af_parts)

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(input_file),
        "-filter:a", af_filter,
        "-vn",
        str(output_file)
    ]
    run_cmd(cmd)


def transcribe_to_verbose_json(
    audio_file: Path,
    output_json: Path,
    model: str
) -> None:
    def _call():
        client = get_openai_client()
        with open(audio_file, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model=model,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"]
            )

        if hasattr(transcript, "model_dump"):
            data = transcript.model_dump()
        else:
            data = transcript

        save_json(output_json, data)

    with_retry(_call)


def generate_audio_assets(variant, config: dict) -> dict:
    ffmpeg_exe = autodetect_binary("FFMPEG_EXE", "ffmpeg")

    voice_file = variant.output_dir / "voice_raw.mp3"
    audio_fast_file = variant.output_dir / "voice_processed.mp3"
    transcript_json_file = variant.output_dir / "transcript.json"

    tts_instructions = (
        config["tts_instructions_hu"]
        if config["language"] == "hu"
        else config["tts_instructions_en"]
    )

    generate_voice(
        script=variant.full_script,
        output_file=voice_file,
        model=config["tts_model"],
        voice=config["voice"],
        instructions=tts_instructions
    )

    process_audio(
        ffmpeg_exe=ffmpeg_exe,
        input_file=voice_file,
        output_file=audio_fast_file,
        speed=float(config["speech_speed"]),
        volume=float(config["speech_volume"]),
        trim_silence=bool(config["trim_silence"])
    )

    transcribe_to_verbose_json(
        audio_file=audio_fast_file,
        output_json=transcript_json_file,
        model=config["transcription_model"]
    )

    return {
        "voice_file": voice_file,
        "audio_fast_file": audio_fast_file,
        "transcript_json_file": transcript_json_file
    }