#!/usr/bin/env python3
"""Decode a browser_evaluate dump of the 1st AI Studio response and write the storyboard .md.

browser_evaluate with `filename=` saves the returned string as a JSON-encoded
quoted string, so this script json-decodes it, prepends a provenance header, and
writes the final markdown. It refuses to write an obviously truncated capture.

Usage:
    # Fully automatic title + provenance (audio filename and duration)
    python3 finalize_markdown.py --in aistudio_response_md.txt \
        --audio /path/to/999doahong.mp3 \
        --model "Gemini 3.8 Flash" \
        --thinking high \
        --out 999doahong.md

    # Manual header (original behavior)
    python3 finalize_markdown.py --in aistudio_response_md.txt \
        --out the-moonlit-promise-and-loss.md \
        --title "The Moonlit Promise & Loss" \
        --source "Source: <model> - Google AI Studio (Temporary chat)" \
        --source "Input: <filename> (<duration>)" \
        --source 'Prompt: "<prompt sent>"' \
        --source "AI Studio response: 1st" \
        --source "System instructions preset: Film Director"

With --audio, the title defaults to the slugified audio filename and the
boilerplate provenance lines are generated (Input duration via ffprobe); pass
--thinking to record the Thinking Level after the preset line. Pass --title or
--source to override any of them. Without --audio, --title is required and only
the supplied --source lines are written.

Exit codes: 0 ok, 1 unreadable/truncated capture or missing audio duration.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MIN_CHARS = 200
CREATIVE_ASK = "give me a good script for this soundtrack"


def slugify(title: str) -> str:
    s = title.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60].rstrip("-")


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if abs(rest - round(rest)) < 1e-9:
        return "{}:{:02d}".format(minutes, int(round(rest)))
    return "{}:{:06.3f}".format(minutes, rest)


def probe_duration(path: Path):
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


def build_source_lines(args, audio_name, audio_duration):
    """Auto-generate provenance lines, then append any manual --source lines."""
    lines = []
    if args.model:
        lines.append(
            "Source: {} — Google AI Studio (Temporary chat)".format(args.model)
        )
    if audio_name:
        if audio_duration is None:
            lines.append("Input: {}".format(audio_name))
        else:
            lines.append(
                "Input: {} ({})".format(audio_name, format_duration(audio_duration))
            )
    if args.audio:
        # Provenance must stay one blockquote line even when the ask has breaks.
        prompt_line = " ".join(str(args.prompt).split())
        lines.append('Prompt: "{}"'.format(prompt_line))
        lines.append("AI Studio response: {}".format(args.response))
        lines.append("System instructions preset: {}".format(args.preset))
        if args.thinking:
            lines.append("Thinking level: {}".format(str(args.thinking).capitalize()))
    lines.extend(args.source)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="JSON dump from browser_evaluate")
    ap.add_argument("--out", help="output .md path (default: <slug>.md)")
    ap.add_argument("--title", help="title (required without --audio)")
    ap.add_argument("--source", action="append", default=[], help="extra provenance line (repeatable)")
    ap.add_argument("--audio", help="soundtrack path; derives title, filename, and duration")
    ap.add_argument("--duration", type=float, help="audio duration override in seconds")
    ap.add_argument("--model", help='model name for the Source line, e.g. "Gemini 3.8 Flash"')
    ap.add_argument("--prompt", default=CREATIVE_ASK, help="creative ask sent to AI Studio")
    ap.add_argument("--response", default="1st", help="response number (always 1st in this pipeline)")
    ap.add_argument("--preset", default="Film Director", help="system-instructions preset")
    ap.add_argument("--thinking", help="AI Studio Thinking Level used (adds a provenance line)")
    args = ap.parse_args()

    if not args.title and not args.audio:
        ap.error("--title is required unless --audio is given")

    audio_path = Path(args.audio) if args.audio else None
    audio_name = audio_path.name if audio_path else None
    audio_duration = args.duration
    if audio_path:
        if not audio_path.exists():
            print("ERROR: audio file not found: {}".format(audio_path), file=sys.stderr)
            return 1
        if audio_duration is None:
            audio_duration = probe_duration(audio_path)
        if audio_duration is None:
            print(
                "ERROR: cannot determine duration for {}. Install ffprobe or pass "
                "--duration.".format(audio_path),
                file=sys.stderr,
            )
            return 1

    title = args.title or slugify(audio_path.stem)

    raw = open(args.inp, encoding="utf-8").read().strip()
    text = json.loads(raw)  # raises on a non-JSON dump: that is a real error, surface it

    if not isinstance(text, str) or len(text) < MIN_CHARS:
        print(
            "ERROR: capture is empty or truncated ({} chars). Re-run "
            "browser_evaluate with extract_markdown.js.".format(
                len(text) if isinstance(text, str) else 0
            ),
            file=sys.stderr,
        )
        return 1

    if text.count("```") % 2:
        print("ERROR: unbalanced code fences -- capture is truncated. Re-extract.", file=sys.stderr)
        return 1

    # Sanity-check that this really is a Film Director storyboard, not the wrong turn.
    # Step 3 has used two formats: the older integrated_multimodal_description block
    # and the six-part Ref2VA block whose prompt field is detailed_description.
    prompt_fields = ("integrated_multimodal_description", "detailed_description")
    if not any(field in text for field in prompt_fields):
        print(
            "ERROR: no integrated_multimodal_description or detailed_description found "
            "-- this does not look like Film Director output (wrong turn or wrong "
            "preset; did you extract a later response instead of the 1st?). "
            "Refresh the page and rerun the flow.",
            file=sys.stderr,
        )
        return 1
    if "non_diegetic_music" not in text:
        print("WARNING: no non_diegetic_music field -- output may be truncated.", file=sys.stderr)

    out = args.out or slugify(title) + ".md"
    header = ["# " + title, ""]
    source_lines = build_source_lines(args, audio_name, audio_duration)
    if source_lines:
        header += ["> " + line for line in source_lines] + [""]
    header += ["---", ""]

    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header) + "\n" + text.rstrip() + "\n")

    clips = len(re.findall(r"^#{3,4}\s*Clip\b", text, re.M))
    prompts = sum(text.count(field + ":") for field in prompt_fields)
    if prompts != clips:
        print(
            "WARNING: {} clip headings but {} prompts -- check for a missing clip.".format(
                clips, prompts
            ),
            file=sys.stderr,
        )
    print("{} ({} chars, {} clip headings, {} prompts)".format(out, len(text), clips, prompts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
