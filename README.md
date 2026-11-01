# comfy-music-video

Turn an audio track into a music video with a local ComfyUI pipeline:

1. **Storyboard** — Google AI Studio's Film Director preset writes a shot-by-shot storyboard (first substantive response only).
2. **Storyboard JSON** — `build_storyboard.py` converts the markdown into the six-part Ref2VA schema.
3. **Reference sheets** — Z-Image Turbo renders 1920×1080 character, environment, and prop sheets.
4. **Segments** — MiniMax H3 renders each storyboard segment at the workflow's configured resolution (896×1568 portrait by default, 24 fps).
5. **Final cut** — `stitch_and_mix.py` concatenates the segments against the original soundtrack.

## Requirements

- Python 3.12+
- Playwright (`playwright>=1.64`) and a Chromium profile signed into Google AI Studio
- ComfyUI at `http://127.0.0.1:8188` with the Z-Image Turbo and MiniMax H3 workflows and models staged
- `ffmpeg` / `ffprobe` on `PATH`

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install "playwright>=1.64"

# Capture a storyboard (also builds outputs/<slug>-storyboard.json)
.venv/bin/python -I .claude/skills/music-video-storyboard/aistudio_storyboard.py \
  --audio /path/to/track.mp3

# Render reference sheets, segments, and the final cut
python3 -I .claude/skills/music-video-storyboard/render_sheets.py \
  --sb outputs/<slug>-storyboard.json
python3 -I .claude/skills/music-video-storyboard/render_h3.py \
  --sb outputs/<slug>-storyboard.json --audio /path/to/track.mp3
python3 -I .claude/skills/music-video-storyboard/stitch_and_mix.py \
  --slug <slug> --sb outputs/<slug>-storyboard.json --trim-output <seconds>
```

## Documentation

| Topic | File |
|---|---|
| Canonical paths, hard rules, pipeline overview | `CLAUDE.md` |
| Storyboard craft and render procedure | `.claude/skills/music-video-storyboard/SKILL.md` |
| Manual AI Studio procedure and red flags | `.claude/skills/music-video-storyboard/_manual-fallback.md` |
| Browser quirks and historical run notes | `memory.md` |

## Notes

- `outputs/` is gitignored: audio, reference sheets, segments, and final renders stay local.
- The capture flow attaches to a browser that is already signed into AI Studio and never stores credentials.
- The storyboard prompt is sent verbatim as the creative ask; see `SKILL.md` for the fixed prompt and the 1st-response-only rule.
