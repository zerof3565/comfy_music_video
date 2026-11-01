#!/usr/bin/env python3
"""Render pre-production reference sheets via Z-Image Turbo.

Reads every sheet's `generation_prompt` and `key_frame_file` from the storyboard
JSON, so the storyboard and the rendered sheet never diverge. For every sheet it
POSTs the workflow to ComfyUI, polls /history, downloads the PNG, and stages a
copy into ComfyUI's input/ so LoadImage can read it.

Usage:
    # All sheets, canonical paths
    python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json

    # One sheet (by filename stem)
    python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json character_elf_front

    # Validate the selection without touching ComfyUI
    python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json --dry-run

    # Write each resolved workflow graph (prompt + dimensions) for inspection
    python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json --dry-run \
        --dump-graph /tmp/sheet_graphs

Sheets are read from `references.character_sheets`, `environment_sheets`, and
`prop_sheets`. Each needs `key_frame_file` and `generation_prompt`. Sheets the
user already supplied (`source: "user-provided"`) can be skipped by not staging
them — the script will re-render anything listed here.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
DEFAULT_WF = os.path.join(SKILL_DIR, "z_image_turbo.json")
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "outputs")  # keep a copy here
DEFAULT_INPUT_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "comfyui", "input"
)  # LoadImage reads only from here
DEFAULT_API = "http://127.0.0.1:8188"


def post(api, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        api + path, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read().decode())


def load_sheets(sb_path):
    """Flatten the three reference-sheet arrays from the storyboard JSON."""
    with open(sb_path, encoding="utf-8") as handle:
        sb = json.load(handle)
    refs = sb.get("references", {})
    return (
        refs.get("character_sheets", [])
        + refs.get("environment_sheets", [])
        + refs.get("prop_sheets", [])
    )


def build_sheet_graph(sheet, cfg):
    """Return the Z-Image graph with this sheet's prompt and output prefix set."""
    name = os.path.splitext(sheet["key_frame_file"])[0]
    with open(cfg.workflow, encoding="utf-8") as handle:
        graph = json.load(handle)
    graph["7875"]["inputs"]["text"] = sheet["generation_prompt"]
    graph["7884"]["inputs"]["width"] = cfg.width
    graph["7884"]["inputs"]["height"] = cfg.height
    graph["7897"]["inputs"]["filename_prefix"] = f"images/claude_code/{name}"
    return graph


def render(sheet, cfg):
    name = os.path.splitext(sheet["key_frame_file"])[0]
    os.makedirs(cfg.input_dir, exist_ok=True)  # LoadImage needs input/ to exist
    graph = build_sheet_graph(sheet, cfg)

    resp = post(cfg.api, "/prompt", {"prompt": graph, "client_id": "claude_code"})
    pid = resp.get("prompt_id")
    if not pid:
        print("QUEUE ERROR:", json.dumps(resp))
        return False
    print(f"[{name}] queued {pid}", flush=True)

    while True:
        hist = post(cfg.api, "/history/" + pid)
        item = hist.get(pid)
        if item and "outputs" in item:
            break
        time.sleep(5)

    save = next(
        (node for node in item["outputs"].values()
         if node.get("type") == "output" or "images" in node),
        None,
    )
    if not save:
        print(f"[{name}] NO OUTPUT")
        return False
    img = save["images"][0]
    url = (
        f'{cfg.api}/view?filename={img["filename"]}&subfolder={img.get("subfolder","")}'
        f'&type={img.get("type","input")}'
    )
    with urllib.request.urlopen(urllib.request.Request(url), timeout=600) as response:
        data = response.read()

    dst = os.path.join(cfg.out_dir, sheet["key_frame_file"])
    with open(dst, "wb") as handle:
        handle.write(data)
    # Always overwrite the staged copy so a regenerated sheet replaces a stale one.
    with open(os.path.join(cfg.input_dir, sheet["key_frame_file"]), "wb") as handle:
        handle.write(data)
    print(f"[{name}] saved {dst} ({len(data)} bytes)", flush=True)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render storyboard reference sheets with Z-Image Turbo."
    )
    parser.add_argument("sheets", nargs="*",
                        help="sheet filename stems to render (default: all)")
    parser.add_argument("--sb", required=True, help="storyboard JSON path")
    parser.add_argument("--workflow", default=DEFAULT_WF, help="Z-Image Turbo workflow JSON")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="project output directory")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR,
                        help="ComfyUI input directory (LoadImage root)")
    parser.add_argument("--api", default=DEFAULT_API, help="ComfyUI API base URL")
    parser.add_argument("--width", type=int, default=1920, help="sheet width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="sheet height (default: 1080)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the resolved selection without calling ComfyUI")
    parser.add_argument("--dump-graph", metavar="DIR",
                        help="with --dry-run, write each resolved graph to DIR/<stem>.json")
    args = parser.parse_args(argv)

    sheets = load_sheets(args.sb)
    wanted = set(args.sheets)
    stems = {os.path.splitext(sheet["key_frame_file"])[0] for sheet in sheets}
    missing = wanted - stems
    if missing:
        print(
            "WARNING: no sheet matches: {}".format(", ".join(sorted(missing))),
            file=sys.stderr,
        )
    selected = [
        sheet for sheet in sheets
        if not wanted or os.path.splitext(sheet["key_frame_file"])[0] in wanted
    ]

    print(
        "config: sb={} workflow={} api={} input={} out={} {}x{}".format(
            args.sb, args.workflow, args.api, args.input_dir, args.out_dir,
            args.width, args.height,
        )
    )
    if args.dry_run:
        for sheet in selected:
            prompt = sheet.get("generation_prompt", "")
            print(
                "DRY RUN: would render {} -> {} ({}x{}) prompt={!r}{}".format(
                    os.path.splitext(sheet["key_frame_file"])[0],
                    os.path.join(args.out_dir, sheet["key_frame_file"]),
                    args.width, args.height,
                    prompt[:80], "..." if len(prompt) > 80 else "",
                )
            )
        if args.dump_graph:
            os.makedirs(args.dump_graph, exist_ok=True)
            for sheet in selected:
                graph = build_sheet_graph(sheet, args)
                stem = os.path.splitext(sheet["key_frame_file"])[0]
                path = os.path.join(args.dump_graph, stem + ".json")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(graph, handle)
                print("  graph: {}".format(path))
        print("DRY RUN: {} sheet(s) selected; no ComfyUI calls made".format(len(selected)))
        return 0

    ok = True
    for sheet in selected:
        ok = render(sheet, args) and ok
    print("ALL SHEETS DONE" if ok else "SOME SHEETS FAILED", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
