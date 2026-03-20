import json
import re
from pathlib import Path

from app.utils import (
    clean_text,
    escape_ass_text,
    seconds_to_ass_time,
    wrap_caption_text,
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


def make_ass_header(config: dict) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {int(config["target_width"])}
PlayResY: {int(config["target_height"])}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Arial,{int(config["caption_font_size"])},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,3,0,2,120,120,{int(config["caption_margin_v"])},1
Style: Active,Arial,{int(config["caption_font_size"])},&H0000FFFF,&H0000FFFF,&H00000000,&H32000000,1,0,0,0,115,115,0,0,1,3,0,2,120,120,{int(config["caption_margin_v"])},1
Style: HookBase,Arial,{int(config["hook_font_size"])},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,130,130,{int(config["hook_margin_v"])},1
Style: HookActive,Arial,{int(config["hook_font_size"])},&H0000FFFF,&H0000FFFF,&H00000000,&H32000000,1,0,0,0,118,118,0,0,1,4,0,2,130,130,{int(config["hook_margin_v"])},1
Style: CtaBase,Arial,{int(config["cta_font_size"])},&H00FFFFFF,&H00FFFFFF,&H00000000,&H32000000,1,0,0,0,100,100,0,0,1,4,0,2,130,130,{int(config["cta_margin_v"])},1
Style: CtaActive,Arial,{int(config["cta_font_size"])},&H0000FF99,&H0000FF99,&H00000000,&H32000000,1,0,0,0,118,118,0,0,1,4,0,2,130,130,{int(config["cta_margin_v"])},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def split_script_lines(script: str) -> list[str]:
    return [strip_leading_caption_marker(line.strip()) for line in script.splitlines() if line.strip()]


def strip_leading_caption_marker(text: str) -> str:
    # Eltavolitjuk a sor eleji lista/bullet jeloleseket (pl. "- miert"),
    # mert overlay feliratban ez zavaróan nez ki.
    return re.sub(r"^\s*[-–—•*]+\s*(?=\w)", "", text).strip()


def is_marker_token(token: str) -> bool:
    return bool(re.match(r"^[-–—•*]+$", token.strip()))


def normalize_caption_token(token: str) -> str:
    token = strip_leading_caption_marker(token)
    token = re.sub(r"[^\w\s]", "", token, flags=re.UNICODE)
    token = re.sub(r"\s+", " ", token).strip()
    return token.upper()


def starts_with_uppercase_word(token: str) -> bool:
    cleaned = token.strip().lstrip("\"'„”«»([{")
    if not cleaned:
        return False
    first_char = cleaned[0]
    return first_char.isalpha() and first_char.isupper()


def get_event_type(index: int, total: int) -> str:
    if index == 0:
        return "hook"
    if index == total - 1:
        return "cta"
    return "body"


def get_event_max_chars(event_type: str, config: dict) -> int:
    if event_type == "hook":
        return int(config["intro_caption_max_chars"])
    if event_type == "cta":
        return int(config.get("cta_caption_max_chars", config["caption_max_chars"]))
    return int(config["caption_max_chars"])


def shift_orphan_last_word_to_next_event(events: list[dict], config: dict) -> list[dict]:
    max_lines = int(config.get("caption_max_lines", 2))

    for i in range(len(events) - 1):
        current = events[i]
        nxt = events[i + 1]

        current_words = [w for w in current.get("text", "").split() if w]
        current_times = current.get("word_times", []) or []
        if len(current_words) <= 1 or len(current_times) != len(current_words):
            continue

        max_chars = get_event_max_chars(current.get("type", "body"), config)
        wrapped = wrap_caption_text(" ".join(current_words), max_chars=max_chars, max_lines=max_lines)
        wrapped_parts = wrapped.split(r"\N")
        if len(wrapped_parts) < 2:
            continue

        last_line_words = [w for w in wrapped_parts[-1].split() if w]
        if len(last_line_words) != 1:
            continue

        next_words = [w for w in nxt.get("text", "").split() if w]
        next_times = nxt.get("word_times", []) or []
        if len(next_words) != len(next_times):
            # Biztonsagi fallback: ha mar eleve nincs osszhang,
            # ne tologassunk tovabb szavakat.
            continue

        moved_word = current_words[-1]
        moved_time = current_times[-1]

        current["text"] = " ".join(current_words[:-1])
        current["word_times"] = current_times[:-1]

        # Fontos: az áttolt szó ne hozza előre a kovetkezo event kezdetet.
        # A kovetkezo caption csak az eredeti kovetkezo TTS indulaskor jelenjen meg.
        if next_times:
            next_anchor_start = float(next_times[0]["start"])
            moved_min_duration = float(config.get("caption_moved_word_min_duration_sec", 0.12))
            moved_time = {
                "word": moved_time["word"],
                "start": next_anchor_start,
                "end": next_anchor_start + moved_min_duration
            }

        nxt["text"] = " ".join([moved_word] + next_words).strip()
        nxt["word_times"] = [moved_time] + next_times

    return events


def split_display_words_to_phrases(
    words: list[str],
    min_words: int = 2,
    max_words: int = 4,
    word_times: list[dict] | None = None
) -> tuple[list[list[str]], list[str]]:
    phrases = []
    break_reasons = []
    current = []

    for idx, word in enumerate(words):
        current.append(word)
        has_next = idx + 1 < len(words)
        next_word = words[idx + 1] if idx + 1 < len(words) else ""

        ends_pause = bool(re.search(r"[,;:!?]$", word))
        ends_sentence = bool(re.search(r"[.]$", word))

        pause_to_next = 0.0
        if has_next and word_times and idx + 1 < len(word_times):
            pause_to_next = max(
                0.0,
                float(word_times[idx + 1]["start"]) - float(word_times[idx]["end"])
            )

        if len(current) >= min_words and (ends_pause or ends_sentence):
            phrases.append(current)
            if has_next:
                break_reasons.append("punct")
            current = []
            continue

        if len(current) >= max_words:
            phrases.append(current)
            if has_next:
                break_reasons.append("max_words")
            current = []

    if current:
        if len(current) <= 1 and phrases:
            phrases[-1].extend(current)
        else:
            phrases.append(current)

    return phrases, break_reasons


def build_phrase_timed_events_from_script(
    transcript_data: dict,
    final_script: str,
    config: dict
) -> list[dict]:
    words = transcript_data.get("words", []) or []
    segments = transcript_data.get("segments", []) or []
    script_lines = split_script_lines(final_script)

    if not script_lines:
        return []

    if not words and not segments:
        return []

    # 1) Először sorszintű eseményeket építünk
    if not words:
        total_start = segments[0]["start"]
        total_end = segments[-1]["end"]
        total_duration = max(0.2, total_end - total_start)

        line_lengths = [max(1, len(line.split())) for line in script_lines]
        total_words = sum(line_lengths)

        line_events = []
        cursor = total_start

        for i, line in enumerate(script_lines):
            if i == len(script_lines) - 1:
                start = cursor
                end = total_end
            else:
                dur = total_duration * (line_lengths[i] / total_words)
                start = cursor
                end = start + dur
                cursor = end

            display_words = line.split()
            per_word = max(0.05, (end - start) / max(1, len(display_words)))

            word_times = []
            for wi, w in enumerate(display_words):
                w_start = start + wi * per_word
                w_end = start + (wi + 1) * per_word
                if wi == len(display_words) - 1:
                    w_end = end

                word_times.append({
                    "word": w,
                    "start": w_start,
                    "end": w_end
                })

            line_events.append({
                "start": start,
                "end": end,
                "text": line,
                "type": get_event_type(i, len(script_lines)),
                "word_times": word_times
            })

    else:
        total_word_count = len(words)
        line_lengths = [max(1, len(line.split())) for line in script_lines]
        target_total = sum(line_lengths)

        assigned_counts = []
        consumed = 0

        for i, length in enumerate(line_lengths):
            if i == len(line_lengths) - 1:
                count = total_word_count - consumed
            else:
                ratio = length / target_total
                count = max(1, round(total_word_count * ratio))
                remaining_min = len(line_lengths) - (i + 1)
                max_now = total_word_count - consumed - remaining_min
                count = min(count, max_now)

            assigned_counts.append(count)
            consumed += count

        diff = total_word_count - sum(assigned_counts)
        if diff != 0 and assigned_counts:
            assigned_counts[-1] += diff

        line_events = []
        idx = 0

        for i, line in enumerate(script_lines):
            count = assigned_counts[i]
            line_word_times = words[idx: idx + count]
            idx += count

            if not line_word_times:
                continue

            line_events.append({
                "start": line_word_times[0]["start"],
                "end": line_word_times[-1]["end"],
                "text": line,
                "type": get_event_type(i, len(script_lines)),
                "word_times": line_word_times
            })

    # 2) A sorokat phrase-ekre bontjuk
    phrase_events = []

    for line_event in line_events:
        timed_words = line_event["word_times"]
        script_words = line_event["text"].split()
        timed_display_words = [item["word"] for item in timed_words]

        # Ha eltér a script és a valós szó-időzítés szó darabszáma,
        # akkor a timestampelt szavakat használjuk, hogy ne csússzon el a highlight.
        if len(script_words) == len(timed_words):
            display_words = script_words
        else:
            display_words = timed_display_words

        phrases, break_reasons = split_display_words_to_phrases(
            display_words,
            min_words=int(config.get("caption_phrase_min_words", 2)),
            max_words=int(config.get("caption_phrase_max_words", 4)),
            word_times=timed_words if len(display_words) == len(timed_words) else None
        )

        cursor = 0
        for phrase_idx, phrase in enumerate(phrases):
            count = len(phrase)
            phrase_word_times = timed_words[cursor: cursor + count]
            cursor += count

            if not phrase_word_times:
                continue

            # Vezető marker tokenek (pl. "-") kiszedése a szövegből és a timingból is,
            # hogy szóindexre pontos maradjon a highlight.
            while phrase and phrase_word_times and is_marker_token(phrase[0]):
                phrase = phrase[1:]
                phrase_word_times = phrase_word_times[1:]

            if not phrase or not phrase_word_times:
                continue

            normalized_words = []
            normalized_word_times = []

            for raw_word, wt in zip(phrase, phrase_word_times):
                normalized = normalize_caption_token(raw_word)
                if normalized:
                    normalized_words.append(normalized)
                    normalized_word_times.append(wt)

            if not normalized_words or not normalized_word_times:
                continue

            phrase_text = " ".join(normalized_words)
            phrase_word_times = normalized_word_times

            phrase_events.append({
                "start": phrase_word_times[0]["start"],
                "end": phrase_word_times[-1]["end"],
                "text": phrase_text,
                "type": line_event["type"],
                "word_times": phrase_word_times
            })

    return shift_orphan_last_word_to_next_event(phrase_events, config)


def add_punctuation_pause_to_word_times(word_times: list[dict], config: dict) -> list[dict]:
    comma_pause = float(config.get("caption_comma_pause_sec", 0.10))
    sentence_pause = float(config.get("caption_sentence_pause_sec", 0.14))
    max_cumulative_shift = float(config.get("caption_max_cumulative_pause_shift_sec", 0.18))

    adjusted = []
    cumulative_shift = 0.0

    for item in word_times:
        word = item["word"]
        start = float(item["start"]) + cumulative_shift
        end = float(item["end"]) + cumulative_shift

        extra = 0.0
        if re.search(r"[,;:]\s*$", word):
            extra = comma_pause
        elif re.search(r"[.!?]\s*$", word):
            extra = sentence_pause

        adjusted.append({
            "word": word,
            "start": start,
            "end": end + extra
        })
        cumulative_shift = min(max_cumulative_shift, cumulative_shift + extra)

    return adjusted


def write_word_highlight_ass(events: list[dict], ass_file: Path, config: dict) -> None:
    lines = [make_ass_header(config)]

    global_offset = float(config.get("caption_time_offset_sec", 0.0))
    gap_before_next = float(config.get("caption_gap_before_next_sec", 0.03))

    for event_idx, ev in enumerate(events):
        line_text = ev["text"].strip()
        event_type = ev["type"]
        word_times = add_punctuation_pause_to_word_times(ev["word_times"], config)

        if not line_text or not word_times:
            continue

        if event_type == "hook":
            max_chars = int(config["intro_caption_max_chars"])
            base_style = "HookBase"
            active_style = "HookActive"
        elif event_type == "cta":
            max_chars = int(config.get("cta_caption_max_chars", config["caption_max_chars"]))
            base_style = "CtaBase"
            active_style = "CtaActive"
        else:
            max_chars = int(config["caption_max_chars"])
            base_style = "Base"
            active_style = "Active"

        wrapped_text = wrap_caption_text(
            line_text,
            max_chars=max_chars,
            max_lines=int(config.get("caption_max_lines", 2))
        )

        wrapped_parts = wrapped_text.split(r"\N")

        flat_tokens = []
        token_word_count = 0
        display_words = line_text.split()

        for part_idx, part in enumerate(wrapped_parts):
            part_words = [w for w in part.split() if w]

            for _ in part_words:
                if token_word_count < len(display_words):
                    flat_tokens.append(display_words[token_word_count])
                    token_word_count += 1

            if part_idx < len(wrapped_parts) - 1:
                flat_tokens.append(r"\N")

        while token_word_count < len(display_words):
            flat_tokens.append(display_words[token_word_count])
            token_word_count += 1

        def build_ass_text(highlight_idx=None) -> str:
            rendered = []
            real_idx = 0

            for tok in flat_tokens:
                if tok == r"\N":
                    rendered.append(r"\N")
                    continue

                safe = escape_ass_text(tok)

                if highlight_idx is not None and real_idx == highlight_idx:
                    rendered.append(r"{\r" + active_style + r"}" + safe + r"{\r" + base_style + r"}")
                else:
                    rendered.append(safe)

                real_idx += 1

            out = ""
            for tok in rendered:
                if tok == r"\N":
                    out += r"\N"
                else:
                    if out and not out.endswith(r"\N"):
                        out += " "
                    out += tok
            return out

        event_start = float(word_times[0]["start"]) + global_offset
        event_end = float(word_times[-1]["end"]) + global_offset

        next_start = None
        if event_idx + 1 < len(events):
            next_start = float(events[event_idx + 1]["start"]) + global_offset

        if next_start is not None:
            full_line_end = max(event_end, next_start - gap_before_next)
        else:
            full_line_end = event_end + float(config.get("caption_end_hold_sec", 0.18))

        for i in range(len(word_times)):
            start = float(word_times[i]["start"]) + global_offset

            if i < len(word_times) - 1:
                next_start = float(word_times[i + 1]["start"]) + global_offset
                # Soron belul folyamatosan latszodjon a felirat:
                # a kiemeles a kovetkezo szo kezdeteeig tart.
                current_end = float(word_times[i]["end"]) + global_offset
                if next_start <= start + 0.001:
                    # Azonos indulasu tokeneknel ne legyen villanas (0 hosszu highlight).
                    end = min(current_end, full_line_end)
                else:
                    end = min(next_start, full_line_end)
            else:
                end = full_line_end

            if start < event_start:
                start = event_start
            if end <= start:
                end = start + 0.05

            lines.append(
                f"Dialogue: 0,{seconds_to_ass_time(start)},{seconds_to_ass_time(end)},{base_style},,0,0,0,,{build_ass_text(i)}"
            )

    ass_file.write_text("\n".join(lines), encoding="utf-8")


def build_caption_assets(variant, audio_fast_file: Path, transcript_json_file: Path, config: dict) -> dict:
    transcript_data = load_verbose_transcript(transcript_json_file)

    events = build_phrase_timed_events_from_script(
        transcript_data,
        variant.full_script,
        config
    )

    ass_file = variant.output_dir / "captions.ass"
    write_word_highlight_ass(events, ass_file, config)

    return {
        "ass_file": ass_file,
        "events_count": len(events),
        "audio_fast_file": audio_fast_file
    }
