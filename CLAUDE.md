# CLAUDE.md — Index & Non-Negotiables

**Purpose:** Entry point for this repo. Canonical paths, hard rules, and pointers to the real docs. Do not duplicate procedures here — they live in the files below.

---

## Quick Start

```bash
cd ~/Documents/comfy_music_video
claude          # starts session with skill discovered
```

Ask Claude to use the `music-video-storyboard` skill (or `/music-video-storyboard`) with the audio path and creative ask.

---

## Canonical Paths

| Category | Path |
|---|---|
| Repo root / Playwright workspace | `~/Documents/comfy_music_video` |
| Skill assets | `.claude/skills/music-video-storyboard/` |
| Final outputs | `outputs/` |
| Upload staging (gitignored) | `.upload_tmp/` |
| Extraction dump (gitignored) | `aistudio_response_md.txt` |
| AI Studio entry | `https://aistudio.google.com/prompts/new_chat` |
| ComfyUI API | `http://127.0.0.1:8188` |
| ComfyUI `LoadImage` reads ONLY | `~/Documents/comfyui/input/` |
| ComfyUI output | `~/Documents/comfyui/output/` |
| Original render pipeline (reference) | `~/Documents/comfy_control` |

---

## Source of Truth — Read These Files

| Topic | File |
|---|---|
| **Execution order (manual fallback SOP)** | `.claude/skills/music-video-storyboard/_manual-fallback.md` |
| **AI Studio UI procedure + red flags** | `.claude/skills/music-video-storyboard/_manual-fallback.md` §2–7, `memory.md` §3 |
| **Storyboard craft + render procedure** | `.claude/skills/music-video-storyboard/SKILL.md` |
| **Browser quirks + run history** | `memory.md` |
| **AI Studio capture CLI (Playwright)** | `.claude/skills/music-video-storyboard/aistudio_storyboard.py` |
| **DOM → markdown serializer** | `.claude/skills/music-video-storyboard/extract_markdown.js` |
| **Dump → final .md writer/validator** | `.claude/skills/music-video-storyboard/finalize_markdown.py` |
| **Markdown → storyboard JSON builder** | `.claude/skills/music-video-storyboard/build_storyboard.py` |
| **Reference sheet rules (Z-Image Turbo)** | `.claude/skills/music-video-storyboard/_z_image_turbo_rules.md` |
| **ref2va prompt format (H3)** | `.claude/skills/music-video-storyboard/_ref2va_rules.md` |
| **Camera/continuity techniques** | `.claude/skills/music-video-storyboard/_techniques.md` |
| **Storyboard JSON schema** | `.claude/skills/music-video-storyboard/_storyboard-schema.json` |
| **ComfyUI workflow: reference sheets** | `.claude/skills/music-video-storyboard/z_image_turbo.json` |
| **ComfyUI workflow: H3 segments** | `.claude/skills/music-video-storyboard/minimax_h3_api.json` |
| **Render script: reference sheets** | `.claude/skills/music-video-storyboard/render_sheets.py` |
| **Render script: H3 segments** | `.claude/skills/music-video-storyboard/render_h3.py` |
| **Worked example (Ref2VA format)** | `outputs/minh.md` |
| **Worked example (older format)** | `outputs/the-moonlit-promise-and-loss.md` (git checkout to recover) |

---

## Non-Negotiables (Hard Rules)

1. **Creative ask only** — send exactly `give me a good script for this soundtrack`. Strip paths, filenames, preset names, format instructions.
2. **Never reload/navigate/close mid-capture** — after a successful submission, do not refresh/navigate/close the AI Studio tab until the 1st response is extracted; temporary chat is unrecoverable. If the 1st response is wrong or empty, **refresh the page and rerun the whole flow from §2** (that is the only retry path).
3. **1st response only** — the **1st substantive model response** is the deliverable. The collapsible **Thoughts** panel above the answer is internal reasoning, **not a response** — never count it as response #1 (that would mislabel the real storyboard as "response #2"). **Never use the 2nd or any later response.** If the 1st fails, refresh the page and rerun; do not send a follow-up turn.
4. **Wait for 1st response completion** — `Stop` gone + `thumb_up`/`thumb_down` present + final code block contains `non_diegetic_music:`. Do not extract mid-stream.
5. **Extract with `extract_markdown.js` via `browser_evaluate`** — never `innerText`. Targets the **first model turn with substantive answer text** (the non-substantive Thoughts turn/panel is skipped); returns `''` if absent/streaming. Never fall back to a later response — refresh and retry.
6. **Upload from allowed root only** — stage copy in `.upload_tmp/` (under Playwright workspace root).
7. **Submit with Run button** — `Enter` inserts newline, does not submit.
8. **Filename from audio filename** — slugify (lowercase, `&`→`and`, punctuation→spaces, spaces→`-`, collapse repeats, trim ~60 chars).
9. **Body is verbatim** — formatting normalized only; wording, numbers, timecodes, prompts never changed.
10. **Finalizer exit 1 or clip-count warning = re-extract** — never hand-edit model output.

---

## Pipeline Overview

### Phase 1: Storyboard (AI Studio → Markdown)

**Automated alternative:** `.venv/bin/python -I .claude/skills/music-video-storyboard/aistudio_storyboard.py --audio <track>` performs steps 1–10 below (CDP attach, preset, upload, 1st-response capture, finalize, verify) and then builds the storyboard JSON (`--no-build-json` to skip). It sets the file input directly, so the MCP allow-list / `.upload_tmp` staging rule (#6) does not apply to automated runs. Use `--check` after any AI Studio UI change. The manual steps in `.claude/skills/music-video-storyboard/_manual-fallback.md` remain the fallback and behavioral source of truth.

1. Preflight audio → `_manual-fallback.md` §1
2. Open temporary chat → `_manual-fallback.md` §2
3. Select Film Director preset → `_manual-fallback.md` §3
4. Stage & attach audio → `_manual-fallback.md` §4
5. Send creative ask → `_manual-fallback.md` §5
6. Submit, wait for 1st response → `_manual-fallback.md` §6
7. Extract 1st response to dump → `_manual-fallback.md` §7
8. Name file, write markdown → `_manual-fallback.md` §8
9. Verify → `_manual-fallback.md` §9
10. Clean up → `_manual-fallback.md` §10

### Phase 2: Render (Z-Image Turbo → Minimax H3 → Final MP4)
1. **Storyboard JSON** — `outputs/<slug>-storyboard.json` (built from markdown with `build_storyboard.py`; the capture CLI builds it automatically unless `--no-build-json`; ref2va is copied verbatim, other fields auto-filled and optionally corrected via `--overrides`)
2. **Reference sheets** — `render_sheets.py` → 1920×1080 PNGs staged in ComfyUI `input/` + saved to `outputs/`
   - `character_protagonist_front.png` — character turnaround
   - `env_lakeside_promenade.png` — environment grid
   - `prop_ring_camellia.png` — prop sheet
   - `--dry-run --dump-graph DIR` writes each resolved Z-Image graph
3. **H3 segments** — `render_h3.py` reads `ref2va` from storyboard JSON, POSTs to ComfyUI, saves `outputs/<slug>_segN.mp4`
   - Node `7893`: `False` = 9:16 portrait, `True` = 16:9 landscape (default from `project.aspect_ratio`; `--aspect` overrides)
   - Ref wiring (auto): first character → 153, first environment → 154, first prop → 155, then remaining characters/environments/props → 156 and auto-created 9001+; unused `ref_image_N` wires are pruned. Override with `--ref NODE=FILE` (153–156 or 9001+); `--ref-image-size match|max` sets node 7518; `--dump-graph DIR` writes the resolved graph. `node_errors` in the queue response aborts immediately.
   - **Audio loading**: Node `7909` (`LoadAudioPlus` — "Load Music File") — `render_h3.py --audio` sets `audio`/`file` and stages the file into ComfyUI `input/`
   - **Audio trim**: Node `7895` (`TrimAudioDuration` — "Music Start Index") — `render_h3.py` sets `start_index` = `--audio-offset` + segment `start` (or cumulative previous durations with `--audio-start-mode cumulative`); `duration` = `--trim-duration` (**20s** default)
   - **Long tracks**: pass the same `--audio-offset` to `stitch_and_mix.py` so the final soundtrack starts at the same point as the H3 windows
   - Monitor: `curl -s http://127.0.0.1:8188/queue | jq '{running:(.queue_running\|length), pending:(.queue_pending\|length)}'`
4. **Copy segments** — `cp ~/Documents/comfyui/output/video/claude_code/<slug>_seg*.mp4 outputs/`
5. **Stitch & soundtrack** — ffmpeg concat + **original soundtrack only** (H3 vocal/foley discarded); `--trim-output <track-duration>`, never auto-trim H3 frame-snapped durations. `--with-h3-audio` opts into the old 65/35 mix if ever needed. For multi-segment runs, pass `--sb outputs/<slug>-storyboard.json` so every clip is trimmed to its requested duration: H3 rounds each request up to frames ≡ 5 mod 17 (up to +0.5 s/clip), and keeping the full renders would push the visuals ahead of the music.
6. **Verify** — `ffprobe` duration, aspect, frames. The current workflow renders portrait natively at **896×1568** (4:7); deliver that file as-is with **no post-processing upscale**. Add a 1080×1920 scale+crop only if explicitly requested (see `SKILL.md` §9)

Full render procedure: `.claude/skills/music-video-storyboard/SKILL.md` §8–9

---

## Key Scripts (Runnable Templates)

| Script | Purpose | CLI (no hardcoded edit needed) |
|---|---|---|
| `aistudio_storyboard.py` | AI Studio Film Director capture from a shell (Playwright) | `--audio` required; `--prompt`, `--out`, `--dump`, `--model`, `--cdp`; `--json`, `--build-json/--no-build-json`, `--aspect-ratio`, `--overrides`, `--character-name`, `--character-file/--env-file/--prop-file`, `--no-extend-last`; `--thinking-level` (default High), `--max-output-tokens` (default 131072; raised through the DOM above AI Studio's 65536 cap); `--check`, `--dry-run`, `--timeout`, `--retries`, `--force`, `--keep-open` |
| `build_storyboard.py` | Markdown → schema-valid storyboard JSON | `--md`, `--out`, `--audio`; optional `--aspect-ratio`, `--character-name`, `--character-file`, `--env-file`, `--prop-file`, `--overrides`, `--no-extend-last` |
| `finalize_markdown.py` | AI Studio dump → final `.md` | `--in`, `--audio`, `--model`; `--out`, `--title`, `--source`, `--thinking` optional |
| `render_sheets.py` | Render Z-Image Turbo reference sheets | `--sb` required; `--dry-run`, `--dump-graph DIR`, `--width/--height`, positional sheet stems |
| `render_h3.py` | Render H3 segments from storyboard JSON | `--sb` required; `--dry-run`, `--dump-graph DIR`, `--audio`, `--audio-offset`, `--audio-start-mode`, `--slug`, `--aspect`, `--ref`, `--ref-image-size`, `--trim-duration` |
| `stitch_and_mix.py` | Concat segments + original soundtrack only (H3 audio discarded) | `--slug`; `--sb outputs/<slug>-storyboard.json` (trim each clip to its requested duration), `--audio-offset` to match H3, `--dry-run`, `--trim-output` |

Run with `python3 -I <script.py>` (stdlib only, Python 3.12+). Exception: `aistudio_storyboard.py` needs Playwright, so run it with `.venv/bin/python -I`. Smoke tests: `python3 -I tests/test_pipeline_scripts.py -v` (its browser-free tests need no Playwright).

---

## Verification Commands

```bash
# Clip headings = prompt fields
grep -ciE '^#{3,4} +Clip' outputs/<slug>.md
grep -cE '(integrated_multimodal_description|detailed_description):' outputs/<slug>.md

# Final video
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_frames \
  -show_entries format=duration -of default=noprint_wrappers=1 outputs/<slug>.mp4
```

---

## Cleanup (Always Run)

```bash
rm -f ~/Documents/comfy_music_video/.upload_tmp/<staged-audio> \
      ~/Documents/comfy_music_video/aistudio_response_md.txt
rmdir ~/Documents/comfy_music_video/.upload_tmp 2>/dev/null || true
```
