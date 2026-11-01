#!/usr/bin/env python3
"""
Stitch H3 segments and apply the soundtrack for this repo's workflow.

Adapted from hardcut_auto_merge.py. Concatenates segments with hard cuts and,
by default, uses the ORIGINAL SOUNDTRACK ONLY — the H3-generated vocal/foley
layer is discarded (replaced by the soundtrack). Pass --with-h3-audio to opt
into the older 65% soundtrack / 35% H3 foley mix.

H3 durations are frame-snapped and intentional, so every frame is kept by
default; --auto-trim restores the old decimal-trimming behavior
(e.g. 14.375s -> 14.0s) for other pipelines.

Usage:
    python3 -I stitch_and_mix.py --slug 1409777950540457 --trim-output 12.225
    python3 -I stitch_and_mix.py --slug <slug> --audio-offset 90 --dry-run

--audio-offset must match render_h3.py's value when the storyboard starts part
way into a long soundtrack; otherwise H3 trims from 90 s but the final mix
starts the song at 0.
"""

import os
import re
import json
import shutil
import subprocess
import argparse


# --- Configuration (edit these per project) ---
CLIP_PREFIX = "1409777950540457_seg"      # e.g., "1409777950540457_seg"
CLIP_EXTENSION = ".mp4"
FPS = 24.0

# H3 segment durations are frame-snapped and intentional (5.875s, 6.583s, ...).
# Keep every frame by default; --auto-trim restores decimal trimming.
AUTO_DETECT_OVERLAPS = False
DEFAULT_OVERLAP_SECONDS = 0.0
OUTPUT_TRIM_SECONDS = None  # --trim-output: cap the final file at the track length
KEEP_DURATIONS = None       # --sb: per-clip trim lengths from the storyboard

# Master audio: the original soundtrack replaces the H3 audio track by default.
# --with-h3-audio restores the optional 65% soundtrack / 35% H3 foley mix.
MASTER_AUDIO_PATH = "1409777950540457.mp3"   # soundtrack file in outputs/
USE_H3_AUDIO = False     # default: soundtrack only (H3 vocal/foley discarded)
FOLEY_VOLUME = 0.35      # H3 foley at 35% (only with --with-h3-audio)
MUSIC_VOLUME = 0.65      # Soundtrack at 65% (only with --with-h3-audio)

# Output
OUTPUT_CRF = 18
# ------------------------------------------------


def check_dependencies():
    for dep in ['ffmpeg', 'ffprobe']:
        if shutil.which(dep) is None:
            print(f"Error: '{dep}' not found in PATH.")
            raise SystemExit(1)


def get_sorted_clips(directory, prefix, ext):
    """Scan directory for <prefix><N><ext> files, sort numerically by N."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(ext)}$", re.IGNORECASE)
    clips = []
    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            index = int(match.group(1))
            clips.append((index, os.path.join(directory, filename)))
    clips.sort(key=lambda x: x[0])
    return [path for _, path in clips]


def get_clip_properties(filepath):
    """Return (duration_sec, nb_frames, has_audio) via ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=nb_frames,r_frame_rate,duration',
        '-of', 'json', filepath
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {filepath}: {result.stderr}")

    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    if not streams:
        raise ValueError(f"No video streams in {filepath}")

    stream = streams[0]
    nb_frames_str = stream.get('nb_frames')
    if nb_frames_str and nb_frames_str != 'N/A':
        nb_frames = int(nb_frames_str)
        duration = nb_frames / FPS
    else:
        duration_str = stream.get('duration')
        r_frame_rate = stream.get('r_frame_rate', f'{int(FPS)}/1')
        if duration_str and duration_str != 'N/A':
            duration = float(duration_str)
            if '/' in r_frame_rate:
                num, den = map(int, r_frame_rate.split('/'))
                fps = num / den if den != 0 else FPS
            else:
                fps = float(r_frame_rate)
            nb_frames = round(duration * fps)
        else:
            raise ValueError(f"Could not determine duration/frames for {filepath}")

    audio_cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=codec_type',
        '-of', 'json', filepath
    ]
    audio_result = subprocess.run(audio_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    audio_data = json.loads(audio_result.stdout)
    has_audio = len(audio_data.get('streams', [])) > 0

    return duration, nb_frames, has_audio


def determine_overlap(trans_idx, clip_duration):
    """Auto-calc overlap = decimal part of clip duration."""
    if AUTO_DETECT_OVERLAPS:
        decimal_part = round(clip_duration % 1.0, 4)
        if clip_duration < 1.0:
            return 0.0
        return decimal_part
    return DEFAULT_OVERLAP_SECONDS


def storyboard_durations(path):
    """Return each segment's requested duration from a storyboard JSON."""
    with open(path, encoding="utf-8") as handle:
        storyboard = json.load(handle)
    segments = storyboard.get("segments") or []
    if not segments:
        raise ValueError("storyboard has no segments: {}".format(path))
    return [float(segment["duration"]) for segment in segments]


def build_filter_complex(filepaths, durations, use_clip_audio, master_audio_path):
    """Build FFmpeg filter_complex for hard-cut concat + audio mix.

    With KEEP_DURATIONS (--sb), every clip — including the last — is trimmed to
    the storyboard's requested duration. H3 rounds each request up to a valid
    frame count (frames ≡ 5 mod 17), so keeping the full render would push the
    visuals ahead of the music; this restores the intended timeline.
    """
    filter_chains = []
    v_concat_inputs = []
    a_concat_inputs = []

    if KEEP_DURATIONS is not None and len(KEEP_DURATIONS) != len(filepaths):
        raise RuntimeError(
            "storyboard has {} segments but {} clips were found".format(
                len(KEEP_DURATIONS), len(filepaths)
            )
        )

    for i in range(len(filepaths)):
        if KEEP_DURATIONS is not None:
            keep_duration = min(KEEP_DURATIONS[i], durations[i])
        elif i < len(filepaths) - 1:
            overlap_seconds = determine_overlap(i + 1, durations[i])
            keep_duration = durations[i] - overlap_seconds
        else:
            keep_duration = durations[i]
        if keep_duration <= 0:
            raise RuntimeError(f"Clip {i} keep duration is not positive ({keep_duration:.4f}s)")

        trimmed = durations[i] - keep_duration
        if trimmed > 0.0005:
            kept_frames = round(keep_duration * FPS)
            trimmed_frames = round(trimmed * FPS)
            print(f"  Clip {i}: keep 0.0000s..{keep_duration:.4f}s (~{kept_frames} frames) "
                  f"(trim tail {trimmed:.4f}s | ~{trimmed_frames} frames)")
            filter_chains.append(f"[{i}:v]trim=start=0:end={keep_duration:.4f},setpts=PTS-STARTPTS[v_{i}_cut]")
            if use_clip_audio:
                filter_chains.append(f"[{i}:a]atrim=start=0:end={keep_duration:.4f},asetpts=PTS-STARTPTS[a_{i}_cut]")
        else:
            print(f"  Clip {i}: kept in full ({durations[i]:.4f}s)")
            filter_chains.append(f"[{i}:v]setpts=PTS-STARTPTS[v_{i}_cut]")
            if use_clip_audio:
                filter_chains.append(f"[{i}:a]asetpts=PTS-STARTPTS[a_{i}_cut]")
        v_concat_inputs.append(f"[v_{i}_cut]")
        if use_clip_audio:
            a_concat_inputs.append(f"[a_{i}_cut]")

    # Concat video
    n = len(filepaths)
    concat_v = "".join(v_concat_inputs) + f"concat=n={n}:v=1:a=0,format=yuv420p[v_final]"
    filter_chains.append(concat_v)

    # Concat audio (H3 foley)
    if use_clip_audio:
        concat_a = "".join(a_concat_inputs) + f"concat=n={n}:v=0:a=1[a_foley]"
        filter_chains.append(concat_a)

        # Mix foley (35%) + soundtrack (65%)
        master_idx = len(filepaths)
        filter_chains.append(
            f"[a_foley]volume={FOLEY_VOLUME}[foley_vol];"
            f"[{master_idx}:a]volume={MUSIC_VOLUME}[music_vol];"
            f"[foley_vol][music_vol]amix=inputs=2:duration=first[a_final]"
        )
        return filter_chains, "[v_final]", "[a_final]"
    else:
        return filter_chains, "[v_final]", None


def main():
    parser = argparse.ArgumentParser(
        description="Stitch H3 segments + original soundtrack (H3 audio discarded by default)")
    parser.add_argument("--slug", required=True, help="Slug prefix (e.g., 1409777950540457)")
    parser.add_argument("--output-dir",
                        default=os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(
                                os.path.dirname(os.path.abspath(__file__))))),
                            "outputs"),
                        help="Directory containing segments and soundtrack")
    parser.add_argument("--auto-trim", action="store_true",
                        help="Trim each segment's decimal tail (old behavior; not for H3)")
    parser.add_argument("--sb", metavar="STORYBOARD_JSON",
                        help="Trim every clip to its segments[].duration so the cut "
                             "matches the intended music timeline after H3 frame snapping")
    parser.add_argument("--trim-output", type=float, default=None, metavar="SECONDS",
                        help="Cap the final video/audio at the track duration")
    parser.add_argument("--with-h3-audio", action="store_true",
                        help="Opt into the 65%% soundtrack / 35%% H3 foley mix "
                             "(default: original soundtrack only)")
    parser.add_argument("--audio-offset", type=float, default=0.0, metavar="SECONDS",
                        help="Seek into the soundtrack by this many seconds "
                             "(match render_h3.py --audio-offset)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the ffmpeg command without running it")
    args = parser.parse_args()
    if args.audio_offset < 0:
        parser.error("--audio-offset must be >= 0")

    check_dependencies()

    output_dir = args.output_dir
    slug = args.slug

    # Update config from slug and flags
    global CLIP_PREFIX, MASTER_AUDIO_PATH, AUTO_DETECT_OVERLAPS
    global DEFAULT_OVERLAP_SECONDS, OUTPUT_TRIM_SECONDS, USE_H3_AUDIO
    global KEEP_DURATIONS
    USE_H3_AUDIO = args.with_h3_audio
    CLIP_PREFIX = f"{slug}_seg"
    MASTER_AUDIO_PATH = os.path.join(output_dir, f"{slug}.mp3")
    output_filename = os.path.join(output_dir, f"{slug}.mp4")
    if args.auto_trim:
        AUTO_DETECT_OVERLAPS = True
        DEFAULT_OVERLAP_SECONDS = 0.17
    OUTPUT_TRIM_SECONDS = args.trim_output

    # Find segments
    filepaths = get_sorted_clips(output_dir, CLIP_PREFIX, CLIP_EXTENSION)
    if not filepaths:
        print(f"No files matching '{CLIP_PREFIX}*{CLIP_EXTENSION}' in {output_dir}")
        return
    if len(filepaths) == 1:
        print("Only 1 segment found; writing it through the mix (no cuts).")

    if args.sb:
        try:
            keep = storyboard_durations(args.sb)
        except (OSError, ValueError, KeyError) as exc:
            print(f"Error: cannot read storyboard durations from {args.sb}: {exc}")
            raise SystemExit(1)
        if len(keep) != len(filepaths):
            print(f"Error: storyboard has {len(keep)} segments but "
                  f"{len(filepaths)} clips were found")
            raise SystemExit(1)
        KEEP_DURATIONS = keep

    print(f"\nFound {len(filepaths)} segments:")
    durations = []
    frame_counts = []
    audio_statuses = []

    for idx, path in enumerate(filepaths):
        duration, nb_frames, has_audio = get_clip_properties(path)
        durations.append(duration)
        frame_counts.append(nb_frames)
        audio_statuses.append(has_audio)
        print(f"  [{idx}] {os.path.basename(path)} | Duration: {duration:.4f}s | Frames: {nb_frames}")

    # The original soundtrack replaces the H3 vocal/foley layer unless the
    # caller explicitly opts into the old mix.
    use_clip_audio = all(audio_statuses) and USE_H3_AUDIO
    if not USE_H3_AUDIO:
        print("Audio: original soundtrack only (H3 vocal/foley discarded).")
    elif any(audio_statuses) and not use_clip_audio:
        print("Warning: Some clips lack audio; mixing will use soundtrack only.")

    # Check master audio exists
    use_master_audio = os.path.exists(MASTER_AUDIO_PATH)
    if not use_master_audio:
        print(f"Warning: Soundtrack not found at {MASTER_AUDIO_PATH}")
        print("Proceeding with clip audio only (no mix).")

    # Build filter complex
    filter_chains, v_out, a_out = build_filter_complex(
        filepaths, durations, use_clip_audio, MASTER_AUDIO_PATH
    )

    # Build FFmpeg command
    cmd = ['ffmpeg', '-y']
    for path in filepaths:
        cmd.extend(['-i', path])
    if use_master_audio:
        if args.audio_offset:
            print(f"Audio offset: {args.audio_offset}s into {MASTER_AUDIO_PATH}")
            cmd.extend(['-ss', str(args.audio_offset)])
        cmd.extend(['-i', MASTER_AUDIO_PATH])

    cmd.extend(['-filter_complex', ";".join(filter_chains)])
    cmd.extend(['-map', v_out])
    if a_out:
        cmd.extend(['-map', a_out])
    elif use_master_audio:
        cmd.extend(['-map', f"{len(filepaths)}:a"])
    else:
        cmd.append('-an')

    cmd.extend([
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', str(OUTPUT_CRF),
        '-r', str(FPS)
    ])
    if a_out or use_master_audio:
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
    if use_master_audio and not use_clip_audio:
        cmd.append('-shortest')
    if OUTPUT_TRIM_SECONDS:
        cmd.extend(['-t', str(OUTPUT_TRIM_SECONDS)])

    cmd.append(output_filename)

    print("\nExecuting FFmpeg...")
    print(" ".join(cmd))
    print()

    if args.dry_run:
        print("DRY RUN: no ffmpeg execution")
        return

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✓ Done! Output: {output_filename}")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ FFmpeg failed: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()