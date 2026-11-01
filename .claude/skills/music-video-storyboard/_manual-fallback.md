# Manual AI Studio Fallback — Storyboard Capture (SOP)

**Purpose:** the manual procedure that `aistudio_storyboard.py` automates (§1–§10). Use it when the automated capture fails or is unavailable; it is the behavioral source of truth for those steps. `SKILL.md` is the storyboard-craft authority; `memory.md` holds browser/upload quirks and run history.

**Automated path (default):** `.venv/bin/python -I .claude/skills/music-video-storyboard/aistudio_storyboard.py --audio <track>` — see `CLAUDE.md`.

**Last updated:** 2026-10-28

**Deliverable:** the **1st substantive response** — the first model turn with answer text (the Film Director Step 1 → Step 2 → Step 3 Ref2VA storyboard). The collapsible **Thoughts** panel is internal reasoning, **not a response**; never count it as response #1 and never use the 2nd or any later response. If the 1st response is wrong, empty, or only audio analysis, **refresh the page and rerun from §2** — do not send a follow-up turn.

---

## 1. Preflight (always run first)

```bash
# 1. Audio must exist and be real audio
ls -lh <audio> && file <audio>

# 2. Record duration (and size; AI Studio rejects oversized files)
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 <audio>

# 3. Confirm the output directory
ls -d ~/Documents/comfy_music_video/outputs
```

- If the audio does not exist, **stop and ask** — never substitute a nearby file silently.
- If `ffprobe` is unavailable, use the duration the attachment chip shows after upload.
- Playwright MCP must be connected to its persistent, signed-in profile. Do not attempt to log in. If it is not connected or not signed in, stop and report.
- The **Film Director** preset must be present in the preset list. If it is absent, stop and ask; never substitute another preset.
- **Paths:** canonical list in `CLAUDE.md` → Canonical Paths. Upload-critical: the file chooser only accepts paths under the Playwright workspace root (expected to be this repo) plus the Playwright cache root. Stage a copy in `.upload_tmp/`.
- **ComfyUI checks only when rendering.** Capture needs no ComfyUI; before rendering, confirm the API answers (`curl -s http://127.0.0.1:8188/queue`) and that the Z-Image/H3 workflows and reference PNGs are staged in ComfyUI `input/`.

---

## 2. Open a fresh temporary chat

1. `browser_navigate` → `https://aistudio.google.com/prompts/new_chat`.
2. `browser_take_screenshot` to confirm you are signed in and in **Temporary chat**.
3. If the user has not been told, say: Temporary chat does not save the conversation, **but uploaded files are saved to their Google Drive**.

Do not reuse an old chat tab. A fresh chat keeps the response isolated and avoids stale DOM state.

---

## 3. Select the Film Director system instruction

1. Click the **`System instructions`** button in the right-hand Run settings panel. On `new_chat` this panel is normally already open; if not, open it with the run-settings toggle in the main header.
2. Click the combobox labelled **`+ Create new instruction`** (it may already show a preset name).
3. Click the **`Film Director`** option in the listbox.
4. Verify all four:
   - combobox label = `Film Director`
   - `Title` field = `Film Director`
   - the instruction textarea is populated with the MiniMax-oriented director prompt
   - the panel shows `Saved`
5. Set **Thinking Level** to **High**. Temporary chat resets it to **Medium** on every new chat, so check it every run: open the **`Thinking Level`** combobox in the Run settings panel and select `High`, then verify it reads `High`. The capture CLI sets this automatically; when running manually, pass `--thinking high` to `finalize_markdown.py` in §8 so the provenance records it.

5b. **Long tracks (10+ clips): raise Maximum output tokens.** Run settings → **Advanced settings** → `Maximum output tokens` is a number input hard-capped at `65536`; High thinking is charged against that same budget, so a 12-clip storyboard is cut mid-clip at ~8k visible tokens. The capture CLI removes the input's `max` attribute and sets `131072` through the DOM before submitting (`--max-output-tokens`, default 131072). In a manual run, expand **Advanced settings**, set the input's `max` attribute and value to `131072` with native `input`/`change` events, and confirm **Get code** reports `'max_output_tokens': 131072` before submitting.
6. Close the panel via **`Close panel`**.

Element refs go stale as soon as a panel opens or closes. Re-run `browser_find` before each click instead of reusing an old ref. If Film Director is missing, stop and ask.

---

## 4. Stage and attach the audio

1. Stage a copy inside an allowed root. Always use absolute paths; never rely on cwd:

   ```bash
   mkdir -p ~/Documents/comfy_music_video/.upload_tmp
   cp -- <audio> ~/Documents/comfy_music_video/.upload_tmp/
   ```

2. Click **`Insert images, videos, audio, or files`** → menu item **`Upload files`**. A file chooser modal opens (the tool reports `Modal state: [File chooser]`).
3. Call `browser_file_upload` with the staged **absolute** path.
4. Verify the attachment chip shows the filename and the duration (e.g. `0:51`). A token count may also appear — record it if present, but do not require it.

If you get `File access denied` or `ENOENT`: the path is outside the allow-list or the filename is mistyped. Fix the path — do not retry the same call. If no `[File chooser]` modal state appears after clicking `Upload files`, re-find and re-click the menu item once; if it still does not open, stop and report.

---

## 5. Compose the prompt

Fill the textbox **`Enter a prompt`** with the **creative ask only**:

- **Default — send exactly `give me a good script for this soundtrack`.** This is a standing user instruction for Gemini runs: do not ask the user for a prompt and do not embellish or vary it.
- If the user dictates different exact prompt text in the current run, send that **verbatim** without embellishment.
- Always strip local paths, filenames, preset names, and save/format instructions. Those are instructions to you, not to the cloud model.
- Do not append format instructions, a `Project Title:` line, or clip-length demands. The Film Director preset controls structure.

---

## 6. Submit and wait for the 1st response

1. Submit by clicking the **`Run`** button. **Enter alone does not submit** — it inserts a newline, and `Run` can remain disabled while the audio finishes registering. (`Ctrl+Enter` also works once `Run` is enabled.) Before clicking, read the composer's `.value` and confirm it is non-empty — an empty submission still queues and produces an empty model turn.
2. Verify: your prompt appears as a user turn with the audio chip attached, and an assistant turn starts streaming.
3. **One-turn flow:** do **not** send a follow-up. The **1st response** is the first model turn with substantive answer text — the Film Director storyboard (Step 1 → Step 2 → Step 3 Ref2VA). The collapsible **Thoughts** panel rendered above it is internal reasoning, **not a response**; ignore it and never count it as response #1. If the 1st response is wrong, empty, or only audio analysis, **refresh the page and rerun from §2**; never send a follow-up and never use the 2nd response.
4. Poll with `browser_wait_for` (5–10 s) then screenshot. Do not use a fixed timeout as proof of completion.
5. **Complete means all three, checked on the 1st response:**
   - the **`Stop`** button is gone
   - the response toolbar (`thumb_up` / `thumb_down`) is present
   - the final code block of the **1st** response contains `non_diegetic_music:`
   A closing fence alone is not proof — Film Director's output ends on the last clip's audio fields, so check the content, not just the fence.

Do **not** extract mid-stream — a partial 1st response looks plausible and passes a casual glance. The **`Stop`** button can flicker off while AI Studio re-renders a fenced block, so a single poll is not proof: require the **last fenced block to contain all six ref2va sections**, every clip heading to have a prompt block, and the extracted text to stay unchanged across two consecutive polls (~6 s). If the 1st is still streaming after ~5 minutes, **keep waiting**; only report if it appears stalled (no new content and `Stop` remains for an extended period). Do not extract a partial answer.

---

## 7. Extract the 1st response to a temporary dump

Read `extract_markdown.js` and pass its **entire contents** (the file is already one complete `() => { … }` expression — not just the body) to `browser_evaluate`, with `filename` so the result is written to disk:

```text
browser_evaluate(
  function: <entire contents of extract_markdown.js>,
  filename: "~/Documents/comfy_music_video/aistudio_response_md.txt"
)
```

Capture the absolute path the tool reports and confirm the dump is a non-empty JSON-quoted string that starts with the H3 storyboard (Step 1 or a project title) and contains `non_diegetic_music:`. Do not proceed on an empty or short dump.

The extractor targets the **1st substantive answer turn** — the **1st response** — and returns `''` if that turn is absent, has less than ~200 characters, or is still streaming (`Stop` present). AI Studio renders the collapsible **Thoughts** panel as its own model turn with **zero answer text** (verified in the live DOM: a Thoughts turn measured 0 characters, the answer turn 5,262), so the extractor filters to model turns that actually contain a substantive answer and takes the first one. The Thoughts panel is **not a response** — if it were counted, the real storyboard would wrongly look like "response #2". The extractor never falls back to a later response.

**Why not `innerText`:** AI Studio's rendered text includes UI chrome (`edit`, `more_vert`, `code`, `Text`, `download`, `content_copy`, `thumb_up`), flattens nested lists, and loses code fences. `document.querySelector('main').innerText` returns an **empty string** on this Angular page. The extractor selects the 1st substantive model turn → `ms-text-chunk ms-cmark-node.cmark-node` and rebuilds markdown.

**Fallback if the extractor returns `''`:**

1. Wait for the 1st response to complete, confirm you are on the right tab, and check the selector in the live DOM. Do not fall back to a later response.
2. Click the **1st response's** **Copy** button, then run `browser_evaluate` with `async () => await navigator.clipboard.readText()` **and the same `filename`** (so the result is JSON-quoted in the same dump format the finalizer expects). Verify the text starts with the H3 storyboard and contains `non_diegetic_music:` before using it — a stale clipboard otherwise.
3. If the copy is still unusable, **refresh the page and rerun the whole flow from §2**. Never ship raw `innerText`; if you must capture it to diagnose, say so explicitly.

---

## 8. Name the file, then write it

**Title.** Use the audio filename (slugified: lowercase, `&` → `and`, punctuation → spaces, spaces → `-`, collapse repeats, trim to ~60 chars). Never use `Step 1…` as the title.

**Model name.** Read it from the Run settings model button (e.g. `Gemini 3.8 Flash` / `gemini-3.8-flash`). If it cannot be read, drop the `Source:` line entirely rather than guessing or leaving a placeholder.

**Path.** Slugify: lowercase, `&` → `and`, punctuation → spaces, spaces → `-`, collapse repeats, trim to ~60 chars. Write to `~/Documents/comfy_music_video/outputs/` (`mkdir -p` it if missing). The intermediate dump stays at the repo root and is deleted in §10.

**Collision.** If the target exists, ask before overwriting. If the user declines, offer `<slug>-2.md`; do not silently reuse or rename the existing file.

**Write** with absolute paths:

```bash
python3 ~/Documents/comfy_music_video/.claude/skills/music-video-storyboard/finalize_markdown.py \
  --in ~/Documents/comfy_music_video/aistudio_response_md.txt \
  --audio /path/to/<slug>.mp3 \
  --model "<model>" \
  --thinking high \
  --out ~/Documents/comfy_music_video/outputs/<slug>.md
```

With `--audio`, the title defaults to the slugified audio filename and the provenance block is generated automatically: `Input: <filename> (<duration>)` (via `ffprobe`), `Prompt: "give me a good script for this soundtrack"`, `AI Studio response: 1st`, and `System instructions preset: Film Director`. The `Source:` line is written only when `--model` is supplied. `--thinking high` adds `Thinking level: High` (the capture CLI passes it automatically). Pass `--title` or repeat `--source` to override; without `--audio` the original manual form (title + source lines) still works.

The finalizer decodes the JSON dump, refuses captures under 200 chars or with unbalanced fences or without a Step 3 prompt field (`integrated_multimodal_description` or `detailed_description`), and prepends the title/provenance/`---` header. Exit code 1 or a clip-count warning means **re-extract** — never hand-fill a missing section or edit the model's wording.

---

## 9. Verify before reporting

Read the file back and check:

- Title + provenance block + `---` present.
- Every clip is present: the number of `Clip` headings equals the number of Step 3 prompt fields (`integrated_multimodal_description:` or `detailed_description:`, exactly one per clip); code fences balanced.

  ```bash
  grep -ciE '^#{3,4} +Clip' ~/Documents/comfy_music_video/outputs/<slug>.md
  grep -cE '(integrated_multimodal_description|detailed_description):' ~/Documents/comfy_music_video/outputs/<slug>.md
  ```

- The last timecode matches the audio duration within ~1 s (whole-second rounding: a 51.4 s track ending at `00:51` is correct).
- No UI chrome words leaked into the body.

If a clip is missing or a warning fired, re-extract. Never hand-edit the model's content to fill the gap.

---

## 10. Clean up and report

- Delete the staged audio file by **absolute path** (not the whole directory) and `aistudio_response_md.txt`; `rmdir .upload_tmp` only if it is empty. Do this on failure paths too — do not leave the audio copy in the repo.

  ```bash
  rm -f ~/Documents/comfy_music_video/.upload_tmp/<staged-audio> \
        ~/Documents/comfy_music_video/aistudio_response_md.txt
  rmdir ~/Documents/comfy_music_video/.upload_tmp 2>/dev/null || true
  ```

- Report the file path, clip count, and the audio filename used as the title (slugified).
- Mention that the chat is Temporary (unrecoverable once closed, uploads persisted to Drive).
- Leave the tab open unless the user asks otherwise.

---

## 11. Failure playbook

| Symptom | Action |
|---|---|
| Audio missing or not real audio | Stop and ask; never substitute silently. |
| Film Director preset absent | Stop and ask; never substitute another preset. |
| `File access denied` / `ENOENT` | Path outside allow-list or mistyped. Stage into an allowed root and fix the path; do not retry the same call. |
| No `[File chooser]` modal | Re-find and re-click `Upload files` once; if still absent, stop and report. |
| `Run` disabled after typing | Wait for the audio chip to finish registering; click `Run`, not Enter. |
| 1st response still streaming | **Keep waiting.** Only report if it appears stalled (no new content and `Stop` remains for an extended period). Do not extract partial. |
| "Thoughts" panel mistaken for the 1st response | The Thoughts panel is **not a response** — it is internal reasoning shown above the answer and contains no answer text. The 1st response is the substantive turn below it (Step 1…). Do not count Thoughts as response #1 or the storyboard as #2. |
| Extracted the 2nd (or later) response | Only the **1st substantive response** is valid. Re-extract the 1st substantive model turn; if it is unusable, refresh the page and rerun from §2. Never ship the 2nd. |
| 1st response is wrong, empty, or only audio analysis | **Refresh the page and rerun the whole flow from §2.** Do not send a follow-up turn and do not use the 2nd response. |
| Extractor returns `''` | Wait for the 1st response to complete, then check tab/response/selector; use the **1st response's** Copy + clipboard fallback with the same `filename`; verify `non_diegetic_music:`; if still unusable, refresh and rerun from §2. |
| Finalizer exit 1 | Re-extract. Never hand-fill. |
| Finalizer warns clip count ≠ prompt count | Re-extract. Do not ship a missing clip. |
| UI chrome in the body | Re-extract with the DOM serializer; never clean it by hand. |
| Wrong turn or wrong preset | Finalizer refuses without a Step 3 prompt field (`integrated_multimodal_description` or `detailed_description`). Re-extract the 1st substantive model turn; if it is genuinely not a storyboard, refresh the page and rerun from §2. Never fall back to the 2nd. |
