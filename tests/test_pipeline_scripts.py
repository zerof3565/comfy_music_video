#!/usr/bin/env python3
"""Smoke tests for the music-video pipeline CLIs.

Run with:  python3 -I tests/test_pipeline_scripts.py -v

The scripts are exercised as subprocesses so the tests cover the real CLI
surface (flags, defaults, exit codes) rather than importing module internals.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / ".claude" / "skills" / "music-video-storyboard"
BUILDER = SKILL / "build_storyboard.py"
FINALIZER = SKILL / "finalize_markdown.py"
SHEETS = SKILL / "render_sheets.py"
H3 = SKILL / "render_h3.py"
STITCH = SKILL / "stitch_and_mix.py"
AISTUDIO = SKILL / "aistudio_storyboard.py"
FIXTURES = REPO / "tests" / "fixtures"
MD = FIXTURES / "999doahong.md"
SB = FIXTURES / "999doahong-storyboard.json"
AUDIO = FIXTURES / "999doahong.mp3"

REF2VA_LABELS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]
LIST_SECTIONS = {"subject_definitions", "retention_analysis"}


def run(script, *args, expect=0):
    proc = subprocess.run(
        [sys.executable, "-I", str(script), *map(str, args)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            "{} exited {} (expected {})\nstdout:\n{}\nstderr:\n{}".format(
                Path(script).name, proc.returncode, expect, proc.stdout, proc.stderr
            )
        )
    return proc


def parse_ref2va_from_markdown(text):
    """Return the first Step 3 code block parsed into the six ref2va fields."""
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.S)
    block = next(b for b in blocks if b.lstrip().startswith("subject_definitions:"))
    out = {}
    for i, label in enumerate(REF2VA_LABELS):
        marker = label + ":"
        start = block.index(marker) + len(marker)
        if i + 1 < len(REF2VA_LABELS):
            end = block.index(REF2VA_LABELS[i + 1] + ":", start)
        else:
            end = len(block)
        body = block[start:end].strip()
        if label in LIST_SECTIONS:
            out[label] = [line for line in body.splitlines() if line.strip()]
        else:
            out[label] = body
    return out


STEP3_TEMPLATE = """### Step 3: MiniMax Generation Prompts (Ref2VA Full-Reference Mode)

{clip_heading}

```text
subject_definitions:
<Subject 1> is a test person.
summary:
A test sequence.
retention_analysis:
<Subject 1>: fully_preserved.
detailed_description:
A cinematic test shot with no dialogue.
overall_soundscape:
Room tone.
non_diegetic_music:
Soft piano.
```
"""


def storyboard_markdown(step1, clip_heading="#### Clip 1 [00:00 - 00:12 | Duration: 12s]"):
    """Build a minimal two-step markdown fixture around a Step 1 body."""
    return (
        "### Step 1: Visual Continuity Reference Prompts\n\n"
        + step1.strip()
        + "\n\n### Step 2: Grounded Cinematic Storyboard\n\n"
        + "- Beat one happens here.\n\n"
        + STEP3_TEMPLATE.format(clip_heading=clip_heading)
    )


MINIMAL_STORYBOARD = """### Step 1: Visual Continuity Reference Prompts

```text
A reference prompt for a test subject.
```

### Step 3: MiniMax Generation Prompts (Ref2VA Full-Reference Mode)

#### Clip 1 [00:00 - 00:12 | Duration: 12s]

```text
subject_definitions:
<Subject 1> is a test person.
summary:
A test sequence.
retention_analysis:
<Subject 1>: fully_preserved.
detailed_description:
A cinematic test shot with no dialogue.
overall_soundscape:
Room tone.
non_diegetic_music:
Soft piano.
```
"""


class FinalizeMarkdownTests(unittest.TestCase):
    def test_audio_derives_title_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "aistudio_response_md.txt"
            dump.write_text(json.dumps(MINIMAL_STORYBOARD), encoding="utf-8")
            out = Path(tmp) / "999doahong.md"
            run(
                FINALIZER,
                "--in", dump,
                "--out", out,
                "--audio", AUDIO,
                "--model", "Gemini 3.8 Flash",
            )
            text = out.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("# 999doahong\n\n"))
        self.assertIn(
            "> Source: Gemini 3.8 Flash — Google AI Studio (Temporary chat)",
            text,
        )
        self.assertIn("> Input: 999doahong.mp3 (0:13.032)", text)
        self.assertIn(
            '> Prompt: "give me a good script for this soundtrack"', text
        )
        self.assertIn("> AI Studio response: 1st", text)
        self.assertIn("> System instructions preset: Film Director", text)
        self.assertTrue(text.rstrip().endswith("```"))

    def test_thinking_level_and_multiline_prompt_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "aistudio_response_md.txt"
            dump.write_text(json.dumps(MINIMAL_STORYBOARD), encoding="utf-8")
            out = Path(tmp) / "999doahong.md"
            run(
                FINALIZER,
                "--in", dump,
                "--out", out,
                "--audio", AUDIO,
                "--prompt", "first line\nsecond line",
                "--thinking", "High",
            )
            text = out.read_text(encoding="utf-8")

        self.assertIn('> Prompt: "first line second line"', text)
        self.assertIn("> Thinking level: High", text)

    def test_without_audio_keeps_manual_title_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "aistudio_response_md.txt"
            dump.write_text(json.dumps(MINIMAL_STORYBOARD), encoding="utf-8")
            out = Path(tmp) / "custom.md"
            run(
                FINALIZER,
                "--in", dump,
                "--out", out,
                "--title", "Custom Title",
                "--source", "Source: manual",
            )
            text = out.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("# Custom Title\n\n"))
        self.assertIn("> Source: manual", text)
        self.assertNotIn("> Input:", text)


class RenderSheetsTests(unittest.TestCase):
    def test_dry_run_lists_storyboard_sheets(self):
        proc = run(SHEETS, "--sb", SB, "--dry-run")
        self.assertIn("DRY RUN", proc.stdout)
        self.assertIn("character_wanderer_front.png", proc.stdout)
        self.assertIn("env_neon_bar_rain.png", proc.stdout)
        self.assertIn("prop_crystal_whiskey_glass.png", proc.stdout)
        self.assertIn("1920x1080", proc.stdout)

    def test_dry_run_filters_by_stem(self):
        proc = run(SHEETS, "--sb", SB, "--dry-run", "env_neon_bar_rain")
        self.assertIn("env_neon_bar_rain.png", proc.stdout)
        self.assertNotIn("character_wanderer_front.png", proc.stdout)

    def test_dry_run_respects_dimensions(self):
        proc = run(
            SHEETS, "--sb", SB, "--dry-run",
            "--width", "1280", "--height", "720",
        )
        self.assertIn("1280x720", proc.stdout)

    def test_requires_sb(self):
        proc = run(SHEETS, "--dry-run", expect=2)
        self.assertIn("--sb", proc.stderr)

    def test_dump_graph_writes_prompt_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_dir = Path(tmp) / "graphs"
            run(SHEETS, "--sb", SB, "--dry-run", "--dump-graph", graph_dir)
            graph = json.loads(
                (graph_dir / "character_wanderer_front.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertIn("charcoal", graph["7875"]["inputs"]["text"].lower())
        self.assertEqual(graph["7884"]["inputs"]["width"], 1920)
        self.assertEqual(graph["7884"]["inputs"]["height"], 1080)
        self.assertIn(
            "character_wanderer_front", graph["7897"]["inputs"]["filename_prefix"]
        )


class RenderH3Tests(unittest.TestCase):
    def test_dry_run_resolves_refs_prefix_and_prompt(self):
        proc = run(H3, "--sb", SB, "--dry-run")
        out = proc.stdout
        self.assertIn("DRY RUN", out)
        self.assertIn("999doahong_seg1", out)
        self.assertIn("audio=999doahong.mp3", out)
        self.assertIn("153=character_wanderer_front.png", out)
        self.assertIn("154=env_neon_bar_rain.png", out)
        self.assertIn("155=prop_crystal_whiskey_glass.png", out)
        self.assertNotIn("156=", out)
        self.assertIn("aspect=9:16", out)
        self.assertIn("non_diegetic_music", out)

    def test_dry_run_overrides_slug_aspect_ref_and_trim(self):
        proc = run(
            H3, "--sb", SB, "--dry-run",
            "--slug", "demo",
            "--aspect", "16:9",
            "--ref", "155=custom_prop.png",
            "--trim-duration", "18.5",
        )
        out = proc.stdout
        self.assertIn("demo_seg1", out)
        self.assertIn("aspect=16:9", out)
        self.assertIn("155=custom_prop.png", out)
        self.assertIn("trim=18.5", out)

    def test_requires_sb(self):
        proc = run(H3, "--dry-run", expect=2)
        self.assertIn("--sb", proc.stderr)

    def test_audio_offset_is_added_to_start_index(self):
        proc = run(H3, "--sb", SB, "--dry-run", "--audio-offset", "90")
        self.assertIn("start_index=90.0", proc.stdout)

    def test_cumulative_start_mode_uses_previous_durations(self):
        sb = json.loads(SB.read_text(encoding="utf-8"))
        second = json.loads(json.dumps(sb["segments"][0]))
        second["id"] = 2
        second["start"] = 0.0
        second["duration"] = 5.0
        sb["segments"].append(second)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-storyboard.json"
            path.write_text(json.dumps(sb), encoding="utf-8")
            proc = run(
                H3, "--sb", path, "--dry-run",
                "--audio", "999doahong.mp3",
                "--audio-start-mode", "cumulative",
            )
        self.assertIn("[demo_seg2]", proc.stdout)
        self.assertIn("start_index=12.958", proc.stdout)

    def test_dry_run_prunes_unused_refs(self):
        proc = run(H3, "--sb", SB, "--dry-run")
        self.assertIn("153=character_wanderer_front.png", proc.stdout)
        self.assertIn("154=env_neon_bar_rain.png", proc.stdout)
        self.assertIn("155=prop_crystal_whiskey_glass.png", proc.stdout)
        self.assertNotIn("156=", proc.stdout)

    def test_aspect_defaults_to_storyboard_project(self):
        sb = json.loads(SB.read_text(encoding="utf-8"))
        sb["project"]["aspect_ratio"] = "16:9"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-storyboard.json"
            path.write_text(json.dumps(sb), encoding="utf-8")
            proc = run(H3, "--sb", path, "--dry-run")
        self.assertIn("aspect=16:9", proc.stdout)

    def test_prefix_count_mismatch_is_an_error(self):
        proc = run(
            H3, "--sb", SB, "--dry-run",
            "--prefix", "one", "--prefix", "two",
            expect=2,
        )
        self.assertIn("--prefix", proc.stderr)

    def five_sheet_storyboard(self, tmp):
        sb = json.loads(SB.read_text(encoding="utf-8"))
        extra_character = json.loads(json.dumps(sb["references"]["character_sheets"][0]))
        extra_character["key_frame_file"] = "character_second_front.png"
        sb["references"]["character_sheets"].append(extra_character)
        extra_prop = json.loads(json.dumps(sb["references"]["prop_sheets"][0]))
        extra_prop["key_frame_file"] = "prop_second.png"
        sb["references"]["prop_sheets"].append(extra_prop)
        path = Path(tmp) / "demo-storyboard.json"
        path.write_text(json.dumps(sb), encoding="utf-8")
        return path

    def test_dump_graph_wires_fifth_ref_and_sets_ref_image_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb_path = self.five_sheet_storyboard(tmp)
            graph_dir = Path(tmp) / "graphs"
            run(
                H3, "--sb", sb_path, "--dry-run",
                "--dump-graph", graph_dir,
                "--ref-image-size", "max",
            )
            graph = json.loads(
                (graph_dir / "demo_seg1.json").read_text(encoding="utf-8")
            )

        self.assertEqual(graph["7518"]["inputs"]["ref_image_size"], "max")
        self.assertEqual(
            graph["7518"]["inputs"]["ref_images.ref_image_4"], ["9001", 0]
        )
        self.assertEqual(graph["9001"]["class_type"], "LoadImage")
        self.assertEqual(graph["9001"]["inputs"]["image"], "prop_second.png")
        self.assertNotIn("ref_images.ref_image_5", graph["7518"]["inputs"])
        self.assertEqual(
            graph["7518"]["inputs"]["ref_images.ref_image_3"], ["156", 0]
        )

    def test_dump_graph_prunes_third_and_fourth_baked_wires(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb_path = self.five_sheet_storyboard(tmp)
            # Drop the two extra sheets so only the three primary refs remain.
            sb = json.loads(sb_path.read_text(encoding="utf-8"))
            sb["references"]["character_sheets"] = sb["references"]["character_sheets"][:1]
            sb["references"]["prop_sheets"] = sb["references"]["prop_sheets"][:1]
            sb_path.write_text(json.dumps(sb), encoding="utf-8")
            graph_dir = Path(tmp) / "graphs"
            run(H3, "--sb", sb_path, "--dry-run", "--dump-graph", graph_dir)
            graph = json.loads(
                (graph_dir / "demo_seg1.json").read_text(encoding="utf-8")
            )
        self.assertNotIn("ref_images.ref_image_3", graph["7518"]["inputs"])
        self.assertNotIn("ref_images.ref_image_4", graph["7518"]["inputs"])


    def test_warns_when_all_starts_are_zero(self):
        sb = json.loads(SB.read_text(encoding="utf-8"))
        second = json.loads(json.dumps(sb["segments"][0]))
        second["id"] = 2
        second["start"] = 0.0
        sb["segments"].append(second)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo-storyboard.json"
            path.write_text(json.dumps(sb), encoding="utf-8")
            proc = run(
                H3, "--sb", path, "--dry-run",
                "--audio", "999doahong.mp3",
            )
        self.assertIn("cumulative", proc.stderr)


class RenderH3NodeErrorTests(unittest.TestCase):
    def test_queue_node_errors_abort_without_polling(self):
        import contextlib
        import importlib.util
        import io
        from types import SimpleNamespace
        from unittest import mock

        spec = importlib.util.spec_from_file_location("render_h3", H3)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        segment = json.loads(SB.read_text(encoding="utf-8"))["segments"][0]
        args = SimpleNamespace(
            workflow=str(SKILL / "minimax_h3_api.json"),
            api="http://127.0.0.1:8188",
            out_dir=tempfile.gettempdir(),
            timeout=1,
            client_id="test",
            aspect="9:16",
            ref_image_size="match",
            trim_duration=20.0,
        )

        def fake_post(api, path, *unused, **kwargs):
            if path == "/prompt":
                return {"prompt_id": "pid", "node_errors": {"7518": "bad ref"}}
            raise AssertionError("render polled after node_errors")

        with mock.patch.object(mod, "post", side_effect=fake_post):
            with contextlib.redirect_stdout(io.StringIO()):
                ok = mod.render(
                    segment, "demo_seg1", 0.0, args, "999doahong.mp3",
                    ["character.png"],
                )
        self.assertFalse(ok)


class StitchAndMixTests(unittest.TestCase):
    def test_dry_run_applies_audio_offset(self):
        proc = run(
            STITCH, "--slug", "999doahong", "--dry-run", "--audio-offset", "90",
            "--output-dir", FIXTURES,
        )
        self.assertIn("-ss 90.0", proc.stdout)

    def test_dry_run_trims_to_storyboard_durations(self):
        sb_path = FIXTURES / "thousand-reasons-sadness-storyboard.json"
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
        for segment in sb["segments"]:
            segment["duration"] = round(float(segment["duration"]) - 0.5, 3)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(sb, handle)
            trimmed_path = handle.name
        try:
            proc = run(
                STITCH, "--slug", "thousand-reasons-sadness", "--dry-run",
                "--sb", trimmed_path, "--output-dir", FIXTURES,
            )
        finally:
            Path(trimmed_path).unlink()
        self.assertIn("Clip 0: keep 0.0000s..13.8750s", proc.stdout)
        self.assertIn("Clip 3: keep 0.0000s..13.8750s", proc.stdout)

    def test_storyboard_clip_count_mismatch_fails(self):
        sb_path = FIXTURES / "thousand-reasons-sadness-storyboard.json"
        sb = json.loads(sb_path.read_text(encoding="utf-8"))
        sb["segments"] = sb["segments"][:2]
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(sb, handle)
            short_path = handle.name
        try:
            proc = run(
                STITCH, "--slug", "thousand-reasons-sadness", "--dry-run",
                "--sb", short_path, "--output-dir", FIXTURES, expect=1,
            )
        finally:
            Path(short_path).unlink()
        self.assertIn("2 segments but 4 clips", proc.stdout)


class AistudioStoryboardTests(unittest.TestCase):
    """Browser-free surface: flags, slug/path resolution, collision handling.

    The live flow needs a signed-in Chromium, so it is exercised by `--check`
    and one real run, not by the unit suite.
    """

    def test_help_lists_check_and_dry_run(self):
        proc = run(AISTUDIO, "--help")
        self.assertIn("--check", proc.stdout)
        self.assertIn("--dry-run", proc.stdout)

    def test_help_lists_build_json_flags(self):
        proc = run(AISTUDIO, "--help")
        self.assertIn("--build-json", proc.stdout)
        self.assertIn("--no-build-json", proc.stdout)
        self.assertIn("--json", proc.stdout)

    def test_dry_run_resolves_json_path_and_builds_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "999doahong.md"
            proc = run(AISTUDIO, "--dry-run", "--audio", AUDIO, "--out", out)
        self.assertIn("build_json=True", proc.stdout)
        self.assertIn("999doahong-storyboard.json", proc.stdout)

    def test_dry_run_no_build_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "999doahong.md"
            proc = run(
                AISTUDIO, "--dry-run", "--audio", AUDIO, "--out", out,
                "--no-build-json",
            )
        self.assertIn("build_json=False", proc.stdout)
        self.assertIn("json=(disabled)", proc.stdout)

    def test_dry_run_refuses_existing_json_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "999doahong.md"
            (Path(tmp) / "999doahong-storyboard.json").write_text(
                "{}", encoding="utf-8"
            )
            proc = run(
                AISTUDIO, "--dry-run", "--audio", AUDIO, "--out", out, expect=2
            )
        self.assertIn("already exists", proc.stderr)

    def test_requires_audio_unless_check(self):
        proc = run(AISTUDIO, expect=2)
        self.assertIn("--audio", proc.stderr)

    def test_rejects_missing_audio(self):
        proc = run(AISTUDIO, "--audio", "/definitely/missing.mp3", expect=2)
        self.assertIn("audio not found", proc.stderr)

    def test_dry_run_resolves_paths_and_creative_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "999doahong.md"
            proc = run(AISTUDIO, "--dry-run", "--audio", AUDIO, "--out", out)
        self.assertIn("DRY RUN", proc.stdout)
        self.assertIn("prompt='give me a good script for this soundtrack'", proc.stdout)
        self.assertIn("preset=Film Director", proc.stdout)
        self.assertIn("999doahong.md", proc.stdout)
        self.assertIn("attempts=2", proc.stdout)

    def test_dry_run_refuses_existing_output_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "taken.md"
            out.write_text("keep me", encoding="utf-8")
            proc = run(AISTUDIO, "--dry-run", "--audio", AUDIO, "--out", out, expect=2)
        self.assertIn("already exists", proc.stderr)


class AistudioBuildJsonTests(unittest.TestCase):
    def test_build_json_runs_the_builder_with_audio_and_overrides(self):
        import contextlib
        import importlib.util
        import io
        from types import SimpleNamespace

        spec = importlib.util.spec_from_file_location("aistudio_storyboard", AISTUDIO)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "demo.md"
            md.write_text(
                storyboard_markdown(
                    "```text\nA reference prompt for a test subject in a neutral room.\n```"
                ),
                encoding="utf-8",
            )
            out_json = Path(tmp) / "demo-storyboard.json"
            overrides = Path(tmp) / "overrides.json"
            overrides.write_text(
                json.dumps({"project": {"genre": "Test genre"}}), encoding="utf-8"
            )
            args = SimpleNamespace(
                audio=str(AUDIO),
                aspect_ratio="9:16",
                character_name="Protagonist",
                character_file=[],
                env_file=[],
                prop_file=[],
                overrides=str(overrides),
                no_extend_last=True,
            )
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                mod.build_json({"out": md, "json": out_json}, args)
            sb = json.loads(out_json.read_text(encoding="utf-8"))

        self.assertEqual(sb["project"]["genre"], "Test genre")
        self.assertEqual(len(sb["segments"]), 1)


class BuildStoryboardTests(unittest.TestCase):
    def build(self, tmp, *extra):
        out = Path(tmp) / "999doahong-storyboard.json"
        run(
            BUILDER,
            "--md", MD,
            "--out", out,
            "--audio", AUDIO,
            "--character-name", "Wanderer",
            "--character-file", "character_wanderer_front.png",
            "--env-file", "env_neon_bar_rain.png",
            "--prop-file", "prop_crystal_whiskey_glass.png",
            *extra,
        )
        return out, json.loads(out.read_text(encoding="utf-8"))

    def test_builds_schema_valid_json_with_verbatim_ref2va(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, sb = self.build(tmp, "--no-extend-last")

        for key in (
            "project", "subject_continuity", "segments",
            "continuity_requirements", "quality_priorities",
            "assumptions_and_defaults", "open_questions",
        ):
            self.assertIn(key, sb)

        project = sb["project"]
        self.assertEqual(project["title"], "999doahong")
        self.assertEqual(project["aspect_ratio"], "9:16")
        self.assertEqual(project["segments_count"], 1)
        self.assertAlmostEqual(project["target_duration_seconds"], 13.032, places=3)

        self.assertEqual(len(sb["segments"]), 1)
        seg = sb["segments"][0]
        self.assertEqual(seg["id"], 1)
        self.assertEqual(seg["start"], 0.0)
        self.assertEqual(seg["duration"], 12.0)
        expected = parse_ref2va_from_markdown(MD.read_text(encoding="utf-8"))
        self.assertEqual(seg["ref2va"], expected)

        refs = sb["references"]
        self.assertEqual(refs["inventory"], {
            "character_count": 1, "prop_count": 1, "location_count": 1,
        })
        self.assertEqual(refs["character_sheets"][0]["key_frame_file"],
                         "character_wanderer_front.png")
        self.assertEqual(refs["environment_sheets"][0]["key_frame_file"],
                         "env_neon_bar_rain.png")
        self.assertEqual(refs["prop_sheets"][0]["key_frame_file"],
                         "prop_crystal_whiskey_glass.png")

    def test_extends_last_segment_to_cover_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, sb = self.build(tmp)

        seg = sb["segments"][0]
        self.assertAlmostEqual(seg["duration"], 12.958, places=3)
        self.assertAlmostEqual(seg["end"], 12.958, places=3)
        self.assertEqual(seg["timecode"], "0:00-0:12.958")
        self.assertTrue(any("12.958" in line for line in sb["assumptions_and_defaults"]))

    def test_overrides_deep_merge_into_matching_segment(self):
        overrides = {
            "project": {"genre": "Neo-noir ballad"},
            "segments": [{"id": 1, "camera": {"angle": "low angle"}}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            ov = Path(tmp) / "overrides.json"
            ov.write_text(json.dumps(overrides), encoding="utf-8")
            _, sb = self.build(tmp, "--no-extend-last", "--overrides", ov)

        self.assertEqual(sb["project"]["genre"], "Neo-noir ballad")
        self.assertEqual(sb["segments"][0]["camera"]["angle"], "low angle")
        # The rest of the extracted segment survives the merge.
        self.assertIn("ref2va", sb["segments"][0])
        self.assertIn("action", sb["segments"][0])

    def build_text(self, text, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "fixture.md"
            md.write_text(text, encoding="utf-8")
            out = Path(tmp) / "fixture-storyboard.json"
            run(
                BUILDER,
                "--md", md,
                "--out", out,
                "--duration", "12",
                "--no-extend-last",
                *extra,
            )
            return json.loads(out.read_text(encoding="utf-8"))

    def test_blockquote_step1_fallback_extracts_sheet(self):
        step1 = (
            "> Character turnaround: a 30-year-old man in a charcoal coat, "
            "full body front view against a neutral studio backdrop, 85mm lens, "
            "soft key light, fine film grain."
        )
        sb = self.build_text(storyboard_markdown(step1))

        sheets = sb["references"]["character_sheets"]
        self.assertEqual(len(sheets), 1)
        self.assertIn("charcoal coat", sheets[0]["generation_prompt"])
        self.assertIn("extract_blockquote_sheets", sheets[0]["notes"])

    def test_bullet_step1_fallback_extracts_sheet(self):
        step1 = (
            "- Character turnaround: a 30-year-old man in a charcoal coat.\n"
            "  Full body front view against a neutral studio backdrop, 85mm lens, "
            "soft key light, fine film grain."
        )
        sb = self.build_text(storyboard_markdown(step1))

        sheets = sb["references"]["character_sheets"]
        self.assertEqual(len(sheets), 1)
        self.assertIn("charcoal coat", sheets[0]["generation_prompt"])
        self.assertIn("extract_bullet_sheets", sheets[0]["notes"])

    def test_untitled_fenced_step1_fallback_extracts_sheet(self):
        step1 = (
            "Character turnaround:\n\n"
            "```text\n"
            "A 30-year-old man in a charcoal coat, full body front view against "
            "a neutral studio backdrop, 85mm lens, soft key light, fine film grain.\n"
            "```"
        )
        sb = self.build_text(storyboard_markdown(step1))

        sheets = sb["references"]["character_sheets"]
        self.assertEqual(len(sheets), 1)
        self.assertIn("charcoal coat", sheets[0]["generation_prompt"])
        self.assertIn("extract_any_fenced_sheets", sheets[0]["notes"])

    def test_bracketed_clip_heading_is_parsed(self):
        step1 = (
            "```text\n"
            "A reference prompt for a test subject standing in a neutral room.\n"
            "```"
        )
        sb = self.build_text(
            storyboard_markdown(
                step1,
                clip_heading="#### Clip [1] [00:03 - 00:17 | Duration: 14s]",
            )
        )
        self.assertEqual(len(sb["segments"]), 1)
        self.assertEqual(sb["segments"][0]["id"], 1)
        self.assertAlmostEqual(sb["segments"][0]["start"], 3.0, places=3)
        self.assertAlmostEqual(sb["segments"][0]["duration"], 14.0, places=3)

    def test_rejects_markdown_without_step3_ref2va(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "bad.md"
            md.write_text("# bad\n\n### Step 1\n\nNothing here.\n", encoding="utf-8")
            proc = run(BUILDER, "--md", md, "--out", Path(tmp) / "out.json", expect=1)
        self.assertIn("ref2va", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
