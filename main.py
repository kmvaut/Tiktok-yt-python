import json
import os
import re
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

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
        "speech_speed"
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


def call_text_model(prompt: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return response.output_text.strip()


def generate_hook_variants(topic: str, language: str, n: int = 3) -> list[str]:
    if language == "hu":
        prompt = f"""
Írj {n} különböző TikTok hookot magyarul.

Téma: {topic}

Szabályok:
- mindegyik külön sorban legyen
- max 12 szó
- legyenek különböző stílusok:
  - kíváncsiság
  - sokk
  - titok
- természetes magyar
- ne használj emojit
- ne számozd
"""
    else:
        prompt = f"""
Write {n} different TikTok hooks.

Topic: {topic}

Rules:
- each on a new line
- max 12 words
- use different styles:
  - curiosity
  - shock
  - secret
- natural spoken English
- no emojis
- do not number them
"""

    text = call_text_model(prompt)
    hooks = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]
    return hooks[:n]


def generate_body(topic: str, language: str) -> str:
    if language == "hu":
        prompt = f"""
Írj rövid TikTok videó törzsszöveget magyarul.

Téma: {topic}

Szabályok:
- 2-4 rövid mondat
- legyen jól kimondható
- természetes magyar legyen
- ne legyen túl sűrű
- ne legyen túl hosszú
- ne használj emojit
- csak a törzsszöveget add vissza
"""
    else:
        prompt = f"""
Write the body of a short TikTok video.

Topic: {topic}

Rules:
- 2-4 short spoken sentences
- natural spoken English
- easy to narrate
- short and punchy
- no emojis
- return only the body text
"""
    return call_text_model(prompt)


def generate_cta(language: str) -> str:
    if language == "hu":
        prompt = """
Írj 1 rövid CTA mondatot magyar TikTok videó végére.

Szabályok:
- maximum 8 szó
- természetes legyen
- ne legyen erőltetett
- ne használj emojit
- csak 1 mondatot adj vissza
"""
    else:
        prompt = """
Write 1 short CTA for the end of a TikTok video.

Rules:
- max 8 words
- natural
- not pushy
- no emojis
- return only 1 sentence
"""
    return call_text_model(prompt)


def assemble_script(hook: str, body: str, cta: str) -> str:
    parts = [hook.strip(), body.strip(), cta.strip()]
    return "\n".join([p for p in parts if p])


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
- Tartsd meg a rövid videós stílust.
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
    return call_text_model(prompt)


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


def speed_up_audio(input_file: Path, output_file: Path, speed: float) -> None:
    if speed <= 0:
        raise ValueError("A speech_speed legyen 0-nál nagyobb.")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-i", str(input_file),
        "-filter:a", f"atempo={speed}",
        "-vn",
        str(output_file)
    ]

    subprocess.run(cmd, check=True)


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


def split_script_sentences(script: str) -> list[str]:
    lines = [line.strip() for line in script.splitlines() if line.strip()]
    if lines:
        return lines

    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return [p.strip() for p in parts if p.strip()]


def allocate_sentence_times(script_sentences: list[str], segment_start: float, segment_end: float) -> list[dict]:
    if not script_sentences:
        return []

    total_duration = max(0.1, segment_end - segment_start)
    sentence_lengths = [max(1, len(s.split())) for s in script_sentences]
    total_words = sum(sentence_lengths)

    events = []
    cursor = segment_start

    for i, sentence in enumerate(script_sentences):
        word_count = sentence_lengths[i]

        if i == len(script_sentences) - 1:
            start = cursor
            end = segment_end
        else:
            fraction = word_count / total_words
            dur = total_duration * fraction
            start = cursor
            end = start + dur
            cursor = end

        events.append({
            "start": start,
            "end": end,
            "text": sentence
        })

    return events


def segments_to_chunk_events_from_script(
    segments: list[dict],
    final_script: str
) -> list[dict]:
    if not segments:
        return []

    segment_start = segments[0]["start"]
    segment_end = segments[-1]["end"]

    script_sentences = split_script_sentences(final_script)
    sentence_events = allocate_sentence_times(script_sentences, segment_start, segment_end)

    events = []
    min_chunk_duration = 0.90

    for sentence_event in sentence_events:
        text = sentence_event["text"]
        start = sentence_event["start"]
        end = sentence_event["end"]

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
    background_video = ASSETS_DIR / video_name

    if not background_video.exists():
        raise FileNotFoundError(f"Hiányzik a videó: {background_video}")

    if config["language"] == "hu":
        tts_instructions = config["tts_instructions_hu"]
    else:
        tts_instructions = config["tts_instructions_en"]

    print(f"\n=== {index}. téma ===")
    print(f"Téma: {topic}")

    print("1. Hook variációk generálása...")
    hooks = generate_hook_variants(topic, config["language"], n=3)

    print("2. Body generálása...")
    body = generate_body(topic, config["language"])
    print(body)

    print("3. CTA generálása...")
    cta = generate_cta(config["language"])
    print(cta)

    for i, hook in enumerate(hooks, start=1):
        print(f"\n--- Hook {i} ---")
        print(hook)

        safe_name = f"{video_stem}_hook{i}"

        hook_file = OUTPUT_DIR / f"{safe_name}_hook.txt"
        body_file = OUTPUT_DIR / f"{safe_name}_body.txt"
        cta_file = OUTPUT_DIR / f"{safe_name}_cta.txt"
        raw_script_file = OUTPUT_DIR / f"{safe_name}_raw_script.txt"
        script_file = OUTPUT_DIR / f"{safe_name}_script.txt"
        voice_file = OUTPUT_DIR / f"{safe_name}_voice.mp3"
        voice_fast_file = OUTPUT_DIR / f"{safe_name}_voice_fast.mp3"
        transcript_json = OUTPUT_DIR / f"{safe_name}_transcript.json"
        ass_file = OUTPUT_DIR / f"{safe_name}.ass"
        output_video = OUTPUT_DIR / f"{safe_name}_final.mp4"

        hook_file.write_text(hook, encoding="utf-8")
        body_file.write_text(body, encoding="utf-8")
        cta_file.write_text(cta, encoding="utf-8")

        print("4. Script összeállítása...")
        raw_script = assemble_script(hook, body, cta)
        raw_script_file.write_text(raw_script, encoding="utf-8")

        print("5. Script javítása...")
        script = postprocess_script(raw_script, config["language"])
        script_file.write_text(script, encoding="utf-8")
        print(script)

        print("6. Hang generálása...")
        generate_voice(
            script,
            voice_file,
            voice=config["voice"],
            tts_instructions=tts_instructions
        )

        print("6.5 Hang gyorsítása...")
        speed_up_audio(
            voice_file,
            voice_fast_file,
            speed=float(config["speech_speed"])
        )

        print("7. Transcript...")
        transcribe_to_verbose_json(voice_fast_file, transcript_json)

        print("8. Caption...")
        segments = load_verbose_segments(transcript_json)
        events = segments_to_chunk_events_from_script(segments, script)

        write_chunk_ass(
            events,
            ass_file,
            caption_max_chars=config["caption_max_chars"],
            caption_font_size=config["caption_font_size"],
            caption_margin_v=config["caption_margin_v"]
        )

        print("9. Render...")
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