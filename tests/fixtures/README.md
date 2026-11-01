# Test fixtures

Small, self-contained inputs for `tests/test_pipeline_scripts.py`.

- `999doahong.md`, `999doahong-storyboard.json`, `thousand-reasons-sadness-storyboard.json` — storyboard fixtures used by the CLI tests.
- `999doahong.mp3` — a silent WAV with an exact 13.032 s duration, named `.mp3` so the provenance assertions match the fixture's original filename. It contains no third-party audio.
- `*_seg*.mp4` — synthetic black clips used only for dry-run path and duration checks.
