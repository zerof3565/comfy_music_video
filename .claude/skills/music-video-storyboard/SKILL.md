---
name: minimax-h3-storyboard
description: Use when the user wants a plan/script for a Minimax H3 video from any input — an idea, short prompt, reference image, or video-analysis breakdown — and optionally wants the final video rendered. Turns the input into a non-visual storyboard (timed shot list + camera + action) plus ready-to-paste Minimax H3 generation prompts for every segment; generates pre-production reference images (characters, environment, props) with the Z-Image Turbo workflow; then hands the storyboard, reference images, and ref2va prompts to the user. Can also load the reference images into the H3 workflow and run the render itself (see Step 8).
---

# Minimax H3 Storyboard

You turn a raw input (an idea, a one-line prompt, a reference image, or a detailed video-analysis document) into two deliverables the user can act on immediately:

1. **A non-visual storyboard / script** — a timed shot list describing what happens, how the camera moves, and how segments connect. No rendered imagery, just the structural plan.
2. **One Minimax H3 generation prompt per segment** — each segment written as a self-contained **full-reference (ref2va) rewrite** (see `_ref2va_rules.md`) and ready to paste into an image-to-video / text-to-video job, with continuity baked into the reference labels.

> **Input source in this repo.** When the input is an audio track, the storyboard comes from Google AI Studio with the **Film Director** system-instruction preset. Extract the **1st response** — the first model turn with substantive answer text (the Step 1–3 Ref2VA storyboard). The collapsible **Thoughts** panel shown above it is internal reasoning, **not a response** and never the deliverable; do not count it as response #1 or the answer as #2. **Never use the 2nd or any later response.** If the 1st response is wrong, empty, or only audio analysis, refresh the page and rerun the whole flow; do not send a follow-up. Full UI procedure: `_manual-fallback.md` §2–7 and `memory.md` §3. Then continue with the storyboard JSON, reference sheets, and H3 render below.

> **FORMAT ENFORCEMENT (100%, no exceptions).** Every final per-segment prompt MUST be written in this exact format, 100% of the time, for every segment:
>
> ```text
> subject_definitions:
> <Subject 1> is …
> <Picture 1> is …
>
> summary:
> [task-type prefix] …
>
> retention_analysis:
> <Subject 1> (appears in [Shot 1]): fully_preserved - …
>
> detailed_description:
> <style opening>
> [Shot 1] …
>
> overall_soundscape:
> <fully described ambience + foley>
>
> non_diegetic_music:
> <fully described score, or N/A only if deliberately silent>
> ```
>
> The six sections above MUST appear in **exactly this order** with **exactly these labels** — `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`. Do not reorder, rename, drop, or split any section, and do not insert extra sections before or between them. Sound is **mandatory and must be fully described** (see §5.5). The worked example in §5.7 is the canonical template; `_ref2va_rules.md` holds the authoritative label/wording rules.

> **One prompt per SEGMENT, never per BEAT.** A **beat** is a single short timed event — one location change, one gesture, one music hit (e.g. a 0.5–1s beat in a hyper-lapse). A **segment** is one H3 generation unit, 12–15s long, and is the ONLY unit that gets a prompt. When a concept packs many beats into a segment (a travel hyper-lapse, a montage, a beat-synced cut-fest), do **not** write one prompt per beat — write ONE prompt per segment and chain the segment's beats inside that single prompt as internal `[Shot N] At MM:SS.mmm, …` markers with hard/whip cuts between them. The storyboard's `segments[].beats` array records those internal beats so the single segment prompt can compress them; the final deliverable is still one prompt per segment.

You **DO** generate the pre-production reference **images** (characters, environment, props) with an image model, then hand those images and the finished storyboard/refs2va prompts to the user to feed into H3 image-to-video. When the user wants the final video, you also load the reference images into the H3 workflow and run the render yourself — see **Step 2.1** for how to render the sheets and **Step 8** for how to load them and execute the H3 job.

**Full pipeline (a–z).** The complete flow, in order:
1. **Intake** (§0) — classify the input (idea / reference image / video-analysis doc).
2. **Resolve parameters** (§1) — duration, aspect ratio, generation strategy (one-take vs stitched), references.
3. **Pre-production references** (§2) — count the inventory, lock identity/look/props.
4. **Create reference images** (§2.1) — render character / environment / prop sheets with Z-Image Turbo and stage them into ComfyUI `input/`.
5. **Storyboard blueprint** (§4) — JSON shot list + camera + continuity manifest.
6. **ref2va prompts** (§5) — one fully-formatted prompt per segment.
7. **Outputs** (§6) — write `<slug>-storyboard.json` / `<slug>-storyboard.md`.
8. **Execute the H3 render** (§8) — load the reference images into `minimax_h3_api.json` (or run `render_h3.py`), set the prompt/duration/aspect, POST the job, save each segment mp4. Only do §8 when the user wants the final video.
9. **Stitch into the final video** (§9) — concatenate the segment mp4s with ffmpeg into `outputs/<slug>.mp4` and verify duration/aspect. Only do §9 when the user wants the final video.

Read these companion files before writing anything:

- `_techniques.md` — Minimax H3 capabilities, camera vocabulary, prompt structure, consistency strategies, and negative-prompt patterns.
- `_ref2va_rules.md` — the **Full-Reference Mode Rewrite (ref2va) output format**. Every segment prompt is written in this format: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`, using `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` reference labels. Read it before writing any segment prompt.
- `_z_image_turbo_rules.md` — the **prompt rules for the Z-Image Turbo image model** used to render the reference sheets. One fluid affirmative prose paragraph (no negations), 150–250 words, ordered [Subject & Wardrobe] → [Action & Pose] → [Environment & Lighting] → [Camera Optics & Film Style]; never embed `--ar`. Read it before writing any reference-sheet prompt.
- `z_image_turbo.json` — the **ComfyUI workflow (a two-stage Z-Image Turbo cascade)** used to render the reference images. POST a modified copy to the running ComfyUI at `http://127.0.0.1:8188` (swap the sheet prompt into node `7875` and the sheet's resolution into node `7884`). Read it before generating any sheet image.
- `build_storyboard.py` — **agnostic builder** from the finalized markdown to the JSON blueprint. `python3 -I build_storyboard.py --md outputs/<slug>.md --out outputs/<slug>-storyboard.json --audio outputs/<slug>.mp3 [--aspect-ratio 9:16] [--character-file ...] [--env-file ...] [--prop-file ...] [--overrides overrides.json]`. It copies the six ref2va sections verbatim and extracts Step 1/2/3 structure; Step 1 sheets may be an H4 + fenced block, any fenced block, a blockquote block, or bulleted key/value lines, and clip headings may be `#### Clip 1` or `#### Clip [1]`. `--overrides` deep-merges authored prose (concept, camera, continuity, quality) into the derived JSON.
- `render_sheets.py` — **CLI** for the Step 2.1 sheet renders. `python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json [--dry-run] [--dump-graph DIR] [<sheet-stem> ...]`. It reads every sheet's prompt/key_frame_file from the storyboard JSON, POSTs `z_image_turbo.json`, polls /history, downloads the PNG, and stages it into ComfyUI `input/`. No hardcoded sheet list.
- `render_h3.py` — **CLI** for the Step 8 H3 render. `python3 -I render_h3.py --sb outputs/<slug>-storyboard.json [--audio ...] [--audio-offset 0] [--audio-start-mode storyboard|cumulative] [--ref NODE=FILE] [--ref-image-size match|max] [--slug ...] [--aspect 9:16|16:9] [--trim-duration 20] [--dry-run] [--dump-graph DIR]`. It reads each segment's `ref2va` from the storyboard JSON, auto-derives refs/prefixes/audio from the SB filename, sets prompt/duration/aspect/ref-images/audio-window/SaveVideo-prefix, POSTs, polls, and saves `outputs/<prefix>.mp4`. Refs are ordered first-character, first-environment, first-prop, then the remaining sheets; the first four use nodes 153–156 and extras get auto-created 9001+ nodes, with unused `ref_image_N` wires pruned.
- `_manual-fallback.md` — the manual AI Studio capture SOP (§1–§10) and failure playbook; use it when `aistudio_storyboard.py` fails. The automated capture is the default path.

---

## 0. Intake — classify the input

Determine which input type you were given and adapt:

- **Audio track / music** — run it through Google AI Studio (Film Director preset, creative ask only) and extract the **1st substantive response** as the storyboard (see the repo note above; never use the 2nd response). The track's duration sets the target duration, and its lyrics drive the lip-sync and sound sections.
- **Idea / short prompt** — a concept in the user's own words. Extract genre, subject, mood, key action. Fill gaps with sensible defaults and ask the user for the few things that change a storyboard most (see step 1).
- **Reference image** — read the image, describe the subject, style, composition, palette, lighting, and character. Treat everything visible in the image as the source of truth for look and identity.
- **Video-analysis document** (e.g. a shot-by-shot breakdown of an existing video, possibly in another language) — treat it as a spec. Extract its timeline, camera moves, style, negative list, and sound design, then reframe them for Minimax H3. Preserve the original intent; translate to prompts.

If multiple inputs arrive together (e.g. an idea + an image), combine them: the image locks the look, the idea supplies the action.

## 1. Resolve the few parameters that matter most

If the input does not already state them, ask the user (use AskUserQuestion) for:

- **Target duration** (e.g. 10s, 30s)
- **Aspect ratio** (e.g. `9:16`, `16:9`, `1:1`)
- **Generation strategy** — one continuous "one-take" shot vs. multiple stitched segments. Default to **stitched-segments**: H3 generates per clip and cannot produce a single long continuous take (a 30s continuous shot is impossible — it will fail or loop). The per-clip generation cap is **15s**, so aim each segment at **12–15s** (settling to **10–14s** only when the beat can't sustain 15s) and stitch. Never build throwaway **2–3s segments** — push to the max. Only use `one-continuous-shot` when the total duration fits within a single per-clip cap (~15s or less). If the source requests a single continuous take but the total duration exceeds one clip, set `generation_strategy: "stitched-segments"` and treat "one continuous take" as the **visual intent** — implement the seamless *look* with shared reference images and cinematic cuts between segments (see Step 2), never by first-frame/last-frame conditioning, and never as a single generation.
- **Reference image availability** — is there a reference image to keep character/look consistent across segments?
- **Beats vs segments** — how many beats pack into each segment? For a concept with many short beats (a travel hyper-lapse, montage, beat-synced cut-fest), decide how many beats fit in one 12–15s segment and chain them as internal cuts. The unit of generation is always the segment; beats are planned (in `segments[].beats`) and then compressed into one prompt per segment. See step 5.

If the input already gives these (as the ink-wash example does: 30s, 9:16), do not re-ask; just confirm the defaults you used at the end.

Default segment length: keep each segment within Minimax H3's 15s per-clip limit, aiming for **12–15s** and settling to **10–14s** when the beat can't sustain 15s, and cap each clip so it stays a single coherent take. Because a long continuous take is not possible, produce the video as multiple stitched segments unless the total duration is short enough for one clip (~15s or less). When splitting a requested "one-take" video, the `generation_strategy` field must read `stitched-segments`; the continuity between the stitched clips is then carried by shared reference images (locked identity/look) and **cinematic cuts between segments** — never by first-frame/last-frame conditioning — not by any single generation.

## 2. Pre-production — lock references (identity, environment, props)

Continuity is the hard part of generating separate segments and stitching them. Decide how each subject stays identical across every clip:

- **Always lock references — never skip.** Every storyboard generates full pre-production reference sheets for characters, environments, and props, regardless of length or complexity. Even a single-segment or "simple" clip needs them; without them the locked identity/look drifts between clips.
- **Reference images are the anchor.** Determine whether references already exist (user-provided, or mandated by the source material — e.g. a brief that says "follow the uploaded reference images") or need generating. Even when user-provided references exist, still produce a sheet entry for every subject so the inventory is complete; cite the provided image as the source.
- **Determine the inventory up front — count everything before generating any sheet.** State explicitly, in the blueprint, how many of each there are, then make sure the matching sheet arrays contain exactly that many entries (no more, no fewer):
  - **Characters** — every named/visible person, creature, or recurring subject.
  - **Props** — every actively-used object (weapons, accessories, hand props, etc.).
  - **Locations** — every distinct setting/scene.
  Record these counts in `references.inventory` (`character_count`, `prop_count`, `location_count`) and cross-check them against `character_sheets`, `prop_sheets`, and `environment_sheets`.
- **Always generate all three sheet types with an image model** (H3 is a video model — it consumes references, it doesn't make them). The skill writes the prompts; you generate the images. Produce:
  - **Character turnaround sheet(s)** — one per character: front / 3/4 / side / back + signature expressions, exact locked wardrobe, neutral background. Biggest identity win.
  - **Environment key frame(s)** — one per location: the setting once, locking lighting, palette, era.
  - **Prop sheet(s)** — one per prop, from multiple angles, so they don't morph between segments.
- **Reuse the identical reference image in every segment** that features a subject; feed it as the starting frame / reference. If the tool has a reference-strength/weight, use high weight for character-locked shots.
- **Join segments with cinematic cuts, NOT first-frame conditioning.** Do not feed segment N's final frame into segment N+1 as its start frame — chaining clips frame-to-frame compounds drift and degrades the chain. Instead plan an intentional cut (j-cut / l-cut / straight-cut / match-cut) on a *contrasting* composition: end each segment on one framing/angle and open the next on a different one (e.g. end on a medium close-up, open the next on a wide / side profile / low angle). See `_techniques.md` §5C for the full method. Continuity across the chain is carried by shared reference images (locked identity/look) and the editing rhythm, not by frame-matching.
- **Record a continuity manifest** (subject → reference file → segment IDs that reuse it → weight). It lives in the blueprint (`references` + `continuity_manifest`) so the generator never guesses which image to reuse.

See `_techniques.md` §5 for the full ranked method and the prompt-based locking that backs it up.

### 2.1 Render the reference images with Z-Image Turbo (mandatory)

The sheets in Step 2 are **not optional prose** — you must actually produce the image files before the user can submit an H3 job. H3 consumes reference images; it does not create them, and the storyboard's `<Subject N>` / `<Picture N>` labels cite the sheet filenames, so missing files mean the prompt is un-pasteable. Do this:

1. **Start ComfyUI** if it is not already running: `cd ~/Documents/comfyui && python main.py` (it serves `http://127.0.0.1:8188`). Confirm it is up with `curl -s http://127.0.0.1:8188/system_stats` before proceeding.
2. **Write each sheet prompt in Z-Image Turbo style** — read `_z_image_turbo_rules.md`. Each prompt is one fluid affirmative prose paragraph (150–250 words), ordered [Subject & Wardrobe] → [Action & Pose] → [Environment & Lighting] → [Camera Optics & Film Style], with **zero negations** and never embedding `--ar`.
3. **Render via `render_sheets.py`** — do NOT hand-POST each sheet. Ensure each sheet's `generation_prompt` and `key_frame_file` are in the storyboard JSON, then run `python3 -I render_sheets.py --sb outputs/<slug>-storyboard.json` (sheets are always 16:9 ≥2 MP → `1920×1080`; override with `--width/--height`). It loads `z_image_turbo.json`, sets the prompt in node `7875` and resolution in node `7884`, POSTs, polls `/history`, downloads the PNG, and stages a copy into ComfyUI `input/`. Run one sheet with `... --sb ... <name>` to save GPU time, or `... --dry-run` to validate the selection without GPU work. (The cascade is GPU-bound — allow several minutes per sheet.)
4. **Stage every sheet into ComfyUI's `input/`** (`~/Documents/comfyui/input/`) before any H3 job — `LoadImage` can only read from there, and the path is `~/Documents/comfyui/input` (NOT a `comfyui/` dir under the project). `render_sheets.py` does this automatically and creates the dir if missing. Also keep a copy in the project `outputs/` under the storyboard's canonical filename (e.g. `character_figure_front.png`) so the storyboard and continuity manifest cite files that actually exist.
5. **Feed the rendered images to H3** as starting frame / reference: **high** weight for characters, **medium** for environments, **low** for props. Cite the rendered filename inside each `<Subject N>` / `<Picture N>` label.
6. **Verify before finishing.** Confirm each expected sheet file exists and is a valid PNG (not an error/blocked page). If a sheet fails, retry it once; if it still fails, tell the user which sheet and why. **Do not hand off an H3 job with a missing reference** — the prompt is only paste-ready once its images exist.

## 3. Research (optional, degrade gracefully)

When it will improve the result, research what others are doing for the target genre/style and borrow their techniques:

- Run `WebSearch` for the genre + style + Minimax H3 / Hailuo prompt techniques.
- If a promising page appears, `WebFetch` it to extract concrete prompt structures, camera moves, and negative-prompt patterns.
- Use the Playwright MCP (`mcp__playwright__browser_*`) to open galleries, examples, or writeups and snapshot them.
- **If research returns nothing** (empty results, connection failures), do not block — proceed using the established techniques in `_techniques.md`. Note in the output that research was unavailable.

Record the techniques you adopted (with source URLs) in the output so the user knows what was borrowed.

## 4. Build the JSON storyboard blueprint

Produce a structured JSON blueprint that is the machine-readable plan. Follow `_storyboard-schema.json`.

For the audio → AI Studio pipeline, generate the base blueprint mechanically with `build_storyboard.py` (see its bullet in the companion-file list), then refine run-specific prose through `--overrides` rather than hand-editing the JSON. The ref2va blocks must remain verbatim from the 1st response; overrides are for the surrounding blueprint fields only.

**Snap segment durations before rendering.** `--extend-last` fixes only the final clip; H3 still snaps every requested duration to a valid frame count (frames ≡ 5 mod 17 at 24 fps). If clip 1's JSON duration is e.g. `10.0` (which renders as 243 frames = 10.125 s), clip 2's `start` is 0.125 s early relative to the rendered timeline and its audio window drifts. Override each segment's `start`/`end`/`duration`/`timecode` in `--overrides` to the snapped values so the H3 audio windows and the stitched timeline agree. For a single-segment short track, choose the largest valid length that covers it (e.g. a 13.032 s track uses **12.958 s = 311 frames**; a 12.0 s request would snap to 12.25 s = 294 frames and cut ~0.8 s of music).

Required content:

- `project`: source, concept, genre, visual_style, mood, target_duration_seconds, aspect_ratio, generation_strategy, segments_count, reference_image, primary_objective.
- `subject_continuity`: each character's canonical description + consistency notes; a style-lock line; palette; world rules. This is what keeps the character/look identical across every segment.
- `references`: pre-production reference sheets generated with an image model — `character_sheets`, `environment_sheets`, `prop_sheets`, plus an `inventory` object stating `character_count`, `prop_count`, `location_count` (determined up front — see Step 2). Each sheet entry has a `generation_prompt` (the prompt to make the sheet), a `key_frame_file` (the chosen frame fed to H3), `views`, and `source` (`generated` or `user-provided`). The sheet arrays must each contain at least the inventory count for their type.
- `continuity_manifest`: a table mapping each subject → reference file → segment IDs that reuse it → reference weight. This is what ties the segments together.
- `segments`: ordered list. Each segment gets `id`, `timecode`, `start`/`end`/`duration`, `narrative_purpose`, `action`, `character_blocking`, `camera` (angle, size, move, notes), `motion` (primary), `secondary_motion`, `lighting`, `transition_in`, `transition_out`, `cut` (the cinematic edit — j-cut/l-cut/straight-cut/match-cut — joining this segment to the previous one, with its `composition_plan` of what it ends on vs. what the next opens on), `sound_cue`, `focus_hierarchy`, `reference_image` (the reference file reused for this segment, or null).
- `continuity_requirements`, `quality_priorities`.
- `assumptions_and_defaults` and `open_questions`: be explicit about anything you invented or left open.

Planning rules (adapt from the proven rules in `_techniques.md`):

- Every timestamp must be numerically consistent and fit the target duration.
- Every segment must serve a purpose; no filler or dead static shots.
- One clear focal point per segment; avoid competing focal points.
- Motion from the first frame — no slow build-ups unless the concept calls for them.
- Keep each segment's action simple enough for the model to render in one take.
- Lock identity, wardrobe, lighting direction, and world rules across all segments.
- Distinguish primary action from secondary motion (hair, fabric, particles, environment).

## 5. Generate one ref2va prompt per segment

Each segment is written as a **self-contained full-reference (ref2va) rewrite** in the format defined by `_ref2va_rules.md`. Every segment prompt carries exactly these six sections in this exact order, so it is independently ready to paste into an image-to-video / text-to-video job (this is the 100%-enforced format from the callout above):

1. `subject_definitions` — one line per reference label used in this segment.
2. `summary` — one paragraph beginning with a square-bracketed task-type prefix.
3. `retention_analysis` — one line per label with a fixed relationship marker.
4. `detailed_description` — style opening + shot-by-shot playback order, with reference labels, speaker IDs, and `<d>` dialogue.
5. `overall_soundscape` — ambience and physical sounds (fully described — see §5.5).
6. `non_diegetic_music` — audience-only background score, fully described (see §5.5).

Read `_ref2va_rules.md` for the exact wording, label rules, speaker rules, and the complete worked example. The mapping below is how those rules apply to a storyboard segment.

### 5.0 Composing one segment prompt from many beats (montage / hyper-lapse)

When a segment holds **many beats** (e.g. a travel hyper-lapse where each beat is a new location + outfit at ~0.5–1s), the rule is still **one prompt per segment**. Compress the segment's beats into that single prompt like this:

- **One `detailed_description`, many internal shots.** Write a single `detailed_description` for the whole segment. Mark the opening `[Shot 1]` (no timestamp); mark each subsequent beat as `[Shot N] At MM:SS.mmm, …` with the timestamp **relative to the segment's own start (0:00)**. Use whip cuts / hard cuts between beats so the location-and-outfit change reads as an intentional edit, not a morph.
- **Keep the identity label stable across the beats.** The character is `<Subject 1>` in every beat; restate the locked face/identity once in `<Subject 1>`'s definition and restate the current beat's outfit inline in that beat's shot line (e.g. "now wearing a …"). Do **not** create a new `<Subject N>` per beat for the same person — that invites face/identity drift.
- **Chain on contrast, not on frame-matching.** End each internal beat on a framing and open the next on a contrasting one (close → wide, left → right, static → whip) so the rapid cuts stay legible. The whip/blur of the transition hides the outfit change.
- **Scale the length to the segment, not to the beat count.** The `detailed_description` is a ~12–15s clip's worth of description — focused and complete, not the full 350–500 word whole-video rewrite. Distribute a sentence or two per beat; dense montages get shorter per-beat lines.
- **Don't overstuff.** Cap the beats a single H3 take can render cleanly (face stable, each outfit/landmark legible). If the concept needs more beats than one 15s segment can hold, add another segment (another prompt) rather than padding one prompt past its cap.

The `segments[].beats` array is where these internal beats are recorded (time offset, location/event, action, outfit) so the single segment prompt can be compressed from it. The final deliverable stays **one prompt per segment**.

### 5.1 Assign reference labels for this segment

Labels are scoped to the segment: each segment re-labels its own content. Assign per the rules, adapting to what the storyboard provides:

- **`<Subject N>`** — every visible subject that is actually used in this segment: the character(s), creature(s), the environment treated as a subject, and key props that are actively used. **Cite the reference-image source inside the definition** when the look is locked from a pre-production sheet, e.g. `<Subject 1> is the swordsman in `character_sheet_A.png`, long black hair in a white robe held by a black belt, gripping a single straight sword, fixed athletic proportions.` This is the replacement for the old "continuity anchor + prepend the reference image" step — the identity line from `subject_continuity` becomes the `<Subject N>` description, and the continuity manifest's reference file becomes the cited source.
- **`<Picture N>`** — only when a reference image is a concrete frame anchor for this segment: a **provided reference image that *is* the segment's first frame**, or the environment key frame that sets the opening composition. Do **not** use `<Picture N>` to carry segment-to-segment continuity — that is now handled by cinematic cuts + shared references, never by feeding one clip's final frame into the next. For segment 1 with no prior clip, anchor on the environment key frame if it sets the first frame, else omit `<Picture N>` entirely. Do **not** create a standalone picture for an image that only defines a character/scene/costume — that stays inside the `<Subject N>` definition.
- **`<Video N>`** — not applicable to a pure storyboard generation (no source video is edited or continued). Add it only when the input is a video-analysis being *continued* or structurally referenced.
- **`<Audio N>`** — only when a source audio signal is copied or referenced. A storyboard's sound is **designed for H3 to generate**, not copied from a source, so **do not** create `<Audio N>`; describe the designed ambience/score in `overall_soundscape` / `non_diegetic_music` instead.

Give each label a stable meaning within the segment and reuse it without redefining.

### 5.2 `summary` task-type prefix

Combine the task types that actually apply, in brackets, joined with ` + `, no repeats:

- Reference images define the subjects → `[reference generation]`.
- A provided reference image *is* the segment's first frame / sets the opening composition → `[keyframe completion]`.
- Both active → `[reference generation + keyframe completion]`. Segment 1, which has no prior clip and no first-frame anchor, is just `[reference generation]`.
- Source is a video continued/edited → add `[video continuation]` / `[video editing]` as appropriate.
- **No `audio reference`** unless a source audio signal is actually copied or referenced (a designed soundscape is not).

### 5.3 `retention_analysis`

One line per label, reusing the meaning from `subject_definitions`, with the fixed markers from the rules:

- Visible (`<Subject N>`, `<Picture N>`): `fully_preserved` (the reference image's locked look is carried into the segment — the default), `partially_preserved`, `attribute_transfer`, or `weak_reference`.
- Format: `<Subject 1> (appears in [Shot 1]): fully_preserved - the locked face, long black hair, white robe, and straight sword from `character_sheet_A.png` are retained.` and `<Picture 1> ([Shot 1] first frame): fully_preserved - the moonlit ink-mist composition is carried into the first frame.`
- Do not treat newly added actions or sounds in the segment as losses of reference fidelity.

### 5.4 `detailed_description`

- Open with one or two sentences establishing the **locked visual style** (medium, palette, lighting, render quality), copied from `subject_continuity`.
- Mark the opening shot `[Shot 1]` (no timestamp). If the segment has internal cuts, mark later shots `[Shot N] At MM:SS.mmm, ...` with timestamps **relative to the segment's own start** (0:00), not the whole-video timecode.
- Insert reference labels at their first clear appearance and reuse them; describe referenced characteristics, frame position, and current action within what is visible.
- Use concrete frame-anchor phrasing: `the shot begins from <Picture 1>`, `the shot's keyframe corresponds to <Picture 2>`, `the shot ends on <Picture 3>`.
- Assign `(S1)`, `(S2)`, … to vocal sources by order of vocal event; write dialogue/lyrics as `<d>[Language] …</d>`. When a referenced subject physically speaks, write `<Subject N> (Sx)`. Dialogue/lyrics live only in `<d>`; the full music and foley that accompanies it is described in the `overall_soundscape` / `non_diegetic_music` sections, which Minimax H3 generates together with the video (see §5.5).
- **Length:** each segment is a ~12–15s clip, so write a complete but focused description scaled to the segment's information load — roughly one to two shots' worth, not the full 350–500 word range, which is for a whole-video rewrite. Distribute detail by information load; a single shot does not force a shorter description, but a single clip does not need a full-video length either. For a **multi-beat segment** (hyper-lapse / montage), write a sentence or two per beat and keep each beat's line short — the description is scaled to the ~12–15s clip, never to the number of beats.
- Keep motion as a cause-and-effect chain (primary action → fabric → hair → accessory → environment → camera), and never invent events that contradict the blueprint.

### 5.5 Sound sections — describe music and foley in full

Minimax H3 can generate music **and foley together with the video**, so these two sections are **generation instructions, not post-production references**, and they must be **fully described** — never terse, and never `N/A` when the segment has sound:

- `overall_soundscape` — the in-world ambience and physical sound effects H3 should generate: room tone, wind, the sword ring, fabric rustle, footsteps, churning ink, etc. State what is heard, its texture and level, and where each sound enters and exits.
- `non_diegetic_music` — the audience-only score H3 should generate: instrumentation, tempo, dynamics, and development; use `N/A` only when the segment is deliberately silent.
- Because H3 mixes both layers into the clip, write each section complete enough that the intended music and foley could be produced straight from it. Do not repeat full dialogue/lyrics here — they live only in `<d>` inside `detailed_description`.

### 5.7 Worked example (segment 1 of the ink-wash storyboard)

```text
subject_definitions:
<Subject 1> is the cold-expression female swordsman in `character_sheet_A.png` — long black hair in a white robe held by a black belt, gripping a single straight sword, fixed athletic proportions.
<Picture 1> is the first frame of [Shot 1], the environment key frame `env_moonlit_ink_A.png`: the full moon half-swallowed by churning ink mist over a still ink sea.

summary:
[reference generation + keyframe completion] The segment opens on <Subject 1> in a moonlit ink-wash landscape anchored by <Picture 1>, as her eyes open and she flicks the tsuba so ink bursts from the blade like wild cursive calligraphy.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - the locked face, long black hair, white robe, black belt, and straight sword from `character_sheet_A.png` are retained.
<Picture 1> ([Shot 1] first frame): fully_preserved - the moonlit ink-mist composition and negative-space layout are carried into the first frame.

detailed_description:
Pure Chinese black-and-white ink-wash on 宣纸 rice paper — 留白 negative space, dry-brush, burnt-ink, flying-white speed trails, churning ink mist, and a full moon; every slash and particle is calligraphic ink, never CG.
[Shot 1] A low-angle close-up rushes to an extreme close-up on the hilt and half-drawn blade as <Subject 1>'s eyes snap open and her thumb flicks the tsuba; the blade rings and a single silver light sweeps the edge. Ink bursts out like wild cursive calligraphy and the ink spirit beast awakens in the same instant while the full moon is swallowed and spat by ink mist. Hair and sleeves already dance from the first frame. The push-in is sharp and sudden, keeping <Subject 1>'s face, costume, and weapon crisp against deep negative space.

overall_soundscape:
A low drum pulse under a sword ring and churning ink texture; no vocals.

non_diegetic_music:
War drums and low bass rise with the ink burst.
```

Note how the old "continuity anchor + prepend the reference image" became `<Subject 1> … in `character_sheet_A.png``; the first-frame anchor became `<Picture 1>`; the style line became the `detailed_description` opening; and the sound is now fully described in the two sound sections. Because Minimax H3 generates music and foley together with the video, `overall_soundscape` and `non_diegetic_music` are complete generation instructions here — not terse, not `[post-prod reference]` tags, and not `N/A` when sound exists. (Segment-to-segment continuity is now handled by cinematic cuts + shared references, not by feeding one clip's final frame into the next.)

## 6. Write outputs and present

Save the artifacts so the user can reuse them, then present inline:

- `outputs/<slug>-storyboard.json` — the JSON blueprint.
- `outputs/<slug>-storyboard.md` — the human-readable storyboard plus each segment's prompt in a copyable block.
- `outputs/<slug>.mp4` — the rendered H3 video, if you ran the render (Step 8).

`<slug>` = lowercase, hyphenated concept (e.g. `ink-wash-swordsman`). If `outputs/` does not exist, create it.

In the chat reply, give:

- A one-line summary of the concept and the key decisions/defaults.
- The storyboard as a compact shot list.
- Each segment's prompt in its own copyable block.
- A short "Assumptions & open questions" note.

## 7. Final quality check

Before returning, verify:

- Timestamps are consistent and sum to the target duration.
- **One prompt per SEGMENT, never per BEAT** — the number of final ref2va prompts equals the number of segments; multi-beat segments are compressed into their single prompt as internal `[Shot N]` markers, and there is no separate prompt for any individual beat.
- **Every segment is 10–15s** (push to 15s; no throwaway 2–3s segments).
- **Every segment joins the next with a cinematic cut** (j-cut / l-cut / straight-cut / match-cut) on a contrasting composition — the `cut` object's `composition_plan` ends on one framing and opens the next on a different one. No segment uses last-frame/first-frame conditioning.
- **Every final prompt is 100% in the exact ref2va format** — all six sections present, in the exact order and labels from the callout, with no reordering, dropped, or extra sections inside/between them.
- **`overall_soundscape` and `non_diegetic_music` are fully described** in every prompt — music, instrumentation, tempo, dynamics, and foley/ambience stated completely, since Minimax H3 generates both with the video (never terse, never `[post-prod reference]`, and not `N/A` when sound exists).
- Character/wardrobe/style are identical across every segment and prompt.
- Each prompt is self-contained and paste-ready.
- Negative constraints target real failure modes, not a generic word dump.
- The storyboard matches the source intent (especially for a video-analysis document).
- The JSON is valid.
- If the video was rendered (Step 8), confirm the mp4 exists, is a playable file, and matches the intended aspect ratio (probe with `ffprobe`).

## 8. Load the reference images into the H3 workflow and run the render

When the user wants the final video (or explicitly asks you to "load the images and execute the H3 generation"), render it yourself. The H3 workflow JSON is `minimax_h3_api.json`; it already has the full pipeline wired (CLIP → VAE → sampling → `SaveVideo` node `447` → `output/video/claude_code/clip/`). Do this — **prefer the `render_h3.py` CLI**: `python3 -I render_h3.py --sb outputs/<slug>-storyboard.json` (add `--audio`, `--ref NODE=FILE`, `--ref-image-size match|max`, `--slug`, `--aspect 9:16|16:9`, or `--trim-duration` only when the defaults from the storyboard filename are wrong). It reads each segment's `ref2va` from the storyboard JSON and does the whole job; use `--dry-run` (optionally with `--dump-graph DIR`) to validate prompts/refs first. For the manual wiring, the node map below is the working truth for this workflow:

1. **Confirm the workflow and images.** Load `minimax_h3_api.json`. Node `7518` is `MiniMaxH3ReferenceToVideo`; its `ref_images` is an autogrow dict (prefix `ref_image_`, min 0, max 9). `ref_image_size` (`match` or `max`) controls whether source pixels are kept or resized up; `render_h3.py --ref-image-size` sets it. Confirm each reference sheet already exists in ComfyUI `input/` (Step 2.1, step 4) — `LoadImage` can only read from there. If a sheet is missing, render and stage it first.

2. **Add one `LoadImage` node per reference image.** For each sheet, add a `LoadImage` node (give it a unique id) whose `image` input is the sheet's filename (e.g. `character_figure_front.png`). Record each new node's id — you need it for wiring.

3. **Wire each LoadImage into `ref_images`.** In the workflow dict, set one entry per reference image (up to 9):
   ```python
   graph["7518"]["inputs"]["ref_images.ref_image_0"] = ["<loadnode_A>", 0]
   graph["7518"]["inputs"]["ref_images.ref_image_1"] = ["<loadnode_B>", 0]
   # … ref_image_2, ref_image_3, … up to ref_image_8
   ```
   Each value is `[LoadImage_node_id, 0]` (output slot 0 = the loaded image). The JSON key carries the dot as a literal string key (`"ref_images.ref_image_0"`). **Prune unused wires:** delete any `ref_images.ref_image_N` entry above your last used index — a leftover baked wire makes the graph expect an image the prompt does not describe, and the `<Picture N>` labels stop matching. `render_h3.py` prunes automatically; nodes `9001+` are created for references beyond the four baked into `153`–`156`.

4. **Match the prompt's `<Picture N>` labels to the ref wiring order — the most common mistake.** The node processes `ref_images` in sorted-suffix order, and each image becomes a `<Picture N>` token in that order: `ref_image_0` → `<Picture 1>`, `ref_image_1` → `<Picture 2>`, and so on. The reference tokens ride through every sampling step, so if the prompt's `<Picture 2>` describes the dog while `ref_image_1` is the environment, vision and text disagree and the image drifts. **Fix:** decide the Picture order first (e.g. Picture 1 = woman, Picture 2 = environment, Picture 3 = dog, Picture 4 = prop), assign them to `ref_image_0..3` in that exact order, then write the ref2va prompt so its `<Picture 1>` refers to the same file as `ref_image_0`, etc. Verify by listing the wiring and reading the prompt's Picture lines together.

5. **Set the prompt.** Node `6009` (`PrimitiveStringMultiline`) holds the ref2va text: `graph["6009"]["inputs"]["value"] = "<full ref2va prompt>"`.

6. **Aspect ratio only — do not touch resolution.** Node `7893` (easy boolean) controls aspect: `false` = 9:16 portrait, `true` = 16:9 landscape. `render_h3.py` defaults it from the storyboard JSON's `project.aspect_ratio`; `--aspect` overrides. The final render size is workflow-owned: node `6074` (phase-2 upscale target) feeds the phase-2a `MMH3UltimateUpscale` node `7569`, currently at `896x1568`; `render_h3.py` leaves `6073`/`6074` untouched. The phase-2b upscale chain and node `7718` were removed from the current graph. To change aspect, flip node `7893`.

7. **Set the soundtrack and its segment window.** Node `7909` (`LoadAudioPlus`, "Load Music File") reads only ComfyUI `input/`; set both `audio` and `file` to the staged soundtrack filename (copy `outputs/<slug>.mp3` there first). Node `7895` (`TrimAudioDuration`, "Music Start Index") selects the window: `start_index` = `--audio-offset` + the segment's `start` (or cumulative previous durations with `--audio-start-mode cumulative`), `duration` = `--trim-duration` (20s default). `render_h3.py` sets the audio filename (`--audio`, default `<slug>.mp3`), stages the file, and resolves `start_index` from each segment automatically; `--dry-run` prints the resolved values. For a storyboard covering a section of a long track, pass `--audio-offset` and the matching `--audio-offset` to `stitch_and_mix.py`.

8. **POST the job.** `POST http://127.0.0.1:8188/prompt` with `{"prompt": graph, "client_id": "claude_code"}`. Read the response: `"node_errors": {}` means it queued cleanly. If `node_errors` is non-empty, fix the named node and retry.

9. **Poll for completion.** `GET http://127.0.0.1:8188/history/{prompt_id}` repeatedly until the prompt id appears with an `outputs` array. H3 is GPU-bound and slow — allow many minutes (portrait clips take ~15+ min). If a poll returns a status with an `error`/`msg` field, stop and report it (e.g. OOM, invalid resolution).

10. **Save the mp4.** Node `447` (`SaveVideo`) writes `output/video/claude_code/clip/clip_XXXX_.mp4`. Copy it to `outputs/<prefix>.mp4` for that segment; the final stitched file becomes `outputs/<slug>.mp4` in Step 9. Probe it with `ffprobe` (`-select_streams v:0 -show_entries stream=width,height,r_frame_rate,nb_frames -show_entries format=duration`) and confirm the aspect ratio matches the intent. The current workflow's portrait mode returns **896×1568** (4:7), not exact 9:16; deliver the native file without a post-processing scale unless the user explicitly asks for one.

**`ref_image_size` choice** (node `7518`): `"match"` (default) scales each ref down only to the generation's pixel area — faster. `"max"` uses a 2048px short edge for best identity fidelity but is several times slower. Use `"max"` when identity fidelity matters most and the render budget allows.

**Duration** (nodes `6014` → `131`): the `length` input feeds node `131`'s expression `max(5, round(a*24)) + (5 - ...) % 17`, which snaps the frame count to a valid H3 length. Set the segment's target seconds in node `6014`.

**Environment gotchas (learned from the worked runs).**
- ComfyUI `input/` is `~/Documents/comfyui/input` — **not** a `comfyui/` folder under the project. `render_sheets.py` creates it if missing.
- Segment `id`s in the storyboard JSON are **integers** (`1`, `2`), not strings — index by order, don't assume keys.
- Node `7893` is aspect only (`false`=9:16, `true`=16:9); the resolution pickers (`6073` phase-1 composition, `6074` phase-2 upscale target) are workflow-owned — `render_h3.py` leaves them alone. The current graph renders at `896×1568`; node `7718` no longer exists.
- Reference sheets are always 16:9 ≥2 MP (`1920×1080`); H3 crops to the video aspect at render time.

## 9. Stitch the segments into the final video

A stitched-segments reel is only finished once the segments are joined into one file. Segments are joined by **cinematic cuts** (planned in each segment's `cut` field), never by frame-matching — so a plain concat is correct.

1. **Confirm the segment mp4s exist and match** (`outputs/<prefix>.mp4`, e.g. `outputs/elf_ballroom_seg1.mp4`). Probe them with `ffprobe` and confirm the same width/height/fps; if they differ, re-encode to a common profile before concat.
2. **Prefer `stitch_and_mix.py`** (hard cuts + **original soundtrack only**; H3 vocal/foley discarded by default — `--with-h3-audio` restores the old 65/35 mix):
   ```bash
   python3 -I .claude/skills/music-video-storyboard/stitch_and_mix.py \
     --slug <slug> --trim-output <track-duration-in-seconds> \
     [--sb outputs/<slug>-storyboard.json] \
     [--audio-offset <seconds>] [--dry-run]
   ```
   It keeps every frame by default — H3's fractional durations (5.875 s, 6.583 s) are intentional. Do **not** pass `--auto-trim` for H3. For multi-segment runs pass `--sb`: every clip is trimmed to its `segments[].duration`, which restores the intended music timeline when the storyboard requests whole seconds and H3 rounds each up to frames ≡ 5 mod 17 (up to +0.5 s/clip). `--trim-output` caps the final file at the track length. Pass the same `--audio-offset` used for the H3 render when the storyboard starts partway into a long track; `--dry-run` prints the ffmpeg command (verify the per-clip keep values equal the storyboard durations). One segment is accepted.
3. **Manual fallback — concatenate** with an ffmpeg list (re-encode to be robust to codec/frame differences):
   ```bash
   # List the segment prefixes — render_h3.py defaults to <slug>_segN; each ends in _segN.
   printf "file '%s'\n" outputs/elf_ballroom_seg1.mp4 outputs/elf_ballroom_seg2.mp4 > /tmp/concat.txt
   ffmpeg -y -f concat -safe 0 -i /tmp/concat.txt -c:v libx264 -pix_fmt yuv420p -c:a aac outputs/elf-ballroom-baby-dragon.mp4
   ```
   (Drop segments that don't exist; adjust the file list to match your `PREFIXES`.)
4. **Verify the finished video** with `ffprobe` — confirm total duration ≈ the sum of segment durations and the aspect matches intent. Frame-snapping can make the sum slightly longer than the track; trim the output to the track. Save it as `outputs/<slug>.mp4` (Step 6, item 1). For exact 9:16 at 1080×1920:
   ```bash
   ffmpeg -y -i <slug>.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" \
     -c:v libx264 -preset medium -crf 18 -c:a copy <slug>-9x16.mp4
   ```
