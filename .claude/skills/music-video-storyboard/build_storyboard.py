#!/usr/bin/env python3
"""Build a storyboard JSON blueprint from a finalized AI Studio markdown storyboard.

The markdown is the model's 1st response: Step 1 reference prompts, Step 2 story
beats + audio design, and Step 3 clip bullets + six-part ref2va blocks. This
script extracts every structural field it can, derives the schema-required but
non-explicit fields with transparent defaults, and deep-merges an optional
overrides JSON for run-specific authored prose (concept, camera, continuity,
quality priorities).

Usage:
    python3 -I build_storyboard.py --md outputs/<slug>.md \
        --out outputs/<slug>-storyboard.json --audio outputs/<slug>.mp3 \
        [--aspect-ratio 9:16] \
        [--character-name Wanderer] \
        [--character-file character_wanderer_front.png] \
        [--env-file env_neon_bar_rain.png] \
        [--prop-file prop_crystal_whiskey_glass.png] \
        [--overrides overrides.json] [--no-extend-last]

Step 1 sheets are accepted in four formats, in this order: a fenced code block
under an H4 heading (canonical), any fenced code block, a blockquote block, or
bulleted key/value lines. Clip headings accept `#### Clip 1` and
`#### Clip [1]` (with an optional bracketed timecode on the same line).

The ref2va sections are copied verbatim. Auto-filled fields are deliberately
generic; use --overrides to correct any field without hand-editing the JSON.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REF2VA_LABELS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]
LIST_SECTIONS = {"subject_definitions", "retention_analysis"}
REQUIRED_TOP = [
    "project",
    "subject_continuity",
    "segments",
    "continuity_requirements",
    "quality_priorities",
    "assumptions_and_defaults",
    "open_questions",
]
REQUIRED_SEGMENT = [
    "id", "timecode", "start", "end", "duration", "narrative_purpose",
    "action", "camera", "secondary_motion", "transition_in", "transition_out",
    "cut", "ref2va",
]
CODE_BLOCK_RE = re.compile(r"```(?:text)?[ \t]*\n(.*?)\n```", re.S)
H4_RE = re.compile(r"^####\s+(.+?)\s*$", re.M)
BEAT_RE = re.compile(
    r"^\s*[-*]\s*(\d{1,2}:\d{2}(?:\.\d+)?)\s*[-–—]\s*"
    r"(\d{1,2}:\d{2}(?:\.\d+)?)\s*[:：]\s*(.+)$"
)
BULLET_KV_RE = re.compile(r"^\s*[-*]\s*([^:]+):\s*(.+)$")
CLIP_RE = re.compile(r"^####\s+Clip\s+\[?(\d+)\]?\s*(.*)$", re.M)
COLOR_WORDS = [
    "charcoal", "black", "white", "grey", "gray", "amber", "cyan", "blue",
    "burgundy", "red", "green", "gold", "silver", "mahogany", "brown",
    "tungsten", "neon", "teal", "orange", "violet", "purple", "pink", "beige",
]
CHARACTER_WORDS = (
    " man", " woman", " person", " character", " protagonist", " boy",
    " girl", " child", " actor", " figure", " he ", " she ",
)
ENVIRONMENT_WORDS = (
    "window", "bar", "room", "street", "interior", "exterior", "environment",
    "location", "booth", "forest", "city", "landscape", "set", "stage",
    "tavern", "house", "cafe", "club",
)


class BuildError(Exception):
    """A markdown capture that cannot be turned into a storyboard."""


def slugify(text):
    s = str(text).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60].rstrip("-")


def parse_time(value):
    """Parse M:SS, H:MM:SS, or plain seconds into seconds."""
    text = str(value).strip()
    if not text:
        raise ValueError("empty time")
    if ":" not in text:
        return float(text)
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    raise ValueError("bad time: {!r}".format(value))


def fmt_time(seconds, force_ms=False):
    """Format seconds as M:SS or M:SS.mmm (no leading zero on minutes)."""
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if force_ms or abs(rest - round(rest)) > 1e-9:
        return "{}:{:06.3f}".format(minutes, rest)
    return "{}:{:02d}".format(minutes, int(round(rest)))


def probe_duration(path):
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def clean_generation_prompt(prompt):
    """Drop trailing Midjourney flags; Z-Image does not use them."""
    prompt = re.sub(
        r"\s+--(?:ar|v|q|s|seed|style|niji|chaos|stylize)\b(?:\s+[^\s]+)?",
        "", prompt,
    )
    return prompt.strip()


def split_h4_sections(text):
    """Split a Step section into {heading: body}; key '' when no H4 exists."""
    sections = {}
    heading = None
    buf = []
    for line in text.splitlines():
        match = H4_RE.match(line)
        if match:
            if heading is not None:
                sections[heading] = "\n".join(buf).strip()
            heading = match.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if heading is not None:
        sections[heading] = "\n".join(buf).strip()
    if not sections:
        sections[""] = text.strip()
    return sections


def step_section(text, number):
    match = re.search(r"^###\s+Step\s+{}\b.*$".format(number), text, re.M)
    if not match:
        return ""
    rest = text[match.end():]
    nxt = re.search(r"^###\s+Step\s+{}\b.*$".format(number + 1), rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def extract_sheet_blocks(step1):
    """Return [{heading, prompt}] for every H4 + fenced block in Step 1."""
    lines = step1.splitlines()
    sheets = []
    heading = None
    i = 0
    while i < len(lines):
        match = re.match(r"^####\s+(.+?)\s*$", lines[i])
        if match:
            heading = match.group(1).strip()
            i += 1
            continue
        if heading and re.match(r"^```(?:text)?[ \t]*$", lines[i]):
            i += 1
            body = []
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            sheets.append({"heading": heading, "prompt": "\n".join(body).strip()})
            heading = None
            i += 1
            continue
        i += 1
    return sheets


def classify_sheet(heading):
    low = heading.lower()
    if "character" in low:
        return "character"
    if "environment" in low:
        return "environment"
    if "prop" in low or "entity" in low or "object" in low:
        return "prop"
    return None


def extract_any_fenced_sheets(step1):
    """Fallback A: every fenced block, heading from the nearest preceding line."""
    lines = step1.splitlines()
    sheets = []
    heading = ""
    i = 0
    while i < len(lines):
        if re.match(r"^```(?:text)?[ \t]*$", lines[i]):
            i += 1
            body = []
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            prompt = "\n".join(body).strip()
            if prompt:
                sheets.append({"heading": heading or "Reference sheet", "prompt": prompt})
            heading = ""
            i += 1
            continue
        stripped = lines[i].strip().lstrip("-*# ").strip()
        if stripped:
            heading = stripped
        i += 1
    return sheets


def extract_blockquote_sheets(step1):
    """Fallback B: contiguous blockquote blocks (one sheet per block).

    Film Director often puts the prompt in a blockquote under an H4 heading
    (`#### Environment Turnaround Sheet: ...`). Use that heading so the sheet is
    classified correctly, and drop the leading "Midjourney / Flux Prompt:" label
    so the image model receives only the prompt prose.
    """
    blocks = []
    current = []
    heading = None
    last_heading = None
    for line in step1.splitlines():
        stripped = line.strip()
        if re.match(r"^#{2,6}\s+", stripped):
            last_heading = re.sub(r"^#{2,6}\s+", "", stripped).strip()
        if line.lstrip().startswith(">"):
            if not current:
                heading = last_heading
            current.append(line.lstrip()[1:].strip())
        elif current:
            blocks.append({"heading": heading, "lines": current})
            current = []
    if current:
        blocks.append({"heading": heading, "lines": current})

    sheets = []
    for block in blocks:
        lines = [item for item in block["lines"] if item]
        if not lines:
            continue
        if re.match(r"^(midjourney|flux)\b.*prompt\s*:?$", lines[0], re.I):
            lines = lines[1:]
        prompt = "\n".join(lines).strip()
        if len(prompt) < 40:
            continue
        title = block["heading"] or (lines[0] if lines else "")
        sheets.append({"heading": title[:120], "prompt": prompt})
    return sheets


def extract_bullet_sheets(step1):
    """Fallback C: Film Director's Step 1 bullet/prose form."""
    groups = []
    current = None
    for line in step1.splitlines():
        if re.match(r"^[-*]\s+", line):
            if current:
                groups.append(current)
            current = {"heading": re.sub(r"^[-*]\s+", "", line).strip(), "lines": [line]}
        elif current is not None:
            if re.match(r"^#{1,6}\s+", line):
                groups.append(current)
                current = None
            elif line.strip():
                current["lines"].append(line)
    if current:
        groups.append(current)

    sheets = []
    for group in groups:
        heading = group["heading"]
        if classify_sheet(heading) is None:
            continue
        # Keep the model's wording verbatim; only strip the bullet markers so
        # the result reads as prose for the image model.
        prompt = " ".join(
            re.sub(r"^\s*[-*]\s*", "", part).strip()
            for part in group["lines"]
            if part.strip()
        )
        if len(prompt) >= 40:
            sheets.append({"heading": heading, "prompt": prompt})
    return sheets


def extract_sheets(step1):
    """Try the four Step 1 shapes in order; use the first that yields sheets."""
    for extractor in (
        extract_sheet_blocks,
        extract_any_fenced_sheets,
        extract_blockquote_sheets,
        extract_bullet_sheets,
    ):
        sheets = extractor(step1)
        if sheets:
            for sheet in sheets:
                sheet["extraction"] = extractor.__name__
            return sheets
    return []


def assign_sheet_files(sheets, args):
    counters = {"character": 0, "environment": 0, "prop": 0}
    provided = {
        "character": list(args.character_file),
        "environment": list(args.env_file),
        "prop": list(args.prop_file),
    }
    fallback_order = ["character", "prop", "environment"]
    character_stem = slugify(args.character_name) or "protagonist"
    for index, sheet in enumerate(sheets):
        kind = sheet.get("kind")
        if kind is None:
            kind = fallback_order[min(index, len(fallback_order) - 1)]
            sheet["kind"] = kind
        ordinal = counters[kind]
        counters[kind] += 1
        if ordinal < len(provided[kind]):
            filename = provided[kind][ordinal]
        elif kind == "character":
            suffix = "" if ordinal == 0 else "_{}".format(ordinal + 1)
            filename = "character_{}{}_front.png".format(character_stem, suffix)
        elif kind == "environment":
            filename = "env_{}.png".format(ordinal + 1)
        else:
            filename = "prop_{}.png".format(ordinal + 1)
        sheet["key_frame_file"] = filename
    return sheets


def extract_step2(step2):
    """Return (beats, audio) from Step 2."""
    sections = split_h4_sections(step2)
    beats_text = ""
    audio_text = ""
    for heading, body in sections.items():
        low = heading.lower()
        if "beat" in low:
            beats_text = body
        elif "audio" in low:
            audio_text = body
    if not beats_text and not audio_text:
        beats_text = step2

    beats = []
    for line in beats_text.splitlines():
        match = BEAT_RE.match(line)
        if match:
            beats.append({
                "start": parse_time(match.group(1)),
                "end": parse_time(match.group(2)),
                "text": match.group(3).strip(),
            })

    audio = {}
    audio_keys = ("dialogue", "foley", "room tone", "score", "music",
                  "ambience", "sound")
    for line in audio_text.splitlines():
        match = BULLET_KV_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        if any(token in key for token in audio_keys):
            audio[key] = match.group(2).strip()
    return beats, audio


def parse_ref2va(block):
    positions = []
    for label in REF2VA_LABELS:
        match = re.search(r"^{}:\s*".format(re.escape(label)), block, re.M)
        if not match:
            raise BuildError(
                "Step 3 code block is missing the {}: ref2va section".format(label)
            )
        positions.append((label, match.start(), match.end()))
    out = {}
    for i, (label, _start, body_start) in enumerate(positions):
        body_end = positions[i + 1][1] if i + 1 < len(positions) else len(block)
        body = block[body_start:body_end].strip()
        if label in LIST_SECTIONS:
            out[label] = [line.strip() for line in body.splitlines() if line.strip()]
        else:
            out[label] = body
    return out


def parse_clip_range(rest):
    start = end = duration = None
    bracket = re.search(r"\[([^\]]+)\]", rest)
    if bracket:
        parts = [part.strip() for part in bracket.group(1).split("|")]
        rng = re.match(r"([\d:.]+)\s*[-–—]\s*([\d:.]+)", parts[0])
        if rng:
            start = parse_time(rng.group(1))
            end = parse_time(rng.group(2))
        for part in parts[1:]:
            dm = re.search(r"Duration:\s*([\d.]+)\s*s", part, re.I)
            if dm:
                duration = float(dm.group(1))
    if duration is None and start is not None and end is not None:
        duration = end - start
    return start, end, duration


def clip_bullets(chunk):
    head = chunk.split("```", 1)[0]
    bullets = {}
    for line in head.splitlines():
        match = BULLET_KV_RE.match(line)
        if match:
            bullets[match.group(1).strip().lower()] = match.group(2).strip()
    return bullets


def extract_clips(step3, default_duration):
    """Return [{id, start, end, duration, bullets, ref2va}] from Step 3."""
    matches = list(CLIP_RE.finditer(step3))
    clips = []
    if matches:
        previous_end = 0.0
        for index, match in enumerate(matches):
            chunk_end = matches[index + 1].start() if index + 1 < len(matches) else len(step3)
            chunk = step3[match.start():chunk_end]
            start, end, duration = parse_clip_range(match.group(2))
            if start is None:
                start = previous_end
            if duration is None and end is not None:
                duration = end - start
            if duration is None:
                duration = default_duration or 12.0
            if end is None:
                end = start + duration
            if duration <= 0:
                raise BuildError("Clip {} has a non-positive duration".format(match.group(1)))
            blocks = [b for b in CODE_BLOCK_RE.findall(chunk)
                      if all(label + ":" in b for label in REF2VA_LABELS)]
            if not blocks:
                raise BuildError(
                    "Clip {} has no six-section ref2va code block".format(match.group(1))
                )
            clips.append({
                "id": int(match.group(1)),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "bullets": clip_bullets(chunk),
                "ref2va": parse_ref2va(blocks[0]),
            })
            previous_end = end
        return clips

    # No "#### Clip N" headings: accept every ref2va block in order.
    blocks = [b for b in CODE_BLOCK_RE.findall(step3)
              if all(label + ":" in b for label in REF2VA_LABELS)]
    if not blocks:
        raise BuildError("No Step 3 ref2va code block found in the markdown")
    start = 0.0
    for index, block in enumerate(blocks):
        duration = default_duration if len(blocks) == 1 and default_duration else 12.0
        clips.append({
            "id": index + 1,
            "start": round(start, 3),
            "end": round(start + duration, 3),
            "duration": round(duration, 3),
            "bullets": {},
            "ref2va": parse_ref2va(block),
        })
        start += duration
    return clips


def sentence_split(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def first_sentence(text):
    sentences = sentence_split(text)
    return sentences[0] if sentences else ""


def camera_from_text(text):
    low = text.lower()
    move_patterns = [
        (r"push(?:es)?[ -]in", "push-in"),
        (r"track(?:s)? right", "track right"),
        (r"track(?:s)? left", "track left"),
        (r"pan(?:s)? right", "pan right"),
        (r"pan(?:s)? left", "pan left"),
        (r"tilt(?:s)? (?:up|down)", "tilt"),
        (r"orbit(?:s)?", "orbit"),
        (r"dolly(?:s)?", "dolly"),
        (r"zoom(?:s)?", "zoom"),
        (r"crane(?:s)?", "crane"),
        (r"handheld", "handheld"),
        (r"whip pan", "whip pan"),
        (r"static", "static"),
    ]
    moves = []
    for pattern, label in move_patterns:
        if re.search(pattern, low) and label not in moves:
            moves.append(label)

    sizes = []
    for term in ["extreme wide", "medium close-up", "close-up", "full body",
                 "two-shot", "wide", "medium", "profile"]:
        if term in low and not any(term in found for found in sizes):
            sizes.append(term)

    angles = []
    if "side profile" in low or "profile" in low:
        angles.append("side profile")
    for term in ["low angle", "high angle", "dutch angle", "overhead",
                 "bird's-eye", "worm's-eye", "eye level", "pov"]:
        if term in low and term not in angles:
            angles.append(term)

    notes = " ".join(
        sentence for sentence in sentence_split(text)
        if "camera" in sentence.lower() or "[shot" in sentence.lower()
    )
    return {
        "angle": ", ".join(angles) or "not specified",
        "size": ", ".join(sizes) or "not specified",
        "move": ", ".join(moves) or "static",
        "notes": notes[:600] if notes else "No camera movement stated in the model output.",
    }


def extract_outfit(text):
    match = re.search(
        r"wearing\s+(.+?)(?:\.|,\s*mapped to|\s*$)", text, re.I | re.S
    )
    return match.group(1).strip().rstrip(",") if match else ""


def extract_palette(text):
    low = text.lower()
    return [color for color in COLOR_WORDS
            if re.search(r"\b{}\b".format(re.escape(color)), low)]


def is_character_line(line):
    low = line.lower()
    return any(re.search(r"\b{}\b".format(word.strip()), low) for word in CHARACTER_WORDS)


def is_environment_line(line):
    low = line.lower()
    return any(re.search(r"\b{}\b".format(word), low) for word in ENVIRONMENT_WORDS)


def strip_reference_mapping(line):
    """Drop 'mapped to <Picture N>.' from a derived subject description."""
    return re.sub(
        r",?\s*mapped to <(?:Picture|Video|Audio) \d+>\.?\s*$", "", line
    ).strip()


def cut_type_from_transitions(head, tail):
    low = (head + " " + tail).lower()
    for token, value in [
        ("j-cut", "j-cut"), ("l-cut", "l-cut"), ("match cut", "match-cut"),
        ("whip pan", "whip-pan"), ("action cut", "action-cut"),
        ("cutaway", "cutaway"),
    ]:
        if token in low:
            return value
    return "straight-cut"


def parse_head_tail(value):
    if not value:
        return "", ""
    match = re.match(r"Head:\s*(.*?)\s*\|\s*Tail:\s*(.*)", value, re.I)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return value.strip(), ""


def snap_h3_duration(seconds, fps=24.0, cap=15.0):
    """Largest H3-valid length (frames % 17 == 5) at or below the target."""
    target = min(float(seconds), cap)
    max_frames = int(target * fps + 1e-9)
    frames = max_frames - ((max_frames - 5) % 17)
    if frames < 5:
        return 0.0
    return round(frames / fps, 3)


def deep_merge(base, override):
    """Recursive merge; list items with matching id/name/role merge in place."""
    if isinstance(base, dict) and isinstance(override, dict):
        for key, value in override.items():
            if key in base:
                base[key] = deep_merge(base[key], value)
            else:
                base[key] = value
        return base
    if isinstance(base, list) and isinstance(override, list):
        if all(isinstance(item, dict) for item in override) and base:
            result = [deep_merge(dict(item), {}) for item in base]
            for index, item in enumerate(override):
                target = None
                for key in ("id", "name", "role", "key_frame_file"):
                    if key in item:
                        for candidate_index, candidate in enumerate(result):
                            if candidate.get(key) == item[key]:
                                target = candidate_index
                                break
                    if target is not None:
                        break
                if target is None:
                    if index < len(result):
                        target = index
                    else:
                        result.append(item)
                        continue
                result[target] = deep_merge(result[target], item)
            return result
        return override
    return override


def build(args):
    md_path = Path(args.md)
    text = md_path.read_text(encoding="utf-8")

    title = args.title or ""
    if not title:
        match = re.search(r"^#\s+(.+?)\s*$", text, re.M)
        title = match.group(1).strip() if match else ""
    slug = args.slug or slugify(title) or slugify(md_path.stem)
    title = title or slug

    provenance = {}
    for line in text.splitlines():
        match = re.match(r"^>\s*([^:]+):\s*(.*)$", line)
        if match:
            provenance[match.group(1).strip().lower()] = match.group(2).strip()

    audio_filename = Path(args.audio).name if args.audio else ""
    header_duration = None
    input_value = provenance.get("input", "")
    input_match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", input_value)
    if input_match:
        if not audio_filename:
            audio_filename = Path(input_match.group(1).strip()).name
        try:
            header_duration = parse_time(input_match.group(2))
        except ValueError:
            header_duration = None

    track_duration = args.duration
    if track_duration is None and args.audio:
        track_duration = probe_duration(args.audio)
        if track_duration is None:
            print(
                "WARNING: could not probe {}; falling back to the markdown Input "
                "duration".format(args.audio), file=sys.stderr,
            )
    if track_duration is None:
        track_duration = header_duration

    step1 = step_section(text, 1)
    step2 = step_section(text, 2)
    step3 = step_section(text, 3)

    sheets = extract_sheets(step1)
    for sheet in sheets:
        sheet["kind"] = classify_sheet(sheet["heading"])
        sheet["prompt"] = clean_generation_prompt(sheet["prompt"])
    sheets = assign_sheet_files(sheets, args)

    beats, audio = extract_step2(step2)
    clips = extract_clips(step3, track_duration)

    # Duration coverage: extend the last segment to a valid H3 length when the
    # mix would otherwise cut the track short (opt out with --no-extend-last).
    extension_note = None
    if args.extend_last and track_duration and clips:
        last = clips[-1]
        if last["end"] + 0.001 < track_duration:
            available = track_duration - last["start"]
            new_duration = snap_h3_duration(available, args.fps)
            if new_duration > last["duration"] + 0.001:
                extension_note = (
                    "The final segment was extended from {:.3f} s to {:.3f} s "
                    "({} frames at {} fps, a valid H3 length) to cover the {:.3f} s track."
                ).format(
                    last["duration"], new_duration,
                    int(round(new_duration * args.fps)), args.fps, track_duration,
                )
                last["duration"] = new_duration
                last["end"] = round(last["start"] + new_duration, 3)
                last["timecode"] = "{}-{}".format(
                    fmt_time(last["start"]), fmt_time(last["end"])
                )

    first = clips[0]
    first_ref2va = first["ref2va"]
    all_text = text
    no_lipsync = bool(re.search(
        r"no\s+lip[- ]?sync|lip[- ]?sync|mouth stays closed|lips remain closed",
        all_text, re.I,
    ))

    subject_lines = [line for line in first_ref2va["subject_definitions"]
                     if re.match(r"<Subject\s+\d+>", line, re.I)]
    picture_lines = [line for line in first_ref2va["subject_definitions"]
                     if re.match(r"<Picture\s+\d+>", line, re.I)]
    character_lines = [line for line in subject_lines if is_character_line(line)]
    environment_lines = [line for line in subject_lines if is_environment_line(line)]
    world_rules = environment_lines + [
        line for line in picture_lines
        if is_environment_line(line) and not is_character_line(line)
    ]

    character_files = [s["key_frame_file"] for s in sheets if s["kind"] == "character"]
    environment_files = [s["key_frame_file"] for s in sheets if s["kind"] == "environment"]
    prop_files = [s["key_frame_file"] for s in sheets if s["kind"] == "prop"]

    character_description = (
        strip_reference_mapping(character_lines[0]) if character_lines
        else "{}: the subject described by the reference sheets.".format(args.character_name)
    )
    outfit = extract_outfit(character_description)
    visual_style = first_sentence(first_ref2va["detailed_description"])
    palette = extract_palette(text)

    character_sheets = []
    for index, sheet in enumerate(s for s in sheets if s["kind"] == "character"):
        role = args.character_name if index == 0 else "{} {}".format(args.character_name, index + 1)
        character_sheets.append({
            "role": role,
            "generation_prompt": sheet["prompt"],
            "key_frame_file": sheet["key_frame_file"],
            "views": ["front", "3/4", "side", "back"],
            "source": "generated",
            "notes": "Extracted from Step 1: {} ({})".format(
                sheet["heading"], sheet.get("extraction", "extract_sheet_blocks")),
        })
    environment_sheets = [{
        "name": sheet["heading"],
        "generation_prompt": sheet["prompt"],
        "key_frame_file": sheet["key_frame_file"],
        "source": "generated",
        "notes": "Extracted from Step 1: {} ({})".format(
            sheet["heading"], sheet.get("extraction", "extract_sheet_blocks")),
    } for sheet in sheets if sheet["kind"] == "environment"]
    prop_sheets = [{
        "name": sheet["heading"],
        "generation_prompt": sheet["prompt"],
        "key_frame_file": sheet["key_frame_file"],
        "source": "generated",
        "notes": "Extracted from Step 1: {} ({})".format(
            sheet["heading"], sheet.get("extraction", "extract_sheet_blocks")),
    } for sheet in sheets if sheet["kind"] == "prop"]

    reference_image = character_files[0] if character_files else None
    environment_name = environment_sheets[0]["name"] if environment_sheets else "the established location"

    storyboard = {
        "project": {
            "title": title,
            "slug": slug,
            "source": args.source_type,
            "concept": "{}{}".format(
                title,
                ": " + (beats[0]["text"] if beats else first_sentence(first_ref2va["detailed_description"])),
            )[:500],
            "genre": (
                "Cinematic ballad music video" if "ballad" in all_text.lower()
                else "Cinematic music video" if "music video" in all_text.lower()
                else "Cinematic video"
            ),
            "visual_style": visual_style,
            "mood": (
                "Melancholic, atmospheric" if "melanchol" in all_text.lower()
                else "Cinematic, atmospheric"
            ),
            "target_duration_seconds": round(
                track_duration if track_duration else clips[-1]["end"], 3
            ),
            "aspect_ratio": args.aspect_ratio,
            "generation_strategy": (
                "one-continuous-shot" if len(clips) == 1 else "stitched-segments"
            ),
            "segments_count": len(clips),
            "reference_image": reference_image,
            "primary_objective": (
                "Lock the reference sheets across {} H3 segment(s), keep the "
                "model's ref2va wording intact, then mix the original soundtrack "
                "over the final cut.".format(len(clips))
            ),
            "audio_filename": audio_filename or None,
        },
        "subject_continuity": {
            "characters": [{
                "name": args.character_name,
                "description": character_description,
                "consistency_notes": [
                    "Identity and wardrobe are locked to `{}`.".format(character_files[0])
                    if character_files else "Identity is locked by the reference sheet.",
                ] + ([
                    "Wardrobe: {}.".format(outfit.rstrip("."))
                ] if outfit else []) + ([
                    "Lips remain closed; no lip-sync."
                ] if no_lipsync else []),
            }],
            "style_lock": visual_style,
            "palette": palette,
            "world_rules": world_rules + [
                "Keep the same location, wardrobe, and light direction across all segments.",
            ],
        },
        "references": {
            "inventory": {
                "character_count": len(character_sheets),
                "prop_count": len(prop_sheets),
                "location_count": len(environment_sheets),
            },
            "character_sheets": character_sheets,
            "environment_sheets": environment_sheets,
            "prop_sheets": prop_sheets,
        },
        "segments": [],
        "continuity_requirements": {
            "character_identity": [character_description],
            "costume_and_accessories": ([
                "Wardrobe: {}.".format(outfit.rstrip("."))
            ] if outfit else []),
            "anatomy_and_motion": [
                "Stable human anatomy with natural proportions and five fingers per hand."
            ],
            "lighting_and_environment": (
                world_rules or ["Maintain a consistent lighting direction and set dressing."]
            ),
            "object_continuity": [
                "{} stays consistent across every cut.".format(sheet["name"])
                for sheet in prop_sheets
            ],
            "camera_continuity": [
                "Each segment cuts on a contrasting composition; never feed the "
                "last frame of one segment into the next as a first frame."
            ],
        },
        "quality_priorities": [],
        "assumptions_and_defaults": [],
        "open_questions": [],
    }

    if sheets:
        manifest = []
        for sheet in character_sheets:
            manifest.append({
                "subject": sheet["role"],
                "reference_file": sheet["key_frame_file"],
                "segment_ids": [clip["id"] for clip in clips],
                "weight": "high",
                "notes": "Lock face, hair, and wardrobe for every segment.",
            })
        for sheet in environment_sheets:
            manifest.append({
                "subject": sheet["name"],
                "reference_file": sheet["key_frame_file"],
                "segment_ids": [clip["id"] for clip in clips],
                "weight": "medium",
                "notes": "Lock set dressing, palette, and light direction.",
            })
        for sheet in prop_sheets:
            manifest.append({
                "subject": sheet["name"],
                "reference_file": sheet["key_frame_file"],
                "segment_ids": [clip["id"] for clip in clips],
                "weight": "low",
                "notes": "Lock the prop's shape and surface detail.",
            })
        storyboard["continuity_manifest"] = manifest

    for clip in clips:
        ref2va = clip["ref2va"]
        bullets = clip["bullets"]
        matching_beats = [
            beat for beat in beats
            if beat["end"] > clip["start"] and beat["start"] < clip["end"]
        ] or beats
        if not matching_beats:
            matching_beats = [{
                "start": clip["start"],
                "end": clip["end"],
                "text": first_sentence(ref2va["detailed_description"]),
            }]
        action = " ".join(beat["text"] for beat in matching_beats).strip()
        head, tail = parse_head_tail(
            bullets.get("head/tail transitions", bullets.get("transitions", ""))
        )
        transition_in = head or "Hard cut"
        transition_out = tail or "Hard cut"
        cut_type = cut_type_from_transitions(transition_in, transition_out)
        sound_parts = [
            value.rstrip(". ") for key, value in audio.items()
            if "foley" in key or "room tone" in key
        ]
        sound_cue = "; ".join(sound_parts) or ref2va["overall_soundscape"]

        segment_beats = [{
            "time_offset": fmt_time(max(0.0, beat["start"] - clip["start"]), force_ms=True),
            "location_or_event": environment_name,
            "action": beat["text"],
            "outfit": outfit or "same outfit as the character reference sheet",
        } for beat in matching_beats]

        storyboard["segments"].append({
            "id": clip["id"],
            "timecode": "{}-{}".format(
                fmt_time(clip["start"]), fmt_time(clip["end"])
            ),
            "start": clip["start"],
            "end": clip["end"],
            "duration": clip["duration"],
            "narrative_purpose": bullets.get(
                "clips & context", bullets.get("context", action)
            ),
            "action": action,
            "character_blocking": action,
            "camera": camera_from_text(ref2va["detailed_description"]),
            "motion": action,
            "secondary_motion": (
                "Environment, fabric, and atmospheric motion follow the action "
                "throughout the shot."
            ),
            "lighting": (
                "Maintain the light direction and palette established by the "
                "environment reference sheet."
            ),
            "transition_in": transition_in,
            "transition_out": transition_out,
            "cut": {
                "type": cut_type,
                "description": "Opens with {} and closes with {}.".format(
                    transition_in.lower(), transition_out.lower()
                ),
                "audio_overlap_seconds": None,
                "composition_plan": {
                    "opens_on": (
                        "N/A - first segment" if clip["id"] == clips[0]["id"]
                        else transition_in
                    ),
                    "ends_on": (
                        "N/A - final segment" if clip["id"] == clips[-1]["id"]
                        else transition_out
                    ),
                },
            },
            "sound_cue": sound_cue,
            "focus_hierarchy": [
                "Primary: {}".format(args.character_name),
                "Secondary: {} and the immediate set dressing.".format(environment_name),
                "Background: the wider location in soft focus.",
            ],
            "reference_image": reference_image,
            "beats": segment_beats,
            "ref2va": ref2va,
        })

    priorities = []
    if character_sheets:
        priorities.append((
            "Character identity and wardrobe continuity",
            "The subject matches the turnaround sheet in every segment; wardrobe never changes.",
        ))
    if no_lipsync:
        priorities.append((
            "No lip-sync / closed mouth",
            "Lips stay closed for the entire video; the performance is carried by gaze and posture.",
        ))
    if environment_sheets or prop_sheets:
        priorities.append((
            "Environment and prop continuity",
            "Set dressing, palette, light direction, and prop details stay identical across cuts.",
        ))
    priorities.append((
        "Shot-to-shot continuity",
        "Each cut lands on a contrasting composition and preserves screen direction.",
    ))
    priorities.append((
        "Audio sync to the original soundtrack",
        "Segment starts and durations cover the track without cutting the music short.",
    ))
    storyboard["quality_priorities"] = [{
        "priority": index + 1,
        "objective": objective,
        "success_criteria": criteria,
    } for index, (objective, criteria) in enumerate(priorities)]

    storyboard["assumptions_and_defaults"] = [
        "Storyboard body extracted verbatim from {} (title: {}); only formatting was normalized into JSON fields.".format(md_path.name, title),
        "Reference-sheet prompts are the raw Step 1 prompts; refine them with --overrides for Z-Image-specific prose.",
        "Auto-filled project, camera, continuity, and quality fields are generic; supply --overrides for run-specific authored wording.",
        "Reference sheets render at 1920x1080 (16:9); H3 crops them to {} at render time.".format(args.aspect_ratio),
        "Final audio is the original soundtrack only; the H3 vocal/foley layer is discarded (stitch_and_mix.py default).",
    ]
    if audio_filename:
        storyboard["assumptions_and_defaults"].append(
            "Target duration comes from {} ({} s).".format(audio_filename, track_duration)
        )
    if sheets:
        storyboard["assumptions_and_defaults"].append(
            "Step 1 sheets extracted with {}.".format(
                sheets[0].get("extraction", "extract_sheet_blocks"))
        )
    if extension_note:
        storyboard["assumptions_and_defaults"].append(extension_note)
    if args.overrides:
        storyboard["assumptions_and_defaults"].append(
            "Overrides applied from {}.".format(args.overrides)
        )

    if args.overrides:
        overrides_path = Path(args.overrides)
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BuildError("cannot read overrides {}: {}".format(overrides_path, exc))
        if not isinstance(overrides, dict):
            raise BuildError("overrides must be a JSON object")
        storyboard = deep_merge(storyboard, overrides)

    return storyboard


def validate(storyboard):
    missing = [key for key in REQUIRED_TOP if key not in storyboard]
    if missing:
        raise BuildError("missing top-level keys: {}".format(", ".join(missing)))
    if not storyboard["segments"]:
        raise BuildError("storyboard has no segments")
    for segment in storyboard["segments"]:
        missing = [key for key in REQUIRED_SEGMENT if key not in segment]
        if missing:
            raise BuildError(
                "segment {} is missing: {}".format(segment.get("id"), ", ".join(missing))
            )
        missing = [label for label in REF2VA_LABELS if label not in segment["ref2va"]]
        if missing:
            raise BuildError(
                "segment {} ref2va is missing: {}".format(
                    segment.get("id"), ", ".join(missing)
                )
            )
        if "type" not in segment["cut"] or "description" not in segment["cut"]:
            raise BuildError("segment {} cut needs type and description".format(segment.get("id")))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a storyboard JSON blueprint from an AI Studio markdown storyboard."
    )
    parser.add_argument("--md", required=True, help="finalized storyboard markdown")
    parser.add_argument("--out", help="output JSON (default: <md-stem>-storyboard.json)")
    parser.add_argument("--slug", help="asset slug (default: title or md stem)")
    parser.add_argument("--title", help="override the markdown H1 title")
    parser.add_argument("--audio", help="soundtrack path; enables duration probing")
    parser.add_argument("--duration", type=float, help="track duration override in seconds")
    parser.add_argument("--aspect-ratio", default="9:16", help="target video aspect (default: 9:16)")
    parser.add_argument(
        "--source-type", default="prompt",
        choices=["idea", "prompt", "image", "video-analysis"],
    )
    parser.add_argument("--character-name", default="Protagonist")
    parser.add_argument("--character-file", action="append", default=[],
                        help="character sheet filename (repeatable, in Step 1 order)")
    parser.add_argument("--env-file", action="append", default=[],
                        help="environment sheet filename (repeatable, in Step 1 order)")
    parser.add_argument("--prop-file", action="append", default=[],
                        help="prop sheet filename (repeatable, in Step 1 order)")
    parser.add_argument("--overrides", help="JSON file deep-merged over the derived storyboard")
    parser.add_argument("--extend-last", dest="extend_last", action="store_true", default=True)
    parser.add_argument("--no-extend-last", dest="extend_last", action="store_false",
                        help="keep the model's clip durations even if the track runs longer")
    parser.add_argument("--fps", type=float, default=24.0, help="H3 frame rate (default: 24)")
    args = parser.parse_args(argv)

    try:
        storyboard = build(args)
        validate(storyboard)
    except (BuildError, ValueError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else Path(args.md).with_name(
        Path(args.md).stem + "-storyboard.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(storyboard, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    refs = storyboard.get("references", {})
    sheets = sum(len(refs.get(key, [])) for key in (
        "character_sheets", "environment_sheets", "prop_sheets"
    ))
    print(
        "wrote {} ({} segment(s), {} sheet(s), {:.3f} s track)".format(
            out, len(storyboard["segments"]), sheets,
            storyboard["project"]["target_duration_seconds"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
