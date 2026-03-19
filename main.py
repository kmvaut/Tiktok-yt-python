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
        "speech_speed",
        "visual_zoom_speed",
        "visual_contrast",
        "visual_saturation",
        "hook_font_size",
        "hook_margin_v",
        "cta_font_size",
        "cta_margin_v",
        "intro_overlay_duration",
        "intro_overlay_alpha",
        "intro_caption_max_chars",
        "hook_variants"
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"Hiányzik a config.json-ból ez a mező: {key}")

    if config["language"] not in ["hu", "en"]:
        raise ValueError("A config.json 'language' mezője csak 'hu' vagy 'en' lehet.")

    if int(config["hook_variants"]) < 1:
        raise ValueError("A hook_variants legalább 1 legyen.")

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
- maximum 12 szó
- különböző stílusok legyenek:
  - kíváncsiság
  - sokk
  - titok
  - figyelmeztetés
  - meglepő állítás
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
- maximum 12 words
- use different styles:
  - curiosity
  - shock
  - secret
  - warning
  - surprising claim
- natural spoken English
- no emojis
- do not number them
"""

    text = call_text_model(prompt)
    hooks = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]

    if len(hooks) < n:
        hooks = hooks + hooks[: max(0, n - len(hooks))]

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
- maximum 8 words
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
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"]
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


def load_verbose_transcript(verbose_json_file: Path) -> dict:
    data = json.loads(verbose_json_file.read_text(encoding="utf-8"))

    segments = data.get("segments", []) or []
    words = data.get("words", []) or []

    cleaned_segments = []
    for seg in segments:
        text = clean_text(seg.get("text", ""))
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))

        if text and end > start:
            cleaned_segments.append({
                "start": start,
                "end": end,
                "text": text
            })

    cleaned_words = []
    for word_item in words:
        word = clean_text(word_item.get("word", ""))
        start = float(word_item.get("start", 0))
        end = float(word_item.get("end", 0))

        if word and end > start:
            cleaned_words.append({
                "word": word,
                "start": start,
                "end": end
            })

    return {
        "segments": cleaned_segments,
        "words": cleaned_words,
        "text": clean_text(data.get("text", ""))
    }


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

        event_type = "body"
        if i == 0:
            event_type = "hook"
        elif i == len(script_sentences) - 1:
            event_type = "cta"

        events.append({
            "start": start,
            "end": end,
            "text": sentence,
            "type": event_type
        })

    return events


def build_word_timed_events_from_script(
    transcript_data: dict,
    final_script: str
) -> list[dict]:
    words = transcript_data.get("words", []) or []
    segments = transcript_data.get("segments", []) or []

    # fallback
    if not words:
        return build_estimated_events_from_script(segments, final_script)

    script_sentences = split_script_sentences(final_script)
    if not script_sentences:
        return build_estimated_events_from_script(segments, final_script)

    total_word_count = len(words)
    sentence_lengths = [max(1, len(s.split())) for s in script_sentences]
    target_total = sum(sentence_lengths)

    # szóelosztás sentence-enként a script alapján
    assigned_counts = []
    consumed = 0
    for i, length in enumerate(sentence_lengths):
        if i == len(sentence_lengths) - 1:
            count = total_word_count - consumed
        else:
            ratio = length / target_total
            count = max(1, round(total_word_count * ratio))
            remaining_min = len(sentence_lengths) - (i + 1)
            max_now = total_word_count - consumed - remaining_min
            count = min(count, max_now)
        assigned_counts.append(count)
        consumed += count

    # korrigálás
    diff = total_word_count - sum(assigned_counts)
    if diff != 0 and assigned_counts:
        assigned_counts[-1] += diff

    sentence_events = []
    idx = 0
    for sent_idx, sentence in enumerate(script_sentences):
        count = assigned_counts[sent_idx]
        sentence_words = words[idx: idx + count]
        idx += count

        if not sentence_words:
            continue

        start = sentence_words[0]["start"]
        end = sentence_words[-1]["end"]

        event_type = "body"
        if sent_idx == 0:
            event_type = "hook"
        elif sent_idx == len(script_sentences) - 1:
            event_type = "cta"

        sentence_events.append({
            "start": start,
            "end": end,
            "text": sentence,
            "type": event_type,
            "word_times": sentence_words
        })

    events = []

    for sentence_event in sentence_events:
        text = sentence_event["text"]
        event_type = sentence_event["type"]
        word_times = sentence_event["word_times"]

        display_words = text.split()
        chunks = smart_chunk_words(display_words, min_words=4, max_words=7)

        if not chunks:
            continue

        cursor = 0
        for chunk in chunks:
            count = len(chunk)
            matched_word_times = word_times[cursor: cursor + count]
            cursor += count

            if not matched_word_times:
                continue

            chunk_start = matched_word_times[0]["start"]
            chunk_end = matched_word_times[-1]["end"]
            chunk_text = " ".join(chunk)
            chunk_text = re.sub(r"\s+([,.!?])", r"\1", chunk_text)

            events.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text,
                "type": event_type,
                "word_times": matched_word_times
            })

    return events


def build_estimated_events_from_script(
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
        event_type = sentence_event["type"]

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

            # becsült word times
            chunk_duration = max(0.05, chunk_end - chunk_start)
            per_word = chunk_duration / len(chunk)

            word_times = []
            for wi, w in enumerate(chunk):
                w_start = chunk_start + wi * per_word
                w_end = chunk_start + (wi + 1) * per_word
                if wi == len(chunk) - 1:
                    w_end = chunk_end
                word_times.append({
                    "word": w,
                    "start": w_start,
                    "end": w_end
                })

            events.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text,
                "type": event_type,
                "word_times": word_times
            })

    return events


def make_ass_header(
    font_size: int,
    margin_v: int,
    hook_font_size: int,
    hook_margin_v: int,
    cta_font_size: int,
    cta_margin_v: int
) -> str:
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
Style: HookBase,Arial,{hook_font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,70,70,{hook_margin_v},1
Style: HookActive,Arial,{hook_font_size},&H0000FFFF,&H0000FFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,70,70,{hook_margin_v},1
Style: CtaBase,Arial,{cta_font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,70,70,{cta_margin_v},1
Style: CtaActive,Arial,{cta_font_size},&H0000FF99,&H0000FF99,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,70,70,{cta_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def escape_ass_text(text: str) -> str:
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    return text


def write_word_highlight_ass(
    events: list[dict],
    ass_file: Path,
    caption_max_chars: int,
    intro_caption_max_chars: int,
    caption_font_size: int,
    caption_margin_v: int,
    hook_font_size: int,
    hook_margin_v: int,
    cta_font_size: int,
    cta_margin_v: int
) -> None:
    lines = [make_ass_header(
        caption_font_size,
        caption_margin_v,
        hook_font_size,
        hook_margin_v,
        cta_font_size,
        cta_margin_v
    )]

    for ev in events:
        chunk_text = ev["text"].strip()
        event_type = ev.get("type", "body")
        word_times = ev.get("word_times", [])

        if not chunk_text or not word_times:
            continue

        if event_type == "hook":
            max_chars = intro_caption_max_chars
            base_style = "HookBase"
            active_style = "HookActive"
        elif event_type == "cta":
            max_chars = caption_max_chars
            base_style = "CtaBase"
            active_style = "CtaActive"
        else:
            max_chars = caption_max_chars
            base_style = "Base"
            active_style = "Active"

        wrapped_text = wrap_text(chunk_text, max_chars=max_chars)

        wrapped_parts = wrapped_text.split(r"\N")
        flat_tokens = []

        for line_idx, part in enumerate(wrapped_parts):
            line_words = [w for w in part.split() if w]
            flat_tokens.extend(line_words)
            if line_idx < len(wrapped_parts) - 1:
                flat_tokens.append(r"\N")

        real_word_positions = [i for i, tok in enumerate(flat_tokens) if tok != r"\N"]
        real_words = [flat_tokens[i] for i in real_word_positions]

        # ha a tördelés miatt eltérne a darabszám, fallback az event word_times-ára
        if len(real_words) != len(word_times):
            real_words = [w["word"] for w in word_times]
            flat_tokens = real_words[:]
            real_word_positions = list(range(len(real_words)))

        for highlight_idx in range(len(word_times)):
            start = float(word_times[highlight_idx]["start"])
            end = float(word_times[highlight_idx]["end"])

            if end <= start:
                end = start + 0.05

            rendered_tokens = []
            real_idx = 0

            for tok in flat_tokens:
                if tok == r"\N":
                    rendered_tokens.append(r"\N")
                    continue

                safe_tok = escape_ass_text(tok)

                if real_idx == highlight_idx:
                    rendered_tokens.append(r"{\r" + active_style + "}" + safe_tok + r"{\r" + base_style + "}")
                else:
                    rendered_tokens.append(safe_tok)

                real_idx += 1

            ass_text = ""
            for tok in rendered_tokens:
                if tok == r"\N":
                    ass_text += r"\N"
                else:
                    if ass_text and not ass_text.endswith(r"\N"):
                        ass_text += " "
                    ass_text += tok

            start_ass = seconds_to_ass_time(start)
            end_ass = seconds_to_ass_time(end)

            lines.append(
                f"Dialogue: 0,{start_ass},{end_ass},{base_style},,0,0,0,,{ass_text}"
            )

    ass_file.write_text("\n".join(lines), encoding="utf-8")


def render_video(
    background_video: Path,
    voice_file: Path,
    ass_file: Path,
    output_video: Path,
    zoom_speed: float,
    contrast: float,
    saturation: float,
    intro_overlay_duration: float,
    intro_overlay_alpha: float
) -> None:
    ass_path = str(ass_file).replace("\\", "/").replace(":", "\\:")

    vf_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"eq=contrast={contrast}:saturation={saturation},"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{intro_overlay_alpha}:t=fill:enable='between(t,0,{intro_overlay_duration})',"
        f"zoompan=z='min(zoom+{zoom_speed},1.08)':d=1:s=1080x1920:fps=30,"
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


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def generate_single_video(topic: str, video_name: str, index: int, config: dict) -> None:
    video_stem = Path(video_name).stem
    background_video = ASSETS_DIR / video_name

    if not background_video.exists():
        raise FileNotFoundError(f"Hiányzik a videó: {background_video}")

    video_output_dir = OUTPUT_DIR / video_stem
    ensure_dir(video_output_dir)

    if config["language"] == "hu":
        tts_instructions = config["tts_instructions_hu"]
    else:
        tts_instructions = config["tts_instructions_en"]

    hook_count = int(config["hook_variants"])

    print(f"\n=== {index}. téma ===")
    print(f"Téma: {topic}")
    print(f"Hook variációk száma: {hook_count}")

    print("1. Hook variációk generálása...")
    hooks = generate_hook_variants(topic, config["language"], n=hook_count)

    print("2. Body generálása...")
    body = generate_body(topic, config["language"])
    print(body)

    print("3. CTA generálása...")
    cta = generate_cta(config["language"])
    print(cta)

    for i, hook in enumerate(hooks, start=1):
        print(f"\n--- Hook {i} ---")
        print(hook)

        hook_dir = video_output_dir / f"hook_{i}"
        ensure_dir(hook_dir)

        hook_file = hook_dir / "hook.txt"
        body_file = hook_dir / "body.txt"
        cta_file = hook_dir / "cta.txt"
        raw_script_file = hook_dir / "raw_script.txt"
        script_file = hook_dir / "script.txt"
        voice_file = hook_dir / "voice.mp3"
        voice_fast_file = hook_dir / "voice_fast.mp3"
        transcript_json = hook_dir / "transcript.json"
        ass_file = hook_dir / "captions.ass"
        output_video = hook_dir / "final.mp4"

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

        print("7. Transcript szó-időzítéssel...")
        transcribe_to_verbose_json(voice_fast_file, transcript_json)

        print("8. Caption...")
        transcript_data = load_verbose_transcript(transcript_json)
        events = build_word_timed_events_from_script(transcript_data, script)

        write_word_highlight_ass(
            events,
            ass_file,
            caption_max_chars=int(config["caption_max_chars"]),
            intro_caption_max_chars=int(config["intro_caption_max_chars"]),
            caption_font_size=int(config["caption_font_size"]),
            caption_margin_v=int(config["caption_margin_v"]),
            hook_font_size=int(config["hook_font_size"]),
            hook_margin_v=int(config["hook_margin_v"]),
            cta_font_size=int(config["cta_font_size"]),
            cta_margin_v=int(config["cta_margin_v"])
        )

        print("9. Render...")
        render_video(
            background_video,
            voice_fast_file,
            ass_file,
            output_video,
            zoom_speed=float(config["visual_zoom_speed"]),
            contrast=float(config["visual_contrast"]),
            saturation=float(config["visual_saturation"]),
            intro_overlay_duration=float(config["intro_overlay_duration"]),
            intro_overlay_alpha=float(config["intro_overlay_alpha"])
        )

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
    print(f"Hook variációk: {config['hook_variants']}")

    for i, job in enumerate(jobs, start=1):
        try:
            generate_single_video(job["topic"], job["video_name"], i, config)
        except Exception as e:
            print(f"Hiba a(z) {i}. videónál: {job['topic']}")
            print(e)

    print("\nMinden kész.")


if __name__ == "__main__":
    main()