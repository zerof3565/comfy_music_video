#!/usr/bin/env python3
"""Render each storyboard segment through the Minimax H3 workflow.

Prompts are read from the storyboard JSON (one `ref2va` dict per segment, in
segment order), so you only edit the storyboard — not this script. It sets the
prompt, segment duration, aspect ratio, the reference-image LoadImage nodes,
their <Picture N> wires, the audio window, and the SaveVideo filename prefix per
segment, then saves each mp4 to the output directory.

Usage:
    # Canonical paths; slug/audio/refs/prefixes derive from the storyboard JSON
    python3 -I render_h3.py --sb outputs/<slug>-storyboard.json

    # Validate everything without touching ComfyUI
    python3 -I render_h3.py --sb outputs/<slug>-storyboard.json --dry-run

    # Write each resolved workflow graph for inspection
    python3 -I render_h3.py --sb outputs/<slug>-storyboard.json --dry-run \
        --dump-graph /tmp/h3_graphs

    # Explicit overrides
    python3 -I render_h3.py --sb outputs/<slug>-storyboard.json \
        --audio <track>.mp3 --aspect 9:16 \
        --ref 153=character_front.png --ref 154=env.png \
        --slug <slug> --trim-duration 20

    # Long track: start the storyboard 90 s into the song and use the rendered
    # timeline for each segment's trim start (clip headings may restart at 00:00)
    python3 -I render_h3.py --sb outputs/<slug>-storyboard.json \
        --audio-offset 90 --audio-start-mode cumulative

Gotchas baked in:
  - Reference sheets must be staged in ComfyUI input/ first (render_sheets.py does this).
  - Aspect is node 7893: False = 9:16, True = 16:9. It defaults to the JSON's
    project.aspect_ratio; --aspect overrides it. Do NOT edit resolution (6073/6074);
    the workflow's 6074 sets the final render size (currently 896x1568).
  - The prompt node is 6009; the duration node is 6014 (seconds).
  - References are ordered first-character, first-environment, first-prop, then
    the remaining characters/environments/props (deduplicated). Nodes 153-156
    hold the first four and are wired to ref_image_0..3 in minimax_h3_api.json;
    each extra reference gets an auto-created LoadImage node 9001, 9002, ... wired
    to ref_image_4, ref_image_5, ... Unused ref_image_N wires are pruned so the
    <Picture N> labels match the rendered graph. --ref-image-size match|max sets
    node 7518's ref_image_size ("match" keeps source pixels; "max" resizes up).
    The order maps to <Picture N> tokens: 153 -> <Picture 1>, 154 -> <Picture 2>,
    etc. Cite character-only sheets inside <Subject N>, not as standalone
    <Picture N> lines.
  - **Audio**: Node 7909 (LoadAudioPlus "Load Music File") loads the soundtrack from ComfyUI input/.
    Set AUDIO below; this script writes both `audio` and `file` on the node and auto-copies
    the source into ComfyUI input/ if it is missing or newer.
  - **Audio trim**: Node 7895 (TrimAudioDuration "Music Start Index") — set per segment:
      * start_index = --audio-offset + segment["start"], or --audio-offset +
        cumulative previous durations with --audio-start-mode cumulative
      * duration = --trim-duration (default 20s; the workflow trims the audio latent to this length)
  - **Long tracks**: pass the same --audio-offset to stitch_and_mix.py so the
    final soundtrack starts at the same point as the H3 windows.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILL_DIR.parents[2]
DEFAULT_WF = str(SKILL_DIR / "minimax_h3_api.json")
DEFAULT_OUT_DIR = str(REPO_ROOT / "outputs")
DEFAULT_COMFY_INPUT = str(Path.home() / "Documents" / "comfyui" / "input")
DEFAULT_API = "http://127.0.0.1:8188"

# The six ref2va sections, in the exact order the skill requires.
SECTIONS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

# Node ids in minimax_h3_api.json.
PROMPT_NODE = "6009"
DURATION_NODE = "6014"
ASPECT_NODE = "7893"       # false = 9:16, true = 16:9
AUDIO_NODE = "7909"
TRIM_NODE = "7895"
SAVE_NODE = "447"

# Reference wiring: the workflow bakes ref_image_0..3 into these LoadImage
# nodes; additional references get auto-created LoadImage nodes 9001, 9002, ...
LOAD_NODES = ["153", "154", "155", "156"]
FIRST_EXTRA_NODE = 9001


def post(api, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        api + path, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read().decode())


def probe_duration(path):
    """Return the media duration in seconds, or None if ffprobe cannot read it."""
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


def segment_start_indexes(segments, mode, offset):
    """Resolve each segment's soundtrack trim start.

    storyboard: trust the JSON's `start` fields (relative to the track).
    cumulative: sum the previous segment durations (the rendered timeline).
    offset: global seek into the soundtrack, added to every segment.
    """
    indexes = []
    cumulative = 0.0
    for segment in segments:
        if mode == "cumulative":
            start = cumulative
        else:
            start = float(segment.get("start", 0.0) or 0.0)
        indexes.append(round(offset + start, 3))
        cumulative += float(segment.get("duration", 0.0) or 0.0)
    return indexes


def section_text(value):
    """Join list fields (subject_definitions, retention_analysis) with newlines."""
    if isinstance(value, list):
        return "\n".join(value)
    return value


def build_prompt(segment):
    return "\n\n".join(
        "{}:\n{}".format(section, section_text(segment["ref2va"][section]))
        for section in SECTIONS
    ).strip() + "\n"


def derive_slug(sb_path):
    stem = Path(sb_path).stem
    if stem.endswith("-storyboard"):
        stem = stem[: -len("-storyboard")]
    return stem


def flatten_references(sb):
    refs = sb.get("references", {})
    return (
        [sheet["key_frame_file"] for sheet in refs.get("character_sheets", [])
         if sheet.get("key_frame_file")],
        [sheet["key_frame_file"] for sheet in refs.get("environment_sheets", [])
         if sheet.get("key_frame_file")],
        [sheet["key_frame_file"] for sheet in refs.get("prop_sheets", [])
         if sheet.get("key_frame_file")],
    )


def ordered_references(sb):
    """Return sheet filenames in the documented primary order, without duplicates.

    The first character, environment, and prop occupy the baked slots, then any
    remaining sheets follow in Step 1 category order. Extra references are wired
    to auto-created LoadImage nodes 9001+.
    """
    characters, environments, props = flatten_references(sb)
    ordered = []
    for group in (characters, environments, props):
        if group:
            ordered.append(group[0])
    for group in (characters[1:], environments[1:], props[1:]):
        for filename in group:
            if filename not in ordered:
                ordered.append(filename)
    return ordered


def ref_node_index(node):
    """Map a LoadImage node id to its zero-based reference index."""
    number = int(node)
    if number in (153, 154, 155, 156):
        return number - 153
    if number >= FIRST_EXTRA_NODE:
        return len(LOAD_NODES) + (number - FIRST_EXTRA_NODE)
    raise SystemExit(
        "--ref node must be 153-156 or {}+ (got {})".format(FIRST_EXTRA_NODE, node)
    )


def ref_node_id(index):
    if index < len(LOAD_NODES):
        return LOAD_NODES[index]
    return str(FIRST_EXTRA_NODE + index - len(LOAD_NODES))


def parse_ref_overrides(values):
    overrides = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--ref must be NODE=FILE (got {!r})".format(value))
        node, filename = value.split("=", 1)
        node = node.strip()
        if not node.isdigit():
            raise SystemExit("--ref node must be numeric (got {!r})".format(node))
        overrides[node] = filename.strip()
    return overrides


def resolve_refs(sb, overrides):
    """Apply --ref overrides to the auto-derived list; keep indices contiguous."""
    refs = ordered_references(sb)
    for node, filename in overrides.items():
        index = ref_node_index(node)
        while len(refs) <= index:
            refs.append(None)
        refs[index] = filename
    missing = [ref_node_id(index) for index, ref in enumerate(refs) if ref is None]
    if missing:
        raise SystemExit(
            "--ref nodes must be contiguous; missing {}".format(", ".join(missing))
        )
    return refs


def resolve_aspect(sb, aspect_arg):
    if aspect_arg:
        return aspect_arg
    aspect = sb.get("project", {}).get("aspect_ratio", "9:16")
    return aspect if aspect in ("9:16", "16:9") else "9:16"


def resolve_audio(args, sb_path, out_dir, slug):
    audio_name = args.audio
    source = Path(args.audio_source) if args.audio_source else None
    if audio_name and (os.sep in audio_name or (os.altsep and os.altsep in audio_name)):
        source = Path(audio_name)
        audio_name = source.name
    audio_name = audio_name or "{}.mp3".format(slug)
    if source is None:
        candidates = [
            Path(out_dir) / audio_name,
            Path(sb_path).parent / audio_name,
            Path.cwd() / audio_name,
        ]
        source = next((path for path in candidates if path.exists()), candidates[0])
    return audio_name, source


def stage_audio(source, comfy_input, audio_name, dry_run):
    dest = Path(comfy_input) / audio_name
    if dry_run:
        return dest
    os.makedirs(comfy_input, exist_ok=True)
    if source.exists() and (not dest.exists() or source.stat().st_mtime > dest.stat().st_mtime):
        shutil.copy2(source, dest)
        print("[audio] staged {} -> {}".format(source, dest))
    if not dest.exists():
        raise SystemExit(
            "AUDIO NOT FOUND: {}\nCopy the soundtrack to {} or pass --audio-source.".format(
                source, dest
            )
        )
    return dest


def build_segment_graph(segment, prefix, refs, aspect, ref_image_size,
                        workflow_path):
    """Return the H3 graph for one segment with prompt/refs/duration applied."""
    with open(workflow_path, encoding="utf-8") as handle:
        graph = json.load(handle)
    graph[PROMPT_NODE]["inputs"]["value"] = build_prompt(segment)
    graph[DURATION_NODE]["inputs"]["value"] = segment["duration"]
    graph[ASPECT_NODE]["inputs"]["value"] = aspect == "16:9"
    graph["7518"]["inputs"]["ref_image_size"] = ref_image_size

    # Drop baked ref wires the caller does not use, so <Picture N> labels match.
    for key in list(graph["7518"]["inputs"]):
        if key.startswith("ref_images.ref_image_"):
            index = int(key.rsplit("_", 1)[1])
            if index >= len(refs):
                del graph["7518"]["inputs"][key]

    for index, filename in enumerate(refs):
        if index < len(LOAD_NODES):
            graph[LOAD_NODES[index]]["inputs"]["image"] = filename
        else:
            node_id = str(FIRST_EXTRA_NODE + index - len(LOAD_NODES))
            graph[node_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": filename},
                "_meta": {"title": "Load reference {}".format(index + 1)},
            }
            graph["7518"]["inputs"]["ref_images.ref_image_{}".format(index)] = [
                node_id, 0,
            ]

    graph[SAVE_NODE]["inputs"]["filename_prefix"] = "video/claude_code/{}".format(prefix)
    return graph


def render(segment, prefix, start_index, args, audio_name, refs):
    graph = build_segment_graph(
        segment, prefix, refs, args.aspect, args.ref_image_size, args.workflow
    )
    graph[AUDIO_NODE]["inputs"]["audio"] = audio_name
    graph[AUDIO_NODE]["inputs"]["file"] = audio_name
    graph[TRIM_NODE]["inputs"]["start_index"] = start_index
    graph[TRIM_NODE]["inputs"]["duration"] = args.trim_duration

    resp = post(args.api, "/prompt", {"prompt": graph, "client_id": args.client_id})
    pid = resp.get("prompt_id")
    if not pid:
        print("QUEUE ERROR:", json.dumps(resp))
        return False
    if resp.get("node_errors"):
        print("NODE ERRORS:", json.dumps(resp["node_errors"]))
        return False
    print("[{}] queued {} (duration={}s)".format(prefix, pid, segment["duration"]))

    while True:
        hist = post(args.api, "/history/" + pid)
        item = hist.get(pid)
        if item and item.get("outputs"):
            break
        time.sleep(5)

    mp4s = [
        image for node in item["outputs"].values()
        for image in node.get("images", [])
        if image.get("type") == "video" or image.get("filename", "").endswith(".mp4")
    ]
    if not mp4s:
        print("[{}] NO MP4 OUTPUT. outputs={}".format(
            prefix, list(item["outputs"].keys())
        ))
        return False
    image = mp4s[0]
    url = (
        '{}?filename={}&subfolder={}&type={}'.format(
            args.api + "/view",
            image["filename"],
            image.get("subfolder", ""),
            image.get("type", "input"),
        )
    )
    with urllib.request.urlopen(urllib.request.Request(url), timeout=600) as response:
        data = response.read()

    dst = os.path.join(args.out_dir, "{}.mp4".format(prefix))
    with open(dst, "wb") as handle:
        handle.write(data)
    print("[{}] saved {} ({} bytes)".format(prefix, dst, len(data)))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render storyboard segments with Minimax H3."
    )
    parser.add_argument("--sb", required=True, help="storyboard JSON path")
    parser.add_argument("--workflow", default=DEFAULT_WF, help="H3 workflow JSON")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="project output directory")
    parser.add_argument("--comfy-input", default=DEFAULT_COMFY_INPUT,
                        help="ComfyUI input directory (LoadImage/LoadAudio root)")
    parser.add_argument("--api", default=DEFAULT_API, help="ComfyUI API base URL")
    parser.add_argument("--audio", help="soundtrack filename (default: <slug>.mp3)")
    parser.add_argument("--audio-source", help="full path to the soundtrack file")
    parser.add_argument("--slug", help="asset slug (default: derived from the SB filename)")
    parser.add_argument("--prefix", action="append", default=[],
                        help="explicit segment output prefix (repeatable, in segment order)")
    parser.add_argument("--ref", action="append", default=[], metavar="NODE=FILE",
                        help="override a reference LoadImage node (153-156 or 9001+; repeatable)")
    parser.add_argument("--aspect", choices=["9:16", "16:9"], default=None,
                        help="video aspect (default: project.aspect_ratio or 9:16)")
    parser.add_argument("--ref-image-size", choices=["match", "max"], default="match",
                        help="H3 ref_image_size (default: match)")
    parser.add_argument("--dump-graph", metavar="DIR",
                        help="with --dry-run, write each resolved graph to DIR/<prefix>.json")
    parser.add_argument("--trim-duration", type=float, default=20.0,
                        help="audio trim window per segment in seconds (default: 20)")
    parser.add_argument("--audio-offset", type=float, default=0.0,
                        help="global seek into the soundtrack in seconds (default: 0)")
    parser.add_argument(
        "--audio-start-mode", choices=["storyboard", "cumulative"],
        default="storyboard",
        help="storyboard: use each segment's start field; cumulative: sum "
             "previous segment durations (use when every clip restarts at 00:00)",
    )
    parser.add_argument("--client-id", default="claude_code")
    parser.add_argument("--dry-run", action="store_true",
                        help="print resolved prompts/refs without calling ComfyUI")
    args = parser.parse_args(argv)
    if args.audio_offset < 0:
        parser.error("--audio-offset must be >= 0")

    with open(args.sb, encoding="utf-8") as handle:
        sb = json.load(handle)
    segments = sb.get("segments", [])
    if not segments:
        print("ERROR: storyboard has no segments", file=sys.stderr)
        return 1

    slug = args.slug or derive_slug(args.sb)
    aspect = resolve_aspect(sb, args.aspect)
    args.aspect = aspect
    audio_name, audio_source = resolve_audio(args, args.sb, args.out_dir, slug)
    track_duration = probe_duration(audio_source) if audio_source.exists() else None
    start_indexes = segment_start_indexes(
        segments, args.audio_start_mode, args.audio_offset
    )
    if (args.audio_start_mode == "storyboard" and len(segments) > 1
            and all(float(segment.get("start", 0.0) or 0.0) == 0.0
                    for segment in segments)):
        print(
            "WARNING: every segment has start=0; use --audio-start-mode cumulative "
            "so each segment trims the next audio window.",
            file=sys.stderr,
        )

    refs = resolve_refs(sb, parse_ref_overrides(args.ref))
    if not refs:
        print(
            "WARNING: storyboard has no reference sheets; the workflow will run "
            "with zero reference images.",
            file=sys.stderr,
        )

    if args.prefix:
        if len(args.prefix) != len(segments):
            parser.error(
                "--prefix count ({}) must match segment count ({})".format(
                    len(args.prefix), len(segments))
            )
        prefixes = args.prefix
    else:
        prefixes = ["{}_seg{}".format(slug, index + 1) for index in range(len(segments))]

    for segment, prefix, start_index in zip(segments, prefixes, start_indexes):
        duration = float(segment.get("duration", 0.0) or 0.0)
        if track_duration and start_index >= track_duration - 0.001:
            print(
                "WARNING: [{}] start_index {}s is at/after the track end "
                "({:.3f}s).".format(prefix, start_index, track_duration),
                file=sys.stderr,
            )
        elif track_duration and start_index + duration > track_duration + 0.001:
            print(
                "WARNING: [{}] segment window {:.3f}-{:.3f}s runs past the "
                "track end ({:.3f}s).".format(
                    prefix, start_index, start_index + duration, track_duration
                ),
                file=sys.stderr,
            )
        if args.trim_duration + 0.001 < duration:
            print(
                "WARNING: [{}] --trim-duration {}s is shorter than the {}s "
                "segment.".format(prefix, args.trim_duration, duration),
                file=sys.stderr,
            )

    refs_text = ",".join(
        "{}={}".format(ref_node_id(index), filename)
        for index, filename in enumerate(refs)
    )
    print(
        "config: sb={} workflow={} api={} input={} out={} audio={} source={} "
        "aspect={} ref_image_size={} trim={} audio_offset={} start_mode={} "
        "track_duration={}".format(
            args.sb, args.workflow, args.api, args.comfy_input, args.out_dir,
            audio_name, audio_source, args.aspect, args.ref_image_size,
            args.trim_duration, args.audio_offset, args.audio_start_mode,
            "{:.3f}".format(track_duration) if track_duration else "unknown",
        )
    )
    print("refs: {}".format(refs_text))
    if not audio_source.exists():
        print(
            "WARNING: audio source not found: {}".format(audio_source),
            file=sys.stderr,
        )

    if args.dry_run:
        for segment, prefix, start_index in zip(segments, prefixes, start_indexes):
            prompt = build_prompt(segment)
            print(
                "DRY RUN [{}] duration={}s start={}s start_index={}s "
                "aspect={} refs={}".format(
                    prefix, segment.get("duration"), segment.get("start"),
                    start_index, args.aspect, refs_text,
                )
            )
            print(
                "DRY RUN [{}] sections={} prompt_chars={}".format(
                    prefix, ",".join(SECTIONS), len(prompt),
                )
            )
        if args.dump_graph:
            graph_dir = Path(args.dump_graph)
            graph_dir.mkdir(parents=True, exist_ok=True)
            for segment, prefix in zip(segments, prefixes):
                graph = build_segment_graph(
                    segment, prefix, refs, aspect, args.ref_image_size,
                    args.workflow,
                )
                path = graph_dir / "{}.json".format(prefix)
                path.write_text(json.dumps(graph), encoding="utf-8")
                print("  graph: {}".format(path))
        print(
            "DRY RUN: {} segment(s) selected; no ComfyUI calls made".format(
                len(segments)
            )
        )
        return 0

    stage_audio(audio_source, args.comfy_input, audio_name, dry_run=False)
    ok = True
    for segment, prefix, start_index in zip(segments, prefixes, start_indexes):
        ok = render(segment, prefix, start_index, args, audio_name, refs) and ok
    print("ALL SEGMENTS DONE" if ok else "SOME SEGMENTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
