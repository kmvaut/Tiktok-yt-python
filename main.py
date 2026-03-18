import json
import os
import re
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- Clients ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Paths ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Config ---
FFMPEG_EXE = r"C:\Users\Katai\Desktop\fejlesztes\ffmpeg-2026-03-12-git-9dc44b43b2-essentials_build\bin\ffmpeg.exe"


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Hiányzik a config fájl: {config_path}")

    config = json.loads(config_path.read_text(encoding="utf-8"))

    required_keys = [
        "language",
        "voice",
        "tts_instructions_hu",
        "tts_instructions_en",
        "caption_max_chars",
        "caption_font_size",
        "caption_margin_v",
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"Hiányzik a config.json-ból ez a mező: {key}")

    if config["language"] not in ["hu", "en"]:
        raise ValueError("A config.json 'language' mezője csak 'hu' vagy 'en' lehet.")

    return config


def load_video_jobs(file_path: Path) -> list[dict]:
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
                f"A formátum legyen: topic|video.mp4"
            )

        topic, video_name = line.split("|", 1)
        topic = topic.strip()
        video_name = video_name.strip()

        if not topic or not video_name:
            raise ValueError(
                f"Hibás sor a videos.txt-ben ({line_number}. sor). "
                f"Hiányzik a topic vagy a videófájlnév."
            )

        jobs.append({
            "topic": topic,
            "video_name": video_name
        })

    return jobs


def generate_script(topic: str, language: str) -> str:
    if language == "hu":
        prompt = f"""
Írj rövid, természetes magyar TikTok / YouTube Shorts szkriptet.

Téma: {topic}

Szabályok:
- maximum 50 szó
- rövid, teljes magyar mondatok
- természetes magyar nyelv
- helyes ragozás
- könnyen kimondható mondatok
- ne használj furcsa vagy túl angolos fordulatokat
- az első mondat legyen figyelemfelkeltő
- a végén legyen rövid CTA
- ne használj markdownot
- ne használj emojikat

Stílus:
- természetes
- tiszta
- közvetlen
- rövid videós
"""
    else:
        prompt = f"""
Write a short, natural TikTok / YouTube Shorts script.

Topic: {topic}

Rules:
- maximum 50 words
- short spoken lines
- natural conversational English
- strong hook in the first line
- short CTA at the end
- no markdown
- no emojis
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return response.output_text.strip()


def postprocess_script(script: str, language: str) -> str:
    if language == "hu":
        prompt = f"""
Javítsd ki az alábbi magyar short videó szkriptet.

Szabályok:
- Javítsd a helyesírást, ragozást és mondatszerkesztést.
- Javítsd a rossz vagy összecsúszott szavakat.
- A szöveg legyen természetes, kimondható magyar.
- Ne írj teljesen új szöveget.
- Ne hosszabbítsd meg jelentősen.
- A vesszők maradhatnak, ha helyesek.
- Csak a javított szöveget add vissza.

Szöveg:
{script}
"""
    else:
        prompt = f"""
Polish the following short-form video script.

Rules:
- Fix grammar and awkward phrasing.
- Keep it short.
- Keep the meaning.
- Return only the corrected text.

Text:
{script}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return response.output_text.strip()

def speed_up_audio(input_file: Path, output_file: Path, speed: float) -> None:
    if speed <= 0:
        raise ValueError("A speech_speed értéke legyen 0-nál nagyobb.")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", str(input_file),
        "-filter:a", f"atempo={speed}",
        "-vn",
        str(output_file)
    ]

    subprocess.run(cmd, check=True)

def generate_voice(
    script: str,
    output_file: Path,
    voice: str,
    tts_instructions: str
) -> None:
    audio = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=script,
        instructions=tts_instructions
    )

    with open(output_file, "wb") as f:
        f.write(audio.read())


def transcribe_to_verbose_json(audio_file: Path, output_json: Path) -> None:
    with open(audio_file, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    if hasattr(transcript, "model_dump_json"):
        output_json.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    elif hasattr(transcript, "model_dump"):
        output_json.write_text(
            json.dumps(transcript.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    else:
        output_json.write_text(
            json.dumps(transcript, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


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


def clean_text(text: str) -> str:
    text = text.replace("*", "")
    text = re.sub(r"[🚀✨🌌🤯😱🔥😂🤣]+", "", text)

    # Maradhatnak vesszők, csak a whitespace-et tisztítjuk
    text = re.sub(r"\s+", " ", text).strip()
    return text


def smart_chunk_words(words: list[str], min_words: int = 4, max_words: int = 7) -> list[list[str]]:
    chunks = []
    current = []

    for word in words:
        current.append(word)

        word_count = len(current)
        ends_sentence = bool(re.search(r"[.!?]$", word))

        if word_count >= min_words and ends_sentence:
            chunks.append(current)
            current = []
            continue

        if word_count >= max_words:
            chunks.append(current)
            current = []

    if current:
        if len(current) <= 2 and chunks:
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    if len(chunks) >= 2 and len(chunks[-1]) <= 2:
        chunks[-2].extend(chunks[-1])
        chunks.pop()

    return chunks


def wrap_text(text: str, max_chars: int = 13) -> str:
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

    if len(lines) > 2:
        merged = []
        current = ""

        for line in lines:
            candidate = line if not current else f"{current} {line}"
            if len(candidate) <= max_chars * 2:
                current = candidate
            else:
                if current:
                    merged.append(current)
                current = line

        if current:
            merged.append(current)

        lines = merged

    return r"\N".join(lines)


def load_verbose_segments(verbose_json_file: Path) -> list[dict]:
    data = json.loads(verbose_json_file.read_text(encoding="utf-8"))
    segments = data.get("segments", [])

    cleaned = []
    for seg in segments:
        text = clean_text(seg.get("text", ""))
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))

        if text and end > start:
            cleaned.append({
                "start": start,
                "end": end,
                "text": text
            })

    return cleaned


def segments_to_chunk_events(segments: list[dict]) -> list[dict]:
    events = []
    min_chunk_duration = 0.90

    for seg in segments:
        text = seg["text"]
        start = seg["start"]
        end = seg["end"]

        words = text.split()
        if not words:
            continue

        chunks = smart_chunk_words(words, min_words=4, max_words=7)
        total_words = len(words)
        total_duration = end - start

        if total_duration <= 0:
            continue

        current_start = start

        for i, chunk in enumerate(chunks):
            chunk_word_count = len(chunk)

            if i == len(chunks) - 1:
                chunk_start = current_start
                chunk_end = end
            else:
                fraction = chunk_word_count / total_words
                chunk_duration = max(min_chunk_duration, total_duration * fraction)

                remaining_chunks = len(chunks) - (i + 1)
                remaining_minimum = remaining_chunks * min_chunk_duration
                max_allowed_end = end - remaining_minimum

                chunk_start = current_start
                chunk_end = min(chunk_start + chunk_duration, max_allowed_end)

                if chunk_end <= chunk_start:
                    chunk_end = chunk_start + min_chunk_duration

                current_start = chunk_end

            chunk_text = " ".join(chunk)
            chunk_text = re.sub(r"\s+([,.!?])", r"\1", chunk_text)

            events.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text
            })

    return events


def make_ass_header(font_size: int, margin_v: int) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,3,0,2,80,80,{margin_v},1
Style: Active,Arial,{font_size},&H0000FFFF,&H0000FFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,3,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def escape_ass_text(text: str) -> str:
    text = text.replace(r"\N", "__LINEBREAK__")
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    text = text.replace("__LINEBREAK__", r"\N")
    return text


def write_chunk_ass(
    events: list[dict],
    ass_file: Path,
    caption_max_chars: int,
    caption_font_size: int,
    caption_margin_v: int
) -> None:
    lines = [make_ass_header(caption_font_size, caption_margin_v)]

    for ev in events:
        start = seconds_to_ass_time(ev["start"])
        end = seconds_to_ass_time(ev["end"])

        wrapped_text = wrap_text(ev["text"], max_chars=caption_max_chars)
        text = escape_ass_text(wrapped_text)

        lines.append(
            f"Dialogue: 0,{start},{end},Active,,0,0,0,,{text}"
        )

    ass_file.write_text("\n".join(lines), encoding="utf-8")


def render_video(
    background_video: Path,
    voice_file: Path,
    ass_file: Path,
    output_video: Path
) -> None:
    ass_path = str(ass_file).replace("\\", "/").replace(":", "\\:")

    vf_filter = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"ass='{ass_path}'"
    )

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-stream_loop", "-1",
        "-i", str(background_video),
        "-i", str(voice_file),
        "-vf", vf_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "medium",
        "-c:a", "aac",
        "-shortest",
        str(output_video)
    ]

    subprocess.run(cmd, check=True)


def generate_single_video(topic: str, video_name: str, index: int, config: dict) -> None:
    video_stem = Path(video_name).stem
    safe_name = video_stem

    background_video = ASSETS_DIR / video_name
    if not background_video.exists():
        raise FileNotFoundError(f"Hiányzik a videó: {background_video}")

    script_file = OUTPUT_DIR / f"{safe_name}_script.txt"
    raw_script_file = OUTPUT_DIR / f"{safe_name}_raw_script.txt"
    voice_file = OUTPUT_DIR / f"{safe_name}_voice.mp3"
    voice_fast_file = OUTPUT_DIR / f"{safe_name}_voice_fast.mp3"
    transcript_json = OUTPUT_DIR / f"{safe_name}_transcript_verbose.json"
    ass_file = OUTPUT_DIR / f"{safe_name}_captions_tiktok.ass"
    output_video = OUTPUT_DIR / f"{safe_name}_final_video.mp4"

    if config["language"] == "hu":
        tts_instructions = config["tts_instructions_hu"]
    else:
        tts_instructions = config["tts_instructions_en"]

    print(f"\n=== {index}. videó készítése ===")
    print(f"Téma: {topic}")
    print(f"Forrásvideó: {background_video.name}")
    print(f"Nyelv: {config['language']}")

    print("1. Script generálása...")
    raw_script = generate_script(topic, config["language"])
    raw_script_file.write_text(raw_script, encoding="utf-8")

    print("1.5 Script javítása...")
    script = postprocess_script(raw_script, config["language"])
    print(script)
    script_file.write_text(script, encoding="utf-8")

    print("2. Hang generálása OpenAI TTS-sel...")
    generate_voice(
        script,
        voice_file,
        voice=config["voice"],
        tts_instructions=tts_instructions
    )

    print("2.5 Hang gyorsítása...")
    speed_up_audio(
        voice_file,
        voice_fast_file,
        speed=float(config["speech_speed"])
    )

    print("3. Verbose transcript generálása...")
    transcribe_to_verbose_json(voice_fast_file, transcript_json)

    print("4. Caption engine futtatása...")
    segments = load_verbose_segments(transcript_json)
    events = segments_to_chunk_events(segments)
    write_chunk_ass(
        events,
        ass_file,
        caption_max_chars=config["caption_max_chars"],
        caption_font_size=config["caption_font_size"],
        caption_margin_v=config["caption_margin_v"]
    )

    print("5. Videó renderelése...")
    render_video(background_video, voice_fast_file, ass_file, output_video)

    print(f"Kész: {output_video}")


def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Hiányzik az OPENAI_API_KEY a .env fájlból.")

    if not Path(FFMPEG_EXE).exists():
        raise FileNotFoundError(f"Hiányzik az ffmpeg.exe: {FFMPEG_EXE}")

    config_file = BASE_DIR / "config.json"
    config = load_config(config_file)

    jobs_file = BASE_DIR / "videos.txt"
    jobs = load_video_jobs(jobs_file)

    if not jobs:
        raise RuntimeError("A videos.txt üres.")

    print(f"{len(jobs)} videófeladat betöltve.")
    print(f"Nyelv: {config['language']}")
    print(f"Voice: {config['voice']}")

    for i, job in enumerate(jobs, start=1):
        try:
            generate_single_video(job["topic"], job["video_name"], i, config)
        except Exception as e:
            print(f"Hiba a(z) {i}. videónál: {job['topic']}")
            print(e)

    print("\nMinden kész.")


if __name__ == "__main__":
    main()