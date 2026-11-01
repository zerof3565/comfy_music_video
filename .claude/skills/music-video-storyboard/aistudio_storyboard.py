#!/usr/bin/env python3
"""Drive Google AI Studio Film Director from a shell and write the storyboard.

This is the automated equivalent of _manual-fallback.md §1-§10. It attaches to an
already-signed-in Chromium over CDP (or launches one with the persistent
profile), opens a fresh temporary chat, selects the Film Director preset,
uploads the audio, sends the creative ask, waits for the 1st substantive
response, extracts it with extract_markdown.js, hands the dump to
finalize_markdown.py, and then builds the storyboard JSON with
build_storyboard.py (disable with --no-build-json).

It never logs in, never sends a follow-up turn, and never falls back to a later
response. A failed 1st response is retried the only allowed way: a fresh
temporary chat (the refresh + rerun path).

Requirements:
    uv pip install --python .venv/bin/python playwright
    A Chromium signed into AI Studio. Attach mode expects --cdp (default
    http://127.0.0.1:9223); if that fails the script launches --chrome with
    --profile (disable with --no-launch).

Usage:
    .venv/bin/python -I aistudio_storyboard.py --audio /path/track.mp3

    # Validate the selectors and preset without uploading or submitting
    .venv/bin/python -I aistudio_storyboard.py --check

    # Launch instead of attaching (the profile must not be in use)
    .venv/bin/python -I aistudio_storyboard.py --audio track.mp3 --no-cdp

    # Resolve paths without touching a browser
    .venv/bin/python -I aistudio_storyboard.py --dry-run --audio track.mp3

    # Markdown only (skip the storyboard JSON build)
    .venv/bin/python -I aistudio_storyboard.py --audio track.mp3 --no-build-json

    # Override auto-filled storyboard fields, or write the JSON elsewhere
    .venv/bin/python -I aistudio_storyboard.py --audio track.mp3 \
        --json outputs/custom-storyboard.json --overrides overrides.json
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CREATIVE_ASK = "give me a good script for this soundtrack"
PRESET = "Film Director"
THINKING_LEVEL = "High"
# AI Studio caps the number input at the model's 65536 default. High thinking is
# charged against the same output budget, so long (10+ clip) storyboards truncate
# mid-clip unless we raise the request above that default through the DOM.
MAX_OUTPUT_TOKENS = 131072

DEFAULT_CDP = "http://127.0.0.1:9223"
DEFAULT_PROFILE = Path.home() / ".cache" / "ms-playwright" / "chrome-for-automation-9223"
DEFAULT_CHROME = "/usr/bin/chromium"
REPO = Path(__file__).resolve().parents[3]
SKILL = Path(__file__).resolve().parent
EXTRACTOR = SKILL / "extract_markdown.js"
FINALIZER = SKILL / "finalize_markdown.py"
BUILDER = SKILL / "build_storyboard.py"

REF2VA_LABELS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

# Every UI dependency lives here. A Google AI Studio rename is a one-line fix.
UI = {
    "preset_button": r"System instructions",
    "preset_combo": "combobox",
    "preset_option": PRESET,
    "instruction_box": "System instructions",
    "close_panel": r"^Close panel$",
    "attach_button": r"Insert images, videos, audio, or files",
    "upload_menu": "Upload files",
    "file_input": "input[type=file].file-input",
    "composer": "Enter a prompt",
    "run": r"^Run\b",
    "stop": r"^Stop\b",
    "toolbar": r"thumb_up|thumb_down|good response|bad response",
    "model": r"^Gemini\b",
    "thinking_combo": "Thinking Level",
    "advanced_expander": 'button[aria-label="Expand or collapse advanced settings"]',
    "max_tokens_input": 'input[aria-label="Maximum output tokens"]',
}

EXIT_OK = 0
EXIT_FINALIZE = 1
EXIT_USAGE = 2
EXIT_BROWSER = 3
EXIT_UI = 4
EXIT_TIMEOUT = 5


class AutomationError(Exception):
    """Base class; `retryable` decides whether a fresh chat is attempted."""

    def __init__(self, message, *, retryable=False, exit_code=EXIT_TIMEOUT):
        super().__init__(message)
        self.retryable = retryable
        self.exit_code = exit_code


def log(message):
    print("[aistudio {}] {}".format(time.strftime("%H:%M:%S"), message), file=sys.stderr, flush=True)


def load_finalizer():
    """Import finalize_markdown.py for slugify/probe_duration without a path hack."""
    spec = importlib.util.spec_from_file_location("finalize_markdown", FINALIZER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def screenshot(page, debug_dir, name):
    if page is None:
        return
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / "{}.png".format(name)
        page.screenshot(path=str(path), full_page=False)
        log("screenshot: {}".format(path))
    except Exception as exc:  # noqa: BLE001 - diagnostics must never mask the real error
        log("screenshot failed: {}".format(exc))


def dump_dom(page, debug_dir, name):
    if page is None:
        return
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / "{}.html".format(name)
        path.write_text(page.content(), encoding="utf-8")
        log("dom dump: {}".format(path))
    except Exception as exc:  # noqa: BLE001
        log("dom dump failed: {}".format(exc))


# --------------------------------------------------------------------------
# Browser
# --------------------------------------------------------------------------


class Session:
    """Owns the browser/page lifecycle. Attached browsers are never closed."""

    def __init__(self, playwright, args):
        self.playwright = playwright
        self.args = args
        self.browser = None
        self.context = None
        self.launched = False
        self.page = None

    def open(self):
        if not self.args.no_cdp:
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(
                    self.args.cdp, timeout=10000
                )
                self.context = self.browser.contexts[0]
                log("attached over CDP: {}".format(self.args.cdp))
                return
            except Exception as exc:  # noqa: BLE001
                log("CDP attach failed ({}); trying the profile launcher".format(exc))
                if not self.args.launch:
                    raise AutomationError(
                        "cannot attach to {} and --launch was disabled. Start Chromium "
                        "with --remote-debugging-port=9223 or pass --launch.".format(self.args.cdp),
                        exit_code=EXIT_BROWSER,
                    ) from exc

        if not self.args.launch:
            raise AutomationError("no browser available (CDP disabled, launch disabled)",
                                  exit_code=EXIT_BROWSER)

        profile = Path(self.args.profile).expanduser()
        if not profile.exists():
            raise AutomationError(
                "profile not found: {}. Sign in to AI Studio once with:\n  {} "
                "--user-data-dir={} --remote-debugging-port=9223".format(
                    profile, self.args.chrome, profile
                ),
                exit_code=EXIT_BROWSER,
            )
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                executable_path=self.args.chrome,
                headless=self.args.headless,
                args=["--no-default-browser-check", "--disable-pings"],
            )
        except Exception as exc:  # noqa: BLE001
            raise AutomationError(
                "cannot launch with profile {}: {}. Another Chromium is probably using "
                "it; attach with --cdp instead, or close that browser.".format(profile, exc),
                exit_code=EXIT_BROWSER,
            ) from exc
        self.launched = True
        log("launched Chromium with profile: {}".format(profile))

    def new_chat_page(self):
        page = self.context.new_page()
        page.set_default_timeout(15000)
        page.goto("https://aistudio.google.com/prompts/new_chat", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if "accounts.google.com" in page.url:
            page.close()
            raise AutomationError(
                "AI Studio redirected to Google sign-in. Sign in manually in this "
                "browser, then rerun. The script never enters credentials.",
                exit_code=EXIT_BROWSER,
            )
        self.page = page
        return page

    def close_page(self):
        """Close only this attempt's tab; a launched browser stays usable for retries."""
        if self.page is not None:
            try:
                self.page.close()
            except Exception:  # noqa: BLE001
                pass
            self.page = None

    def shutdown(self, keep_page=False):
        if keep_page:
            # Keeping the page means keeping its browser too, including a launched one.
            return
        self.close_page()
        if self.launched:
            try:
                self.context.close()
            except Exception:  # noqa: BLE001
                pass
        # Never browser.close() an attached browser: it may be the user's.


# --------------------------------------------------------------------------
# Step helpers
# --------------------------------------------------------------------------


def wait_visible(locator, timeout, what):
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise AutomationError(
            "UI changed: {} is not visible ({})".format(what, exc),
            exit_code=EXIT_UI,
        ) from exc


def close_settings_panel(page):
    close = page.get_by_role("button", name=re.compile(UI["close_panel"], re.I))
    if close.count():
        close.first.click()
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(800)


def select_preset(page, *, interactive=True):
    """Select Film Director and verify the instruction body loaded."""
    button = page.get_by_role("button", name=re.compile(UI["preset_button"], re.I))
    wait_visible(button, 15000, "System instructions button")
    button.first.click()
    page.wait_for_timeout(800)

    combo = page.get_by_role(UI["preset_combo"]).first
    wait_visible(combo, 10000, "preset combobox")
    combo.click()
    page.wait_for_timeout(700)

    option = page.get_by_role("option", name=UI["preset_option"], exact=True)
    if option.count() == 0:
        page.keyboard.press("Escape")
        raise AutomationError(
            "preset '{}' is missing from the listbox. Do not substitute another "
            "preset; add it in AI Studio.".format(PRESET),
            exit_code=EXIT_UI,
        )
    if interactive:
        option.first.click()
    else:
        page.keyboard.press("Escape")

    page.wait_for_timeout(1200)
    if not interactive:
        return {"selected": False, "instruction_chars": 0}

    combo_text = (combo.inner_text(timeout=5000) or "").strip()
    if PRESET.lower() not in combo_text.lower():
        raise AutomationError(
            "combobox shows {!r}, not {!r}".format(combo_text, PRESET), exit_code=EXIT_UI
        )

    # Saved marker + populated instruction body are the two content checks.
    try:
        page.get_by_text(re.compile(r"^\s*Saved\s*$")).first.wait_for(
            state="visible", timeout=10000
        )
    except Exception:  # noqa: BLE001
        raise AutomationError(
            "preset did not report 'Saved' after selection", exit_code=EXIT_UI
        )

    box = page.get_by_role("textbox", name=UI["instruction_box"]).first
    wait_visible(box, 10000, "system instruction textarea")
    chars = len(box.input_value())
    if chars < 1000:
        raise AutomationError(
            "system instruction body is only {} chars; the preset did not load".format(chars),
            exit_code=EXIT_UI,
        )

    close_settings_panel(page)
    return {"selected": True, "instruction_chars": chars}


def select_thinking_level(page, level, *, interactive=True):
    """Select the Thinking level in the same run-settings panel as the preset.

    The control is a Material select labelled 'Thinking Level' with Low/Medium/
    High options; the panel is opened by the System instructions button.
    """
    combo = page.get_by_role("combobox", name=UI["thinking_combo"])
    if not combo.count() or not combo.first.is_visible():
        opener = page.get_by_role("button", name=re.compile(UI["preset_button"], re.I))
        wait_visible(opener, 15000, "System instructions button")
        opener.first.click()
        page.wait_for_timeout(800)
    wait_visible(combo, 10000, "thinking level combobox")

    target = str(level).strip()
    current = (combo.first.inner_text() or "").strip()
    if not interactive or current.lower() == target.lower():
        close_settings_panel(page)
        return {"level": current, "changed": False}

    combo.first.click()
    page.wait_for_timeout(500)
    option = page.get_by_role("option", name=target, exact=True)
    if option.count() == 0:
        page.keyboard.press("Escape")
        raise AutomationError(
            "thinking level {!r} is missing from the dropdown".format(target),
            exit_code=EXIT_UI,
        )
    option.first.click()
    page.wait_for_timeout(500)

    selected = (combo.first.inner_text() or "").strip()
    if selected.lower() != target.lower():
        raise AutomationError(
            "thinking level shows {!r}, not {!r}".format(selected, target),
            exit_code=EXIT_UI,
        )
    close_settings_panel(page)
    return {"level": selected, "changed": True}


def set_max_output_tokens(page, value):
    """Raise AI Studio's 'Maximum output tokens' above its 65536 UI cap.

    The number input carries a hard max attribute at the model default, and
    High thinking is charged against the same output budget, so a 12-clip
    storyboard truncates mid-clip. Removing the attribute and firing Angular's
    value-accessor events makes the UI send the larger
    generationConfig.maxOutputTokens instead of clamping it.
    """
    value = int(value)
    if value <= 0:
        raise AutomationError("max output tokens must be positive", exit_code=EXIT_USAGE)

    selector = UI["max_tokens_input"]
    inp = page.query_selector(selector)
    if not inp or not inp.is_visible():
        # Open the run-settings panel when it is closed, then Advanced settings.
        close = page.get_by_role("button", name=re.compile(UI["close_panel"], re.I))
        if not close.count():
            opener = page.get_by_role(
                "button", name=re.compile(UI["preset_button"], re.I)
            )
            wait_visible(opener, 15000, "System instructions button")
            opener.first.click()
            page.wait_for_timeout(800)
        expander = page.query_selector(UI["advanced_expander"])
        if not expander:
            raise AutomationError(
                "advanced settings expander is missing", exit_code=EXIT_UI
            )
        expander.click()
        page.wait_for_timeout(600)
    inp = page.wait_for_selector(selector, state="visible", timeout=10000)

    current = int(float(inp.input_value() or "0"))
    if current >= value:
        close_settings_panel(page)
        return {"value": current, "changed": False}

    page.evaluate(
        """(v) => {
          const inp = document.querySelector(
            'input[aria-label="Maximum output tokens"]');
          inp.removeAttribute('max');
          const set = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype, 'value').set;
          set.call(inp, String(v));
          inp.dispatchEvent(new Event('input', {bubbles: true}));
          inp.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )
    page.wait_for_timeout(300)
    applied = int(float(inp.input_value() or "0"))
    if applied != value:
        raise AutomationError(
            "max output tokens shows {!r}, not {!r}".format(applied, value),
            exit_code=EXIT_UI,
        )
    close_settings_panel(page)
    return {"value": applied, "changed": True}


def attachment_region(page):
    return page.evaluate(
        """() => {
          const ta = [...document.querySelectorAll('textarea')].find(
            (t) => (t.getAttribute('aria-label') || '') === 'Enter a prompt');
          if (!ta) return '';
          let el = ta;
          for (let i = 0; i < 10 && el; i += 1) el = el.parentElement;
          return el ? (el.innerText || '') : '';
        }"""
    )


def attachment_seen(page, audio):
    """The chip may sit outside the composer's ancestor chain; check the page too."""
    region = attachment_region(page)
    if audio.name in region:
        return region, True
    try:
        if page.get_by_text(audio.name, exact=False).count() > 0:
            return region, True
    except Exception:  # noqa: BLE001
        pass
    return region, False


def wait_for_chip(page, audio, timeout):
    deadline = time.time() + timeout
    region = ""
    while time.time() < deadline:
        region, seen = attachment_seen(page, audio)
        if seen:
            return True, region
        time.sleep(1)
    return False, region


def attach_audio(page, audio):
    """Upload by setting the hidden file input; fall back to the menu chooser."""
    file_input = page.locator(UI["file_input"]).first
    if file_input.count():
        try:
            file_input.set_input_files(str(audio))
            log("audio set directly on {}".format(UI["file_input"]))
            seen, region = wait_for_chip(page, audio, 60)
            if seen:
                if re.search(r"\b\d{1,2}:\d{2}\b", region):
                    log("attachment chip shows {} and a duration".format(audio.name))
                else:
                    log("WARNING: attachment shows the filename but no duration; continuing")
                return
            log("direct upload produced no chip; falling back to the attach menu")
        except Exception as exc:  # noqa: BLE001
            log("direct file input failed ({}); using the attach menu".format(exc))

    attach = page.get_by_role("button", name=re.compile(UI["attach_button"], re.I))
    wait_visible(attach, 10000, "attach button")
    try:
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            attach.first.click()
            page.get_by_role("menuitem", name=UI["upload_menu"], exact=True).first.click()
        chooser_info.value.set_files(str(audio))
        log("audio set through the file chooser")
    except Exception as exc:  # noqa: BLE001
        raise AutomationError(
            "could not open the upload chooser: {}".format(exc), exit_code=EXIT_UI
        ) from exc

    seen, region = wait_for_chip(page, audio, 90)
    if seen:
        if re.search(r"\b\d{1,2}:\d{2}\b", region):
            log("attachment chip shows {} and a duration".format(audio.name))
        else:
            log("WARNING: attachment shows the filename but no duration; continuing")
        return
    raise AutomationError(
        "attachment chip never showed '{}'. Composer region text: {!r}".format(
            audio.name, region[:300]
        ),
        retryable=True,
    )


def read_model_name(page):
    try:
        button = page.get_by_role("button", name=re.compile(UI["model"])).first
        label = (button.get_attribute("aria-label") or button.inner_text() or "").strip()
        match = re.match(r"^(Gemini[^\n|]+?)\s+(?:gemini-|Our\b)", label)
        if match:
            return match.group(1).strip()
        match = re.match(r"^(Gemini\s+[0-9][^\n|]*)", label)
        if match:
            return match.group(1).strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def submit_prompt(page, prompt):
    composer = page.get_by_role("textbox", name=UI["composer"]).first
    wait_visible(composer, 15000, "prompt textarea")
    composer.fill(prompt)
    if composer.input_value() != prompt:
        raise AutomationError("composer did not accept the prompt text", exit_code=EXIT_UI)

    run = page.get_by_role("button", name=re.compile(UI["run"])).first
    deadline = time.time() + 60
    while time.time() < deadline:
        if run.is_enabled():
            break
        time.sleep(1)
    else:
        raise AutomationError(
            "Run stayed disabled for 60s; the audio may still be registering",
            retryable=True,
        )
    run.click()
    log("submitted: {!r}".format(prompt))


def clipboard_fallback(page):
    """Copy button + clipboard, used only if the DOM serializer returns empty."""
    try:
        page.bring_to_front()
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:  # noqa: BLE001
            pass
        clicked = page.evaluate(
            """() => {
              const turns = [...document.querySelectorAll('ms-chat-turn')];
              const turn = turns.find((t) => {
                if (!t.querySelector('.chat-turn-container.model')) return false;
                const r = t.querySelector('ms-text-chunk ms-cmark-node.cmark-node');
                const txt = r ? (r.innerText || '').trim() : '';
                return txt.length > 200 && !/^Thoughts\\b/i.test(txt);
              });
              if (!turn) return false;
              const buttons = [...turn.querySelectorAll('button')];
              const copy = buttons.find((b) =>
                /copy/i.test(b.getAttribute('aria-label') || '') ||
                /content_copy/.test(b.innerText || ''));
              if (!copy) return false;
              copy.click();
              return true;
            }"""
        )
        if not clicked:
            return ""
        page.wait_for_timeout(800)
        return page.evaluate("async () => await navigator.clipboard.readText()") or ""
    except Exception as exc:  # noqa: BLE001
        log("clipboard fallback failed: {}".format(exc))
        return ""


def final_block_complete(text):
    """True when the last fenced block is a complete ref2va prompt.

    The Stop button can flicker off during AI Studio's per-block re-render, so
    content completeness is the authoritative signal. An unclosed fence means
    the answer is still streaming; the last closed block must also carry all six
    ref2va sections, and every clip heading must already have a prompt block.
    """
    if len(re.findall(r"(?m)^```", text)) % 2:
        return False
    blocks = re.findall(r"```[a-zA-Z]*[ \t]*\n(.*?)```", text, re.S)
    if not blocks:
        return False
    last = blocks[-1]
    if not all(
        re.search(r"(?m)^{}:".format(re.escape(label)), last)
        for label in REF2VA_LABELS
    ):
        return False
    headings = len(re.findall(r"(?m)^#{3,4} +Clip\b", text))
    prompts = sum(1 for b in blocks if re.search(r"(?m)^subject_definitions:", b))
    return prompts >= headings


def wait_for_response(page, extractor_src, timeout, debug_dir):
    deadline = time.time() + timeout
    stop_gone_at = None
    last_report = 0.0
    last_text = ""
    stable_reads = 0
    while time.time() < deadline:
        text = ""
        try:
            text = page.evaluate(extractor_src) or ""
        except Exception as exc:  # noqa: BLE001
            log("extractor error (will retry): {}".format(exc))

        stop_present = page.get_by_role("button", name=re.compile(UI["stop"])).count() > 0
        toolbar = 0
        if text and not stop_present:
            toolbar = page.get_by_role(
                "button", name=re.compile(UI["toolbar"], re.I)
            ).count()

        # Never capture a mid-stream snapshot: the last block must be complete
        # and the text must stay unchanged for three consecutive polls (~6s).
        complete = bool(text) and not stop_present and final_block_complete(text)
        stable_reads = stable_reads + 1 if complete and text == last_text else 0
        if complete and stable_reads >= 2:
            if toolbar == 0:
                log("WARNING: response toolbar not found; completion judged by content")
            return text
        last_text = text

        if not stop_present:
            stop_gone_at = stop_gone_at or time.time()
            if time.time() - stop_gone_at > 15 and not text:
                fallback = clipboard_fallback(page)
                if fallback and final_block_complete(fallback):
                    log("recovered the response through the clipboard fallback")
                    return fallback
        else:
            stop_gone_at = None

        if time.time() - last_report > 30:
            last_report = time.time()
            log("waiting: {} chars, stop={}, final_block={}".format(
                len(text), stop_present, final_block_complete(text)))
        time.sleep(3)

    raise AutomationError(
        "no complete 1st response within {}s (content-based completion signal never "
        "fired)".format(timeout),
        retryable=True,
    )


# --------------------------------------------------------------------------
# Finalize and verify
# --------------------------------------------------------------------------


def finalize(paths, args, model):
    cmd = [
        sys.executable, "-I", str(FINALIZER),
        "--in", str(paths["dump"]),
        "--out", str(paths["out"]),
        "--audio", str(args.audio),
        "--prompt", args.prompt,
        "--preset", PRESET,
        "--thinking", args.thinking_level,
    ]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        log("finalizer: {}".format(proc.stdout.strip()))
    if proc.returncode != 0:
        raise AutomationError(
            "finalizer exited {}: {}".format(proc.returncode, proc.stderr.strip()),
            retryable=True,
            exit_code=EXIT_FINALIZE,
        )
    if "WARNING:" in proc.stderr:
        raise AutomationError(
            "finalizer warning, re-extract: {}".format(proc.stderr.strip()),
            retryable=True,
            exit_code=EXIT_FINALIZE,
        )


def build_json(paths, args):
    cmd = [
        sys.executable, "-I", str(BUILDER),
        "--md", str(paths["out"]),
        "--out", str(paths["json"]),
        "--aspect-ratio", args.aspect_ratio,
        "--character-name", args.character_name,
    ]
    if args.audio:
        cmd += ["--audio", str(args.audio)]
    if args.overrides:
        cmd += ["--overrides", args.overrides]
    for name in args.character_file:
        cmd += ["--character-file", name]
    for name in args.env_file:
        cmd += ["--env-file", name]
    for name in args.prop_file:
        cmd += ["--prop-file", name]
    if args.no_extend_last:
        cmd += ["--no-extend-last"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        log("builder: {}".format(proc.stdout.strip()))
    if proc.stderr.strip():
        log("builder stderr: {}".format(proc.stderr.strip()))
    if proc.returncode != 0:
        raise AutomationError(
            "builder exited {}: {}".format(proc.returncode, proc.stderr.strip()),
            retryable=True,
            exit_code=EXIT_FINALIZE,
        )


def verify_output(out, dump_text, json_path=None):
    md = Path(out).read_text(encoding="utf-8")
    if not md.startswith("# "):
        raise AutomationError("output has no title header", retryable=True, exit_code=EXIT_FINALIZE)
    if md.count("```") % 2:
        raise AutomationError("unbalanced code fences", retryable=True, exit_code=EXIT_FINALIZE)
    clips = len(re.findall(r"^#{3,4}\s*Clip\b", md, re.M))
    prompts = md.count("integrated_multimodal_description:") + md.count("detailed_description:")
    if clips == 0 or prompts != clips:
        raise AutomationError(
            "{} clip headings vs {} Step 3 prompts".format(clips, prompts),
            retryable=True,
            exit_code=EXIT_FINALIZE,
        )
    if "non_diegetic_music:" not in md:
        raise AutomationError("no non_diegetic_music in the final body", retryable=True,
                              exit_code=EXIT_FINALIZE)
    if "non_diegetic_music:" not in dump_text:
        raise AutomationError("capture lost the final audio fields", retryable=True,
                              exit_code=EXIT_FINALIZE)

    sheets = 0
    if json_path:
        storyboard = json.loads(Path(json_path).read_text(encoding="utf-8"))
        segments = storyboard.get("segments") or []
        if not segments:
            raise AutomationError("storyboard JSON has no segments", retryable=True,
                                  exit_code=EXIT_FINALIZE)
        for segment in segments:
            missing = [label for label in REF2VA_LABELS
                       if label not in (segment.get("ref2va") or {})]
            if missing:
                raise AutomationError(
                    "segment {} JSON ref2va is missing {}".format(
                        segment.get("id"), ", ".join(missing)),
                    retryable=True, exit_code=EXIT_FINALIZE,
                )
        refs = storyboard.get("references") or {}
        sheets = sum(len(refs.get(key, [])) for key in (
            "character_sheets", "environment_sheets", "prop_sheets"
        ))
        if sheets == 0:
            log("WARNING: storyboard JSON has zero reference sheets; add them via "
                "--overrides before rendering")
    return clips, prompts, sheets


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------


def run_check(session, args, debug_dir):
    page = session.new_chat_page()
    report = []

    def item(name, okay, detail=""):
        report.append((okay, name, detail))
        log("{} {} {}".format("OK  " if okay else "FAIL", name, detail))

    composer = page.get_by_role("textbox", name=UI["composer"])
    item("signed in (no sign-in redirect)", "accounts.google.com" not in page.url, page.url)
    item("prompt textarea", composer.count() > 0)

    attach = page.get_by_role("button", name=re.compile(UI["attach_button"], re.I))
    item("attach button", attach.count() > 0)
    item("file input", page.locator(UI["file_input"]).count() > 0)

    run = page.get_by_role("button", name=re.compile(UI["run"])).first
    item("Run button", page.get_by_role("button", name=re.compile(UI["run"])).count() == 1)
    if composer.count():
        composer.first.fill("check")
        page.wait_for_timeout(800)
        item("Run enables with text", run.is_enabled())
        composer.first.fill("")
        page.wait_for_timeout(500)

    try:
        preset = select_preset(page, interactive=True)
        item("Film Director option", True)
        item("preset instruction body", preset["instruction_chars"] > 1000,
             "{} chars".format(preset["instruction_chars"]))
    except AutomationError as exc:
        item("Film Director preset", False, str(exc))

    try:
        thinking = select_thinking_level(page, args.thinking_level)
        item("thinking level {}".format(args.thinking_level),
             thinking["level"].lower() == args.thinking_level.lower(), thinking["level"])
    except AutomationError as exc:
        item("thinking level {}".format(args.thinking_level), False, str(exc))

    model = read_model_name(page)
    item("model readable", bool(model), model or "not found")

    okay = all(row[0] for row in report)
    screenshot(page, debug_dir, "check")
    if not okay:
        raise AutomationError("selector check failed; see the FAIL rows above",
                              exit_code=EXIT_UI)
    log("check passed; no upload or submission was performed")
    session.shutdown(keep_page=args.keep_open)
    return EXIT_OK


def run_once(session, args, debug_dir, attempt):
    page = session.new_chat_page()
    log("attempt {}/{}: new temporary chat".format(attempt, args.max_attempts))

    preset = select_preset(page, interactive=True)
    log("preset selected: {} ({} chars)".format(PRESET, preset["instruction_chars"]))

    thinking = select_thinking_level(page, args.thinking_level)
    log("thinking level: {}".format(thinking["level"]))

    attach_audio(page, Path(args.audio))
    tokens = set_max_output_tokens(page, args.max_output_tokens)
    log("max output tokens: {}{}".format(
        tokens["value"], "" if tokens["changed"] else " (already set)"))
    model = args.model or read_model_name(page)
    log("model: {}".format(model or "(not readable; Source line omitted)"))

    submit_prompt(page, args.prompt)
    extractor_src = EXTRACTOR.read_text(encoding="utf-8")
    text = wait_for_response(page, extractor_src, args.timeout, debug_dir)
    log("captured {} chars from the 1st substantive response".format(len(text)))

    dump = Path(args.dump)
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(json.dumps(text), encoding="utf-8")
    log("dump: {}".format(dump))

    paths = {"dump": dump, "out": Path(args.out), "json": Path(args.json)}
    finalize({"dump": dump, "out": Path(args.out)}, args, model)
    if args.build_json:
        build_json(paths, args)
    clips, prompts, sheets = verify_output(
        args.out, text, args.json if args.build_json else None
    )
    log("verified: {} clips, {} prompts, {} reference sheet(s)".format(
        clips, prompts, sheets))
    session.shutdown(keep_page=args.keep_open)
    return EXIT_OK


def main():
    ap = argparse.ArgumentParser(
        description="Automate AI Studio Film Director storyboard capture.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--audio", help="source soundtrack (required unless --check)")
    ap.add_argument("--prompt", default=CREATIVE_ASK, help="creative ask sent verbatim")
    ap.add_argument("--thinking-level", default=THINKING_LEVEL,
                    help="AI Studio thinking level: Low, Medium, or High (default: %(default)s)")
    ap.add_argument("--max-output-tokens", type=int, default=MAX_OUTPUT_TOKENS,
                    help="maximum output tokens; values above AI Studio's 65536 "
                         "UI cap are set through the DOM (default: %(default)s)")
    ap.add_argument("--out", help="output .md (default outputs/<slug>.md)")
    ap.add_argument("--json", help="output JSON (default <out-stem>-storyboard.json)")
    ap.add_argument("--build-json", dest="build_json", action="store_true", default=True,
                    help="build the storyboard JSON after finalizing (default)")
    ap.add_argument("--no-build-json", dest="build_json", action="store_false",
                    help="only write the markdown")
    ap.add_argument("--aspect-ratio", default="9:16",
                    help="target video aspect passed to the builder (default 9:16)")
    ap.add_argument("--overrides", help="JSON overrides passed to build_storyboard.py")
    ap.add_argument("--character-name", default="Protagonist",
                    help="passed to build_storyboard.py")
    ap.add_argument("--character-file", action="append", default=[],
                    help="character sheet filename (repeatable)")
    ap.add_argument("--env-file", action="append", default=[],
                    help="environment sheet filename (repeatable)")
    ap.add_argument("--prop-file", action="append", default=[],
                    help="prop sheet filename (repeatable)")
    ap.add_argument("--no-extend-last", action="store_true",
                    help="keep the model's last-clip duration")
    ap.add_argument("--dump", help="temporary JSON dump (default aistudio_response_md.txt)")
    ap.add_argument("--model", help="model label for the Source line (default: read from the UI)")
    ap.add_argument("--cdp", default=DEFAULT_CDP, help="CDP endpoint (default %(default)s)")
    ap.add_argument("--no-cdp", action="store_true", help="do not try the CDP attach")
    ap.add_argument("--no-launch", dest="launch", action="store_false",
                    help="do not fall back to launching Chromium when CDP is unavailable")
    ap.set_defaults(launch=True)
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE), help="Chromium user-data-dir")
    ap.add_argument("--chrome", default=DEFAULT_CHROME, help="Chromium executable")
    ap.add_argument("--headless", action="store_true",
                    help="headless launch (discouraged; Google may challenge it)")
    ap.add_argument("--check", action="store_true",
                    help="verify selectors and preset only; no upload or submission")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved paths and prompt, then exit (no browser)")
    ap.add_argument("--timeout", type=int, default=900, help="response timeout in seconds")
    ap.add_argument("--retries", type=int, default=1,
                    help="extra attempts after the first (each is a fresh temporary chat)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing --out")
    ap.add_argument("--keep-open", action="store_true", help="leave the chat tab/browser open")
    ap.add_argument("--keep-dump", action="store_true", help="keep the dump after success")
    ap.add_argument("--debug-dir", help="artifact directory for failures")
    args = ap.parse_args()
    args.max_attempts = 1 + max(0, args.retries)

    if not args.check and not args.audio:
        ap.error("--audio is required unless --check is used")
    if args.audio and not Path(args.audio).expanduser().exists():
        ap.error("audio not found: {}".format(args.audio))

    finalizer = load_finalizer()
    timestamp = now()
    debug_dir = Path(args.debug_dir) if args.debug_dir else REPO / ".debug" / timestamp

    preexisting = set()
    if args.audio:
        audio = Path(args.audio).expanduser().resolve()
        slug = finalizer.slugify(audio.stem)
        args.audio = str(audio)
        args.out = str(Path(args.out) if args.out else REPO / "outputs" / (slug + ".md"))
        # Keep the JSON beside a custom --out unless --json is explicit.
        args.json = str(Path(args.json) if args.json else
                        Path(args.out).with_name(Path(args.out).stem + "-storyboard.json"))
        args.dump = str(Path(args.dump) if args.dump else REPO / "aistudio_response_md.txt")
        if not args.check:
            targets = [("output", args.out)]
            if args.build_json:
                targets.append(("JSON", args.json))
            for label, path in targets:
                target = Path(path)
                if target.exists():
                    preexisting.add(target)
                    if not args.force:
                        print(
                            "ERROR: {} already exists: {}. Pass --force to overwrite, "
                            "or choose another path.".format(label, path),
                            file=sys.stderr,
                        )
                        return EXIT_USAGE
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            if args.build_json:
                Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        duration = finalizer.probe_duration(audio)
        log("audio: {} ({})".format(audio, duration if duration is not None else "duration unknown"))

    if args.dry_run and not args.check:
        print("DRY RUN")
        print("audio={}".format(args.audio))
        print("out={}".format(args.out))
        print("json={}".format(args.json if args.build_json else "(disabled)"))
        print("build_json={}".format(args.build_json))
        print("dump={}".format(args.dump))
        print("prompt={!r}".format(args.prompt))
        print("preset={}".format(PRESET))
        print("thinking_level={}".format(args.thinking_level))
        print("cdp={} launch_fallback={}".format(args.cdp, args.launch))
        print("attempts={} timeout={}s".format(args.max_attempts, args.timeout))
        return EXIT_OK

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: playwright is not installed for this interpreter. Run:\n"
            "  uv pip install --python .venv/bin/python playwright",
            file=sys.stderr,
        )
        return EXIT_USAGE

    exit_code = EXIT_OK
    with sync_playwright() as playwright:
        session = Session(playwright, args)
        try:
            session.open()
            if args.check:
                return run_check(session, args, debug_dir)
            for attempt in range(1, args.max_attempts + 1):
                try:
                    return run_once(session, args, debug_dir, attempt)
                except AutomationError as exc:
                    screenshot(session.page, debug_dir, "attempt-{}".format(attempt))
                    dump_dom(session.page, debug_dir, "attempt-{}".format(attempt))
                    log("attempt {} failed: {}".format(attempt, exc))
                    if not exc.retryable or attempt == args.max_attempts:
                        exit_code = exc.exit_code
                        log("keeping the failed chat tab open for inspection")
                        session.shutdown(keep_page=True)
                        break
                    log("retrying with a fresh temporary chat (no follow-up turn)")
                    # A failed attempt may have written a partial output before
                    # the builder failed; remove it so the retry writes cleanly.
                    for path in (args.out, args.json if args.build_json else None):
                        if path and Path(path) not in preexisting:
                            try:
                                Path(path).unlink(missing_ok=True)
                            except OSError:
                                pass
                    session.close_page()
            return exit_code
        except AutomationError as exc:
            log("fatal: {}".format(exc))
            screenshot(session.page, debug_dir, "fatal")
            dump_dom(session.page, debug_dir, "fatal")
            session.shutdown(keep_page=True)
            return exc.exit_code
        except Exception as exc:  # noqa: BLE001 - surface unexpected Playwright errors
            log("unexpected error: {}: {}".format(type(exc).__name__, exc))
            screenshot(session.page, debug_dir, "unexpected")
            dump_dom(session.page, debug_dir, "unexpected")
            session.shutdown(keep_page=True)
            return EXIT_BROWSER
        finally:
            if args.audio and exit_code == EXIT_OK and not args.keep_dump:
                try:
                    Path(args.dump).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass


if __name__ == "__main__":
    sys.exit(main())
