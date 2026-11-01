# Agent Memory & Environment Gotchas — Google AI Studio / Film Director Pipeline

**Purpose:** Persistent institutional memory for the browser-driven storyboard pipeline in this repo: AI Studio/Playwright realities, learned quirks, and past run retrospectives. Read this before planning or running a job.

**This repo now includes the full Z-Image Turbo → Minimax H3 render pipeline** (copied from `~/Documents/comfy_control`). After the storyboard markdown is generated, you can render the video locally using the same workflow:

1. **Storyboard markdown** → AI Studio (Film Director) → `outputs/<slug>.md`
2. **Storyboard JSON** → built from markdown → `outputs/<slug>-storyboard.json`
3. **Reference sheets** → Z-Image Turbo (1920×1080) → staged in ComfyUI `input/`
4. **H3 segments** → Minimax H3 per segment → `outputs/<slug>_segN.mp4`
5. **Final video** → ffmpeg concat with soundtrack mix → `outputs/<slug>.mp4`

---

## 1. Local Machine Realities & Paths

- **Canonical paths:** see `CLAUDE.md` → Environment Paths / Source of Truth. The upload-critical constraint is repeated here:
- **Repo root / Playwright workspace root:** `~/Documents/comfy_music_video`
- **Skill:** `~/Documents/comfy_music_video/.claude/skills/music-video-storyboard/`
- **Outputs:** `~/Documents/comfy_music_video/outputs/`
- **Upload staging:** `~/Documents/comfy_music_video/.upload_tmp/` (gitignored)
- **Extraction dump:** `~/Documents/comfy_music_video/aistudio_response_md.txt` (gitignored)
- **AI Studio entry point:** `https://aistudio.google.com/prompts/new_chat`
- **Playwright MCP:** connected to a persistent profile already signed into Google. Do not attempt to log in.
- **Automation profile / CDP:** the signed-in Chromium used by the capture CLI runs with `--remote-debugging-port=9223 --user-data-dir=~/.cache/ms-playwright/chrome-for-automation-9223`. Attach with `connect_over_cdp`; never copy the profile (5.5 GB) and never run two launchers against the same `user-data-dir`.
- **Upload allow-list:** the file chooser only accepts paths under the Playwright MCP workspace root — expected to be this repo — plus `~/.cache/ms-playwright/chrome-for-automation-reddit`. A denied upload reports the actual allowed roots; stage the copy into whichever root the error lists and upload from there.
- **ComfyUI Local Port:** `http://127.0.0.1:8188`
- **ComfyUI `LoadImage` Hard Constraint:** `LoadImage` nodes **can ONLY read from `~/Documents/comfyui/input/`**. They cannot resolve project-local relative paths. Every generated reference sheet must be copied/staged here immediately.
- **ComfyUI Output:** `~/Documents/comfyui/output/video/claude_code/`

---

## 2. Toolchain Benchmarks & Execution Quirks

- **The 1st substantive response is the deliverable:** extract the **1st response** — the first model turn with substantive answer text (the Film Director storyboard). The collapsible **Thoughts** panel above the answer is **internal reasoning, not a response**; it renders as its own model turn with zero answer text (measured: Thoughts turn 0 chars, answer turn 5,262). Never count Thoughts as response #1 or the storyboard as #2. **Never use the 2nd or any later response.** Wait for the 1st to finish — do not use a fixed timeout as proof of completion. If it is still streaming after ~5 minutes, keep waiting; only report if it appears stalled (no new content and `Stop` remains for an extended period). Do not extract a partial answer. If the 1st response is wrong, empty, or only audio analysis, **refresh the page and rerun the whole flow from the top**; never send a follow-up and never use the 2nd.
- **Audio policy — original soundtrack only:** the final video uses the source track and **replaces/discards the H3-generated vocal/foley layer**. `stitch_and_mix.py` now defaults to soundtrack-only; `--with-h3-audio` restores the old 65/35 mix only when explicitly requested.
- **No background rendering:** unlike `comfy_control`, this pipeline is interactive browser work. Wait with `browser_wait_for` (5–10 s) then screenshot; do not poll in a tight loop.
- **Shell automation:** `aistudio_storyboard.py` performs §2–§10 in one command (CDP attach, preset, upload, 1st-response wait, extract, finalize, verify), then builds the storyboard JSON by default (`--no-build-json` to skip; `--json`, `--aspect-ratio`, `--character-name`, `--overrides`, and `--*-file` pass through to the builder). The post-build verifier checks every segment's six ref2va labels. `--check` validates every selector and the preset without uploading; exit code 4 means UI drift. Failures retry as a fresh temporary chat, never as a follow-up turn.
- **Builder extraction fallbacks:** `build_storyboard.py` tries Step 1 sheet formats in order — H4 + fenced block, any fenced block, blockquote block, bulleted key/value lines — so Film Director runs that ignore the code-fence instruction still produce sheets. Clip headings accept `#### Clip 1` and `#### Clip [1]`. Only indented prose with no heading/fence/bullet still needs `--overrides`.
- **Renderer reference wiring is dynamic:** `render_h3.py` orders refs (first character, first environment, first prop, then the rest), wires the first four to nodes 153–156 and extras to auto-created 9001+, and prunes unused `ref_image_N` wires so `<Picture N>` labels match. `--dump-graph DIR` writes the exact graph; a `node_errors` response aborts instead of polling for history that will never arrive.
- **H3 render resolution (workflow update 2026-10-29):** the phase-2b upscale chain is removed; node `6074` feeds the phase-2a upscale, so portrait renders come out at **896×1568** (24 fps, 4:7). `render_h3.py` does not touch resolution. The native file is the deliverable; no post-processing upscale is applied unless explicitly requested.
- **H3 snaps durations up to frames ≡ 5 mod 17:** whole-second requests round up (10.0 s → 243 frames = 10.125 s), so 180 s of requested segments renders as **185.583 s**. Keeping every rendered frame pushes the visuals ahead of the soundtrack. `stitch_and_mix.py --sb outputs/<slug>-storyboard.json` trims every clip — including the last — back to `segments[].duration`, restoring the intended timeline; `--trim-output` caps the result at the track length. Without `--sb` the script still keeps every frame (intentional for other pipelines). A count mismatch between storyboard segments and clips exits 1.
- **Maximum output tokens is UI-capped at 65536:** Run settings → Advanced settings hard-caps the number input. High thinking is charged against the same output budget, so long storyboards truncate mid-clip. `aistudio_storyboard.py` removes the input's `max` attribute and sets **131072** through the DOM before submitting (`--max-output-tokens`, default 131072); AI Studio's Get code then reports `'max_output_tokens': 131072`.
- **Temporary chat is unrecoverable:** it does not save the conversation. Reloading, navigating away, or closing the tab destroys the only copy of the response. Uploaded files are still saved to Google Drive — say this before uploading if the user has not been told.
- **Presets are browser-local:** stored in localStorage. Observed presets: `Nothing`, `Minimax H3 FL2VA`, `Video Clip Analysis`, `Film Director`, `Image Analysis`. If `Film Director` is absent, stop and ask; never substitute another preset or paste your own instruction text.
- **Model/thinking level:** the capture CLI reads the model name from the Run settings button and sets the Thinking Level combobox to **High** on every run (Temporary chat resets it to Medium). `--thinking-level` overrides it; the level is recorded in the markdown provenance with `Thinking level: High`.
- **Model name:** read it from the Run settings model button (e.g. `Gemini 3.8 Flash` / `gemini-3.8-flash`). If it cannot be read, omit the `Source:` line entirely rather than guessing or leaving a placeholder.
- **Upload size:** AI Studio rejects oversized files. Check size and duration before uploading. If `ffprobe` is unavailable, use the duration shown on the attachment chip after upload.
- **Attachment chip:** must show the filename and duration (e.g. `0:51`). A token count may also appear; it is optional and not a requirement.

---

## 3. AI Studio UI Map & Playwright Gotchas

| Target | How to find it |
|---|---|
| System instruction button | `browser_find` "System instructions" |
| Preset dropdown | role `combobox`, name `+ Create new instruction` (or the current preset) |
| Film Director option | role `option`, name `Film Director` |
| Attach menu | button `Insert images, videos, audio, or files` → menuitem `Upload files` |
| Prompt box | textbox `Enter a prompt` |
| Submit | button `Run` |
| Completion signal (1st response) | `Stop` gone + `thumb_up`/`thumb_down` present + final fenced block has all six ref2va labels + text stable across 3 polls |
| Model name | Run settings model button (e.g. `Gemini 3.8 Flash gemini-3.8-flash …`) |
| Response body | 1st *substantive* model `ms-chat-turn` (Thoughts/empty turns skipped) → `ms-text-chunk ms-cmark-node.cmark-node` |
| Preset close | button `Close panel` after a preset is selected; `Escape` also collapses the panel and leaves the composer usable |
| Upload (direct) | `input[type=file].file-input` (`multiple`) exists before the menu opens; `set_input_files` bypasses the chooser |
| Submit (automation) | accessible name is `Run Ctrl keyboard_return` — match `^Run\b`, **not** `exact=True`; disabled while the composer is empty |
| Preset list (2026-10-27) | Create new instruction, **Minimax H3 R2VA**, Nothing, Minimax H3 FL2VA, Video Clip Analysis, Film Director, Image Analysis |

### Critical gotchas

1. **Thoughts ≠ a response; the 1st substantive answer turn is the 1st response:** the "Thoughts" UI renders internal reasoning as its **own `ms-chat-turn`** with **zero answer text** (live DOM check on 2026-10-27: raw turns were user, prompt, Thoughts model turn (0 chars), the answer model turn (5,262 chars), an empty turn, the 2nd Thoughts turn (0 chars), the 2nd answer turn). An empty/aborted reply also adds an empty model turn, so counting raw model turns is unreliable. The extractor filters to model turns that contain a substantive `ms-text-chunk ms-cmark-node.cmark-node` (>200 chars, not starting with "Thoughts") and then takes **index 0** — the 1st response. It never falls back to the 2nd. If no substantive answer turn exists, or it is still streaming, the extractor returns `''`; then refresh the page and rerun the flow.
2. **Stale refs:** element refs go stale as soon as a panel opens or closes. Re-run `browser_find` before each click; never reuse an old ref across a panel transition.
3. **`innerText` is empty on this Angular page:** `document.querySelector('main').innerText` returns an empty string. Even where text exists, raw `innerText` includes UI chrome (`edit`, `more_vert`, `code`, `Text`, `download`, `content_copy`, `thumb_up`) and flattens nested lists / code fences. Use the DOM serializer.
4. **Submit semantics:** `Enter` inserts a newline and does not submit. Click `Run`; `Ctrl+Enter` also works once `Run` is enabled. `Run` can remain disabled while the audio finishes registering. **Verify the composer is non-empty before clicking Run** — read the textarea's `.value` in `browser_evaluate`. An empty submission still queues and yields an empty model turn, so you end up waiting for a response that will never come. The extractor correctly skips that empty turn (it filters to substantive model turns), which makes the failure look like a missing 1st response rather than a lost prompt — refresh and rerun.
5. **File chooser detection:** after clicking `Upload files`, wait for the tool to report `Modal state: [File chooser]`. If no modal appears, re-find and re-click the menu item once; if it still fails, stop and report.
6. **Upload denial:** `File access denied` or `ENOENT` means the path is outside the allow-list or mistyped. Fix the path — do not retry the same call.
7. **Clipboard fallback:** if the extractor returns `''`, wait for the 1st response to complete; do not fall back to a later response. Then click the **1st response's** Copy button and run `browser_evaluate` with `async () => await navigator.clipboard.readText()` **and the same `filename`**, so the result is JSON-quoted in the same dump format the finalizer expects. Verify the text starts with the H3 storyboard and contains `non_diegetic_music:` before using it — a stale clipboard otherwise. If it still fails, refresh the page and rerun the flow. Never ship raw `innerText`.
8. **Completion is content-based:** `Stop` gone + response toolbar present + the final code block of the **1st response** contains `non_diegetic_music:`. A closing fence alone is not proof — Film Director's output ends on the last clip's audio fields.
9. **The Stop button can flicker mid-stream:** AI Studio briefly re-renders fenced blocks and `Stop` can disappear for a poll while the answer is still streaming. A single "Stop gone + toolbar present" check can therefore capture a partial answer (Run 11 attempt: capture ended at Clip 12/17 while Clip 12 was still being revealed, then the tab closed "as completed"). Completion now requires all of: no `Stop`, the **last fenced block** contains all six ref2va labels, clip headings == prompt blocks, and the extracted text unchanged across **3 consecutive polls (~6 s)**. `final_block_complete()` in `aistudio_storyboard.py` implements this.

---

## 4. Model Behavior & Output Formatting Rules

### Film Director preset
1. **1st-response rule:** the **1st response** (the substantive answer below the Thoughts panel) is the H3 storyboard and is the only one extracted. The Thoughts panel is reasoning, not a response. Never send a follow-up and never use the 2nd or later response. Wait for the 1st response's completion signals before extracting; if it is wrong or empty, refresh the page and rerun from the top.
2. **The preset controls structure.** Do not append format instructions, a `Project Title:` line, or clip-length demands to the initial prompt. Send only the creative ask. **Standing default: send exactly `give me a good script for this soundtrack`** — the user instructed this for Gemini runs, so never ask them for a prompt and never embellish or vary it. Only if the user dictates different text in the current run do you send theirs verbatim instead. Do not append a storyboard follow-up: the 1st response is extracted directly (`_manual-fallback.md` §6).
3. **Three-step output; Step 3 has two variants:** the response follows `Step 1: Visual Continuity Reference Prompts` → `Step 2: Grounded Cinematic Storyboard` → `Step 3: MiniMax Generation Prompts` (the Step 3 subtitle varies). Per-clip Step 3 uses either:
   - the older `integrated_multimodal_description:` block (Run 01), or
   - the six-part Ref2VA block with `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music` (Run 02).
   The AI Studio system prompt was subsequently updated to emit the six-part Ref2VA H3 schema used by `comfy_control` by default; the finalizer accepts the older form too for backwards compatibility. Do not "fix" one into the other.
4. **Reference prompts in Step 1** are prose prompts for image generation (character turnaround, prop sheet, environment turnaround). The observed run used `--ar 16:9`; that is the model's output, so preserve it. Do not edit or normalize the model's prompts. Formatting varies: Run 07 returned the Step 1 prompts as **blockquotes** (`> …`) and Run 09 returned them as indented `- Prompt:` prose bullets; `build_storyboard.py` extracts only fenced code blocks, so both runs supplied the sheets via `--overrides` with Z-Image-style prompts (drop the model's `--ar 16:9`; sheets are always 1920×1080).
5. **Clip structure:** Step 2 uses bullets like `- Clip 1 (00:00 - 00:12 | 12s): Title`. Step 3 uses headings like `#### Clip 1 [00:00 - 00:12 | Duration: 12s]`. The verification grep targets the `####`/`###` heading form.
6. **Internal shot timecodes are not always segment-relative:** ref2va wants `[Shot N] At MM:SS.mmm` relative to the segment start, but the model sometimes writes whole-video time. Run 09's Clip 2 carried `At 00:15.200` inside a 10.8 s clip. The prompt is kept verbatim per the no-edit rule, so expect that internal cut to land late or be ignored by H3; record it in `open_questions` rather than changing the model's numbers.
7. **Title:** use the audio filename (slugified: lowercase, `&` → `and`, punctuation → spaces, spaces → `-`, collapse repeats, trim to ~60 chars). Never use `Step 1…` as the title.
8. **Lyrics/dialogue:** in the observed run, foreign-language lyrics appear inline as `<d>[Vietnamese] …</d>`. Preserve them exactly; do not translate, trim, or reformat.
9. **Completion:** do not extract mid-stream. A partial 1st response looks plausible and passes a casual glance. Wait for all three completion signals on the **1st** response. The Thoughts panel is not part of the answer — judge completion by the answer text and the response toolbar, not by the Thoughts panel.

### Output naming
- File name comes from the audio filename (slugified: lowercase, `&` → `and`, punctuation → spaces, spaces → `-`, collapse repeats, trim to ~60 chars).
- If the target exists, ask before overwriting. If the user declines, offer `<slug>-2.md`; do not silently reuse or rename the existing file.
- Outputs land in `outputs/`. The intermediate dump stays at the repo root and is deleted in Step 10.

---

## 5. Finalizer Behavior & Guardrails

`finalize_markdown.py`:

- json-decodes the dump; raises on non-JSON (surface the real error).
- refuses captures under 200 chars.
- refuses captures with an odd number of ``` fences.
- refuses text without either Step 3 prompt field, `integrated_multimodal_description` or `detailed_description` (wrong model turn — e.g. a later response — or wrong preset).
- counts both fields for the clip/prompt check.
- warns — but exits 0 — if `non_diegetic_music` is absent.
- warns — but exits 0 — if the number of `###/#### Clip` headings differs from the number of Step 3 prompt fields (`integrated_multimodal_description:` or `detailed_description:`).
- prepends `# <title>`, the provenance `> Source:` lines, and `---`.
- exit codes: `0` ok, `1` unreadable/truncated capture.

Treat exit code 1 or any warning as a reason to re-extract before reporting. Never hand-edit the model's body to satisfy a check.

---

## 6. Historical Run Log (Worked Examples)

### Run 01: `the-moonlit-promise-and-loss` (2026-10-26)

- **Source:** committed as `outputs/the-moonlit-promise-and-loss.md` in commit `10b5ce9`.
- **Input:** `1409777950540457.mp3` (0:51, 1,647 tokens).
- **Prompt sent:** `give me a good script for this soundtrack`.
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** single response — this run predates the 1st-response-only workflow. Do not use it as the model for new runs.
- **Output:** 4 clips — 12 s + 12 s + 13 s + 14 s = 51 s; 4 `integrated_multimodal_description` fields (older Step 3 format); 4 `non_diegetic_music` fields; 117 lines, ~7.7 KB.
- **Step 1 reference prompts:** 3 — character turnaround (24-year-old Vietnamese man, charcoal wool coat, Chelsea boots), prop sheet (vintage tarnished silver locket), environment turnaround (wet rooftop balcony at dusk). All use `--ar 16:9`.
- **Story:** Minh stands on a rain-slicked rooftop balcony under a pale moon, clutching a silver locket, singing in Vietnamese across four clips that move from moonlit promise to acceptance and closure.
- **Verification:** title + provenance + `---` present; 4 clip headings = 4 prompts; last timecode `00:51` matches the track duration within ~1 s; no UI chrome observed.
- **Title source:** audio filename `1409777950540457.mp3` → slug `1409777950540457`.
- **Artifact note (2026-10-26):** the file is committed but currently deleted in the working tree (`git status` shows `D outputs/the-moonlit-promise-and-loss.md`; as of Run 03, `outputs/` contains only `minh.md`). Recover with `git checkout -- outputs/the-moonlit-promise-and-loss.md` if the artifact is needed. An untracked `outputs/film_director.md` appeared in the initial git status but was absent when checked; do not assume either file is on disk.

### Run 02: `solitary-regret` (2026-10-26)

- **Source:** `~/Documents/comfy_music_video/outputs/solitary-regret.md` (test run).
- **Input:** `1409777950540457.mp3` (0:51, 1,647 tokens) — same track as Run 01.
- **Prompt sent:** initial `give me a good script for this soundtrack`; the model returned audio analysis only, so a follow-up requested the actual storyboard: `Now produce the actual film script / music-video storyboard...`.
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** 2nd (historical — predates the 1st-response-only rule; do not repeat).
- **Output:** 4 clips — 13 s + 12 s + 13 s + 13 s = 51 s; 4 `detailed_description` fields (six-part Ref2VA format); 4 `overall_soundscape`; 4 `non_diegetic_music`; model body 202 lines / 13,696 chars; final file 213 lines / 14,208 bytes.
- **Title source:** audio filename `1409777950540457.mp3` → slug `1409777950540457`.
- **Verification:** 4 clip headings = 4 prompt fields; last timecode `00:51`; balanced fences (8); no UI chrome; body byte-identical to the decoded DOM dump.
- **Failure & fix:** `finalize_markdown.py` originally required `integrated_multimodal_description` and rejected this valid Ref2VA output. Updated the validator to accept `integrated_multimodal_description` **or** `detailed_description`, and to count both. Re-ran successfully.
- **Lesson:** the current Film Director preset emits the six-part Ref2VA block with `detailed_description`; the older committed Run 01 used `integrated_multimodal_description`. Do not assume only one format.

### Run 03: `minh` (2026-10-26)

- **Source:** `/path/to/1409777950540457.mp3` (user-supplied path outside the repo).
- **Input:** `1409777950540457.mp3` (0:51) — same track as Runs 01–02.
- **Prompt sent:** `give me a good script for this soundtrack`; after the 1st response finished, a separate storyboard follow-up was sent.
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** 2nd (historical — predates the 1st-response-only rule; do not repeat).
- **Output:** 4 clips — 15 s + 12 s + 12 s + 12 s = 51 s; 4 `detailed_description` fields; 4 `non_diegetic_music`; 190 lines / 12,263 bytes.
- **Step 1 reference prompts:** 3 — character turnaround (28-year-old Vietnamese man, charcoal overcoat, navy turtleneck), prop sheet (antique engraved silver pocket locket watch), environment turnaround (open-air coastal train platform at night). All use `--ar 16:9`.
- **Story:** a young man waits on a rain-slicked coastal night platform under a full moon, holding an engraved silver locket watch with a fading portrait, moving from waiting to acceptance across four clips.
- **Title source:** audio filename `1409777950540457.mp3` → slug `1409777950540457`.
- **Verification:** title + provenance + `---` present; 4 clip headings = 4 prompt fields; last timecode `00:51` matches duration; balanced fences (8); no UI chrome.
- **Lesson:** the same 0:51 track produced a different story in each run (Runs 01–03); do not carry titles, settings, or character names across runs or assume deterministic output. The file name always comes from the audio filename (slugified).

### Run 04: `past-lives` (2026-10-26)

- **Source:** `/path/to/past_lives.mp3` (user-supplied path outside the repo).
- **Input:** `past_lives.mp3` (0:12.225).
- **Prompt sent:** `give me a good script for this soundtrack`; after the 1st response, a standard storyboard follow-up was sent.
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** 2nd (historical — predates the 1st-response-only rule; do not repeat).
- **Output:** 2 clips; 2 `detailed_description` fields; 2 `non_diegetic_music`; 8,650-byte file. The model asked for ~6 s per clip; the JSON used 5.875 s + 6.583 s because those are H3-valid frame counts.
- **Step 1 reference prompts:** 4 — Jun (character turnaround), Elias (character turnaround), train corridor (environment), brass compass (prop). All rendered at 1920×1080.
- **Story:** Jun, alone in a train corridor at golden hour, holds a brass compass; Elias's reflection appears in the window, then he is physically present in the corridor.
- **Title source:** audio filename `past_lives.mp3` → slug `past-lives`.
- **Render:** 768×1344 (H3 native portrait, 4:7 — **not** exact 9:16) at 24 fps; seg1 141 frames = 5.875 s, seg2 158 frames = 6.583 s; each with AAC 32 kHz stereo.
- **Final:** `outputs/past-lives.mp4` — 768×1344, 294 frames, 12.25 s (trimmed toward the 12.225 s track; ffmpeg lands on the nearest frame), soundtrack 65% + foley 35%, max volume −9.0 dB. Exact-9:16 deliverable `outputs/past-lives-9x16.mp4` — 1080×1920, same 294 frames.
- **Failures & fixes:**
  - First follow-up submitted empty (text never entered the composer) → empty model turn. Re-typed, verified the textarea `.value`, confirmed `Run` enabled, then submitted. See §3 gotcha 4.
  - Extractor initially returned the 1st response because the Thoughts UI adds model turns (`modelTurns=4`). Fixed `extract_markdown.js` to filter substantive >200-char cmark turns before indexing. At the time it took index 1; the current rule is index 0 (the 1st response). See §3 gotcha 1.
  - Clip 2 had JSON-only label mismatches: `<Audio 2>` (workflow has one ref audio) and `[Shot 2] At 00:09.000` (absolute rather than segment-relative). Normalized to `<Audio 1>` and `At 00:03.000` in the storyboard JSON only; the markdown body stays verbatim.
  - `stitch_and_mix.py`'s old auto-trim would cut 0.875 s from a 5.875 s segment. The template now keeps every frame by default and offers `--auto-trim` only for non-H3 pipelines; `--trim-output` caps the final at the track length.
  - A 6 s request snaps to 6.583 s (158 frames). Budget segment sums from valid H3 lengths, not round seconds.
- **Lesson:** H3 valid frame counts at 24 fps are ≡ 5 mod 17 (141 = 5.875 s, 158 = 6.583 s, 294 = 12.25 s). Never decimal-trim H3 segments; trim the final output to the track instead. H3's "9:16" mode is 768×1344; add a scale+center-crop pass for exact 1080×1920.

### Run 05: `999doahong` (2026-10-27)

- **Source:** `~/Documents/comfyui/input/999doahong.mp3` (user-supplied path outside the repo).
- **Input:** `999doahong.mp3` (0:13.032, 357 KB, 419 tokens in AI Studio).
- **Prompt sent:** `give me a good script for this soundtrack`; **no follow-up** (1st-response-only flow).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** **1st** (the substantive answer below the Thoughts panel). The Thoughts panel was its own model turn with 0 answer chars; the 1st response held 5,262 answer chars. The 2nd response (a non-Ref2VA prose script) was ignored.
- **Output:** 1 clip `[00:00 - 00:12 | 12s]`; 1 `detailed_description`; 1 `non_diegetic_music`; finalized `outputs/999doahong.md` 5,196 chars.
- **Step 1 reference prompts:** 3 — Chen (character turnaround, charcoal overcoat + burgundy silk shirt), cut-crystal plum-wine glass (prop), 1990s Hong Kong neon lounge (environment). All rendered at 1920×1080.
- **Story:** a man sits alone by a rain-streaked neon window in a 1990s Hong Kong lounge, singing a Chinese ballad in the first half, then lifting the plum-wine glass for a slow sip before the dissolve to black.
- **Title source:** audio filename `999doahong.mp3` → slug `999doahong`.
- **Render:** 3 Z-Image Turbo sheets; 1 H3 segment at 768×1344 (H3 native portrait, 4:7 — not exact 9:16), 311 frames = 12.958 s, 24 fps, AAC 32 kHz stereo. Requested duration 12.958 s (a valid 5-mod-17 length) so the clip covers the 13.032 s track.
- **Final:** `outputs/999doahong.mp4` — 768×1344, 311 frames, 12.96 s, **original soundtrack only** (H3 vocal/foley discarded; 48 kHz stereo), mean −15.6 dB / max −4.4 dB. Exact-9:16 deliverable `outputs/999doahong-9x16.mp4` — 1080×1920, same 311 frames.
- **Failures & fixes:**
  - A follow-up storyboard turn was submitted before the user clarified the rule; the resulting 2nd response was a non-Ref2VA prose script and was ignored. **Fix:** no follow-up; extract the 1st response. The extractor was changed to `modelTurns[0]` and the docs were rewritten.
  - The Thoughts panel was initially described loosely as “a separate response”; the user clarified it is internal reasoning, **not a response**. The extractor now filters substantive answer turns (not starting with “Thoughts”) and the docs state the distinction explicitly.
  - The 1st response planned 12 s but the track is 13.032 s; the JSON uses 12.958 s (311 frames) instead of the 12.25 s that a 12.0 s request snaps to.
  - The workflow has four `ref_image` slots but this storyboard only defines Pictures 1–3; slot 4 was pointed at the character sheet and is unreferenced by the prompt.
  - The first final mix used the old 65/35 soundtrack + H3 foley blend. The user set the standing rule to **original soundtrack only**, so the artifacts were re-stitched with H3 audio discarded and `stitch_and_mix.py` now defaults to that behavior.
- **Verification:** 1 clip heading = 1 prompt field; last timecode `00:12` vs 13.032 s track (model rounded down); fences balanced; ffprobe final matches intent; 3-frame contact sheet shows the overcoated singer, the crystal glass, and the neon rain.

### Run 06: `999doahong` (no-lipsync re-run) (2026-10-27)

- **Source:** `/path/to/999doahong.mp3` (user-supplied path outside the repo).
- **Input:** `999doahong.mp3` (0:13.032, 350 KB, 419 tokens in AI Studio).
- **Prompt sent:** `no lipsync script` (user-dictated creative ask, sent verbatim; **no follow-up**).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** **1st** — the substantive answer below the Thoughts panel (raw turns: user, prompt, Thoughts model turn 0 chars, answer model turn 5,464 chars). No follow-up was sent.
- **Output:** 1 clip `[00:00 - 00:12 | 12s]`; 1 `detailed_description`; 1 `non_diegetic_music`; finalized `outputs/999doahong.md` 5,679 bytes.
- **Step 3 format:** Ref2VA six-part (`detailed_description`), **verbatim** from the model — verified field-by-field against the markdown code block.
- **Story:** a 32-year-old East Asian man in a charcoal wool trench coat sits alone at a rain-streaked window in a dim 1990s neon bar. **Silent acting — no lip-sync**: lips stay closed for the whole clip, the emotion carried by gaze, breath, and a suppressed gesture (he lifts the faceted crystal whiskey glass two inches, hesitates with a clenched jaw, and sets it back down without drinking).
- **Step 1 reference prompts:** 3 — character turnaround (32-year-old East Asian man, charcoal trench coat + black ribbed sweater), faceted crystal rocks glass with amber whiskey (prop), 4-view neon bar interior in the rain (environment).
- **Title source:** audio filename `999doahong.mp3` → slug `999doahong`.
- **Storyboard JSON:** `outputs/999doahong-storyboard.json` (built with the one-off `outputs/build_storyboard_999doahong.py`; the reusable replacement is `.claude/skills/music-video-storyboard/build_storyboard.py`, with run-specific authored prose supplied via `--overrides`); character sheet is Picture 1, environment is Picture 2 (matching the model's `<Picture N>` lines), prop sheet sits in the third reference slot and is uncited by the prompt.
- **Render:** 3 Z-Image Turbo sheets (1920×1080); 1 H3 segment at 768×1344 (H3 native portrait, 4:7 — not exact 9:16), 311 frames = 12.958 s, 24 fps, AAC 32 kHz stereo.
- **Final:** `outputs/999doahong.mp4` — 768×1344, 311 frames, 12.96 s, **original soundtrack only** (H3 vocal/foley discarded; 48 kHz stereo), mean −15.6 dB / max −4.4 dB. Exact-9:16 deliverable `outputs/999doahong-9x16.mp4` — 1080×1920, same 311 frames.
- **Failures & fixes:**
  - `browser_evaluate` needs the extractor source as a function **string**; passing the file contents directly returned `undefined`. **Fix:** the Playwright snippet reads the file, wraps it with `new Function('return (' + SRC + ')')()`, evaluates it in the page, stashes the result in `window.__md`, and a second `browser_evaluate` with `filename` writes the JSON-quoted dump to disk. (`browser_run_code_unsafe` has no `require` and no dynamic `import` in its sandbox, so the file must be embedded in the snippet by a shell/python step.)
  - The creative ask produced a story where the character does not sing on camera; the H3 prompt's "lips remain closed" instruction was kept verbatim so the render matches the ask.
- **Verification:** 1 clip heading = 1 prompt field; 8 fences (balanced); no UI chrome; last timecode `00:12` vs 13.032 s track (model rounded down; the render covers 12.958 s); ffprobe on both masters; 3-frame contact sheet shows the closed-mouth profile at the neon window and the crystal glass in hand.

### Run 07: `thousand-reasons-sadness` (2026-10-27)

- **Source:** `/path/to/thousand_reasons_sadness.mp3` (user-supplied path outside the repo).
- **Input:** `thousand_reasons_sadness.mp3` (0:55.615, 2.2 MB, 320 kbps, 44.1 kHz stereo; 1,781 tokens in AI Studio).
- **Prompt sent:** `give me a good script for this soundtrack`; **no follow-up** (1st-response-only flow).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Response used:** **1st** — the substantive answer below the Thoughts panel; the Thoughts turn carried no answer text.
- **Output:** 4 clips (14 + 13 + 14 + 14 = 55 s); 4 `detailed_description`; 4 `non_diegetic_music`; finalized `outputs/thousand-reasons-sadness.md` (12,072 bytes).
- **Step 3 format:** Ref2VA six-part (`detailed_description`), **verbatim**.
- **Story:** Lin (beige trench coat, cream turtleneck) and Chen (midnight-blue overcoat) linger on opposite sides of a rain-swept brutalist transit concourse at blue hour, singing a Mandarin ballad duet; Lin boards the last train and Chen walks away into the rain.
- **Step 1 reference prompts:** 4 — Lin turnaround, Chen turnaround, transparent vinyl umbrella + creased envelope prop sheet, transit concourse environment grid. **They arrived as blockquotes, not fenced code blocks**, so `build_storyboard.py` extracted zero sheets; the four sheets and their Z-Image Turbo prompts were supplied through `--overrides` (`outputs/thousand-reasons-sadness-overrides.json`).
- **Storyboard JSON:** `outputs/thousand-reasons-sadness-storyboard.json` (4 segments, 4 sheets, inventory 2 characters / 1 prop / 1 location).
- **Timing:** H3-valid durations 14.375 / 12.958 / 13.667 / 14.375 s = 55.375 s against the 55.615 s track; starts 0 / 14.375 / 27.333 / 41.0. Rendered with `--audio-start-mode cumulative` so each segment's audio window matches its position in the stitched timeline.
- **Ref wiring:** 153 = environment (`<Picture 1>`), 154 = Lin (`<Picture 2>`), 155 = umbrella/envelope prop (`<Picture 3>`), 156 = Chen (`<Picture 4>`), matching the model's per-clip `<Picture N>` lines.
- **Render:** 4 Z-Image Turbo sheets at 1920×1080; 4 H3 segments at 768×1344 (H3 native portrait, 4:7 — not exact 9:16), 345 / 311 / 328 / 345 frames, 24 fps; 1,329 frames total.
- **Final:** `outputs/thousand-reasons-sadness.mp4` — 768×1344, 1,329 frames, 55.375 s, **original soundtrack only** (H3 audio discarded; 44.1 kHz stereo AAC), mean −16.9 dB / max −3.7 dB. Exact-9:16 deliverable `outputs/thousand-reasons-sadness-9x16.mp4` — 1080×1920, same 1,329 frames.
- **Failures & fixes:** Only one — the blockquote-formatted Step 1 sheet prompts defeated the builder's fenced-block extractor; fixed with authored `--overrides`. The browser flow completed on the first submission with no retries.
- **Verification:** 4 clip headings = 4 prompts; rebuilt ref2va blocks are byte-identical to the markdown code blocks; ffprobe on both masters; 4-frame contact sheet shows Chen under the concourse, Lin with the umbrella, the envelope in hand, and Lin at the train doors.

### Run 08: `999doahong` (automated capture smoke test) (2026-10-27)

- **Source:** `outputs/999doahong.mp3` (13.032 s), test artifact written outside the repo.
- **Prompt sent:** `give me a good script for this soundtrack`; 1st-response-only flow, no follow-up.
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Automation:** `--check` passed every selector (signed in, composer, attach, file input, Run enable/disable, preset, 8,918-char instruction body, model label). The live run attached over CDP, selected the preset, uploaded via `input[type=file].file-input`, and captured the response in ~39 s.
- **Output:** 1 clip, 1 `detailed_description`, 1 `non_diegetic_music`; 8,583 chars; `/tmp/aistudio_spike/live/999doahong-autotest.md` (not committed; `outputs/999doahong.md` untouched).
- **Verification:** 1 clip heading = 1 prompt; 2 fences balanced; provenance line reads `Gemini 3.8 Flash`; finalizer and script both exited 0.
- **Failures & fixes:** none in the live pass. Confirmed the `Run` accessible name is `Run Ctrl keyboard_return` (exact `Run` fails), the direct file input avoids the chooser, and the completion-toolbar selector matches. The script closed its temporary-chat tab after finalize, so that chat is intentionally unrecoverable.

### Run 09: `2843221756060178` (2026-10-27)

- **Source:** `/path/to/2843221756060178.mp3` (user-supplied path outside the repo).
- **Input:** `2843221756060178.mp3` (0:20.950, 820 KB, 320 kbps, 44.1 kHz stereo).
- **Prompt sent:** `give me a good script for this soundtrack`; **no follow-up** (1st-response-only flow).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Automation:** `aistudio_storyboard.py --check` passed all selectors; the live run attached over CDP, selected the preset, uploaded via `input[type=file].file-input`, and captured the 1st substantive response in ~34 s.
- **Output:** 2 clips (10 + 10 = 20 s); 2 `detailed_description`; 2 `non_diegetic_music`; 6,904-char response; finalized `outputs/2843221756060178.md` (7,241 bytes).
- **Step 3 format:** Ref2VA six-part (`detailed_description`), **verbatim** (both blocks byte-identical to the markdown).
- **Story:** a late-twenties East Asian woman in an oversized slate-gray trench coat stands in profile at a rain-streaked penthouse window, singing a Chinese ballad of unanswered love; she turns away, crosses her arms, sits on the empty sofa, and fades into the wet city reflections.
- **Step 1 reference prompts:** 3 — character turnaround, acrylic-rib umbrella + cracked smartphone prop sheet, rainy penthouse environment grid. **They arrived as indented prose bullets, not fenced code blocks**, so `build_storyboard.py` extracted zero sheets; the three sheets and their Z-Image Turbo prompts were supplied through `--overrides` (`outputs/2843221756060178-overrides.json`).
- **Storyboard JSON:** `outputs/2843221756060178-storyboard.json` (2 segments, 3 sheets, inventory 1 character / 1 prop / 1 location).
- **Timing:** model clips were 10 s + 10 s; both durations were snapped to H3-valid frame counts in the overrides — 10.125 s (243 frames) + 10.833 s (260 frames) = 20.958 s against the 20.950 s track. The JSON `start` of clip 2 is 10.125 s so its audio window matches the rendered (snapped) clip-1 length rather than the model's stated 10.0 s.
- **Ref wiring:** 153 = character (`<Picture 1>`), 154 = environment (`<Picture 2>`), 155 = umbrella/phone prop (uncited), 156 = character spare, matching the model's `<Picture N>` lines.
- **Render:** 3 Z-Image Turbo sheets at 1920×1080; 2 H3 segments at 768×1344 (H3 native portrait, 4:7 — not exact 9:16), 243 / 260 frames, 24 fps.
- **Final:** `outputs/2843221756060178.mp4` — 768×1344, 502 frames, 20.917 s, **original soundtrack only** (H3 vocal/foley discarded; 44.1 kHz stereo AAC), mean −16.2 dB / max −2.9 dB. Exact-9:16 deliverable `outputs/2843221756060178-9x16.mp4` — 1080×1920, same 502 frames.
- **Model quirks (kept verbatim):** Clip 2's second internal cut is written `At 00:15.200` — a whole-video timecode, not segment-relative — so H3 may place that cut late or ignore it inside the 10.833 s clip. Step 2 Beat 3 describes a flashback embrace that never appears in the Step 3 prompts. The Step 1 prop sheet (umbrella + cracked phone) is not cited by either prompt.
- **Verification:** 2 clip headings = 2 prompts; 4 fences balanced; 2 `non_diegetic_music`; ref2va byte-identical; ffprobe on both masters; contact sheet confirms the profile-at-window, arms-crossed, and sofa-silhouette beats.

### Run 10: `1482519210397284` (2026-10-29)

- **Source:** `/path/to/1482519210397284.mp3` (user-supplied path outside the repo).
- **Input:** `1482519210397284.mp3` (0:21.603, 846 KB, 320 kbps, 44.1 kHz stereo).
- **Prompt sent:** `give me a good script for this soundtrack`; **no follow-up** (1st-response-only flow).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat.
- **Automation:** `aistudio_storyboard.py --check` passed all selectors; the live run attached over CDP, selected the preset, uploaded via `input[type=file].file-input`, and captured the 1st substantive response in ~45 s (submitted 16:00:07, captured 16:00:52).
- **Output:** 2 clips (11 s + 10 s), 2 `detailed_description`, 2 `non_diegetic_music`; 8,089-char response; finalized `outputs/1482519210397284.md`; JSON at `outputs/1482519210397284-storyboard.json`.
- **Step 3 format:** Ref2VA six-part (`detailed_description`), **verbatim** (both blocks byte-identical to the markdown).
- **Story:** Elena Wong, a 38-year-old woman in a burgundy silk-wool trench coat, alone on a 1980s Kowloon rooftop at dusk with a vintage brass flip-top lighter; she watches the sunset over Victoria Harbour, flicks the lighter alight, then turns into the twilight and walks toward the rooftop exit.
- **Step 1 reference prompts:** 3 blockquotes (character turnaround, brass lighter prop sheet, rooftop environment grid). `build_storyboard.py` extracted all three; their Z-Image Turbo prose and descriptive filenames were supplied through `--overrides` (`outputs/1482519210397284-overrides.json`).
- **Storyboard JSON:** 2 segments, 3 sheets, inventory 1 character / 1 prop / 1 location.
- **Timing:** durations snapped to H3-valid frame counts at 24 fps: **11.5417 s (277 frames)** and **10.125 s (243 frames)** = 21.667 s against the 21.603 s track. Clip 1's requested 11.0 s snaps up to 277 frames, so Clip 2's `start` is **11.542 s** (not 11.0) to align its audio window with the rendered timeline. Final trimmed to 21.603 s; ffmpeg lands on **517 frames / 21.572 s**.
- **Ref wiring:** 153 = character (`character_elena_front.png`, `<Picture 1>`), 154 = environment (`env_kowloon_rooftop_key.png`, `<Picture 2>`), 155 = brass lighter (`prop_brass_lighter_sheet.png`, `<Picture 3>`); the baked fourth wire was pruned.
- **Workflow test (the point of the run):** the updated `minimax_h3_api.json` removed the phase-2b upscale chain (nodes 7718/7873/7876/7877/7881/7891/7892), switched node 7869 to `minimax_h3_open_regenerate_2k_refiner_rank_384_bf16.safetensors`, inserted the `H3MemoryOptimization` + `taomate_h3_3step_MAXQUALITY` motion LoRA chain (7911 → 7910), set chunk_length 153, and moved the phase-2 upscale target (node 6074) to `896x1568`. `render_h3.py` queued both segments with **empty `node_errors`** and produced **896×1568, 24 fps, 277 / 243 frames** — the new resolution works.
- **Render:** 3 Z-Image Turbo sheets at 1920×1080; 2 H3 segments at 896×1568, 24 fps (seg1 saved 16:17, seg2 16:26).
- **Final:** `outputs/1482519210397284.mp4` — 896×1568, 24 fps, **517 frames, 21.572 s**, **original soundtrack only** (H3 vocal/foley discarded; 44.1 kHz stereo AAC), mean −16.4 dB / max −2.3 dB. **No post-processing upscale** (deliverable is the native 896×1568 render).
- **Model quirks (kept verbatim):** Clip 2's internal cut is written `At 00:15.000` — a whole-video timecode, not segment-relative, so H3 may place it late or ignore it inside the 10.125 s clip. Clip 2's summary begins `[video continuation + reference generation]` although no source video is fed. `non_diegetic_music` names Anita Mui's `夕陽之歌`; that layer is discarded in the final mix.
- **Workflow gotcha:** node `156` still bakes `prop_leash_collar.png` after the third ref wire is pruned. The file exists in ComfyUI `input/`, so validation passes; if it is ever removed, an unwired `156` could fail validation. `render_h3.py` prunes wires but not the node.
- **Verification:** 2 clip headings = 2 prompts; 4 fences balanced; 2 `non_diegetic_music`; ref2va byte-identical; `tests/test_pipeline_scripts.py` 39/39 pass; ffprobe confirms 896×1568 / 24 fps / 517 frames / 21.572 s; contact strips confirm the parapet, lighter close-up, and wide silhouette beats.

### Run 11: `redacted-track` (2026-10-31)

- **Redaction:** track title and local source path removed for public release.

- **Source:** `/path/to/track.m4a` (user-supplied path outside the repo).
- **Input:** `track.m4a` (2:59.566 = 179.5665 s). Canonical soundtrack `outputs/redacted-track.mp3` (320 kbps, 179.616 s container), staged identically into ComfyUI `input/`.
- **Prompt sent:** `give me a good script for this soundtrack`; **no follow-up** (1st-response-only flow).
- **Preset / model:** Film Director; Gemini 3.8 Flash; Temporary chat; Thinking High; **Maximum output tokens 131072 via DOM**.
- **Capture history:** attempt 1 (stock 65536) returned only 3 clips; retry attempt 1 returned 12 clips with builder "no six-section ref2va" errors; attempt 2 returned 12 headings / 11 prompts. The hardened run with 131072 + the content-based completion gate captured **17 clips** and was kept open (`--keep-open`). Root cause of the cut-offs was the completion gate accepting `non_diegetic_music:` from an already-complete clip while the answer was still streaming (Stop flicker), not only the token cap.
- **Output:** 17 clips (10, 10, 11, 12, 9, 10, 12, 10, 9, 11, 10, 11, 12, 11, 14, 9, 9 s), 17 `detailed_description`, 17 `non_diegetic_music`; 33,062-char storyboard `outputs/redacted-track.md`.
- **Step 3 format:** Ref2VA six-part; **verbatim** (copied byte-for-byte into the JSON by `build_storyboard.py`).
- **Story:** Marcus, in a black-and-orange varsity jacket and black beanie, hosts a Halloween block party on Maple Street — porch performance, trick-or-treaters and a dancing skeleton, a flashlight-lit alley beat, a costumed crowd, the stage mic, and a final empty porch.
- **Step 1 reference prompts:** blockquote sheets. `build_storyboard.py` was fixed to classify each blockquote by its nearest preceding H4 and to strip the leading `Midjourney / Flux Prompt:` label. Authored Z-Image prompts supplied via `--overrides` (`outputs/redacted-track-overrides.json`).
- **Storyboard JSON:** 17 segments, 3 sheets, inventory 1 character / 1 prop / 1 location; 9:16.
- **Timing:** requests snap to [10.125, 10.125, 11.542, 12.25, 9.417, 10.125, 12.25, 10.125, 9.417, 11.542, 10.125, 11.542, 12.25, 11.542, 14.375, 9.417, 9.417] = **185.583 s** for 180 s requested (+5.583 s). `stitch_and_mix.py --sb` trimmed each clip back to its storyboard duration, then `--trim-output 179.616` capped at the track.
- **Ref wiring:** 153 = character `character_marcus_front.png`, 154 = environment `env_maple_street_block_party.png`, 155 = prop `prop_flashlight_stage_mic.png`; unused wire pruned.
- **Render:** 3 Z-Image Turbo sheets at 1920×1080; 17 H3 segments at 896×1568 / 24 fps / **4,454 frames total** (seg1 243 … seg15 345 … seg17 226), rendered 14:05–17:40.
- **Final:** `outputs/redacted-track.mp4` — 896×1568, 24 fps, **4,309 frames, 179.573 s**, **original soundtrack only** (AAC stereo 48 kHz), mean −15.3 dB / max −0.9 dB. **No post-processing upscale.**
- **Tooling added this run:** `--max-output-tokens` + `set_max_output_tokens()` and `final_block_complete()` / 3-stable-poll gate in `aistudio_storyboard.py`; `--sb` storyboard-duration trimming with count validation in `stitch_and_mix.py` + tests; blockquote sheet classification fix in `build_storyboard.py`; docs updated in `CLAUDE.md`, `SKILL.md`, `_manual-fallback.md`.
- **Verification:** 17 clip headings = 17 prompts = 17 `non_diegetic_music`; ref2va byte-identical; `tests/test_pipeline_scripts.py` **41/41** pass; final ffprobe 896×1568 / 24 fps / 4,309 frames / 179.573 s / audio present; 17-frame contact sheet confirms every segment and character continuity.

---

## 7. Run Retrospective Log (Template for New Runs)

*Copy and append to §6 after completing a new run:*

```markdown
### Run [ID]: `<slug>` (YYYY-MM-DD)
- **Source:** [commit or file path]
- **Input:** [filename] ([duration], [tokens if shown])
- **Prompt sent:** "[creative ask]"
- **Preset / model:** Film Director; [model]; Temporary chat
- **Output:** [N] clips ([durations]), [N] prompts, [N] non_diegetic_music; [size]
- **Response used:** 1st
- **Step 3 format:** integrated_multimodal_description / detailed_description
- **Title source:** audio filename (slugified)
- **Render:** [sheet count], [resolution/aspect], [segment frame counts/durations], [audio]
- **Final:** [path], [resolution], [frames/duration], [mix], [exact-9:16 pass if any]
- **Verification:** clip headings = prompts; last timecode vs duration; UI chrome check; ffprobe final
- **Failures & fixes:** [truncation, upload denial, stale refs, wrong preset, clipboard fallback]
```
