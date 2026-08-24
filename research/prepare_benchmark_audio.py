"""
STEP 6A — Prepare frozen benchmark audio set.

Produces exactly 600 WAV files:
  benchmark_audio/uzbek/<utterance_id>.wav   (300 files — from murodbek/uzbek-speech-corpus)
  benchmark_audio/kazakh/<utterance_id>.wav  (300 files — from ISSAI KSC archive FLAC)

All output files are: 16 kHz, mono, 16-bit PCM WAV.

No STT APIs are called. No models are run.
"""

import os
import csv
import wave
import tarfile
import tempfile
import hashlib
import subprocess
import sys

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_DATASETS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTHONIOENCODING"] = "utf-8"

BASE   = "C:/Users/erkin/central-asian-voice-benchmark"
UZ_MANIFEST  = os.path.join(BASE, "research", "uzbek_benchmark_manifest.csv")
KK_MANIFEST  = os.path.join(BASE, "research", "kazakh_benchmark_manifest.csv")
UZ_AUDIO_DIR = os.path.join(BASE, "benchmark_audio", "uzbek")
KK_AUDIO_DIR = os.path.join(BASE, "benchmark_audio", "kazakh")
KSC_ARCHIVE  = os.path.join(BASE, "data", "ksc", "ISSAI_KSC_335RS_v1.1_flac.tar.gz")
OUT_MANIFEST = os.path.join(BASE, "research", "audio_benchmark_manifest.csv")
OUT_STATS    = os.path.join(BASE, "research", "audio_benchmark_statistics.md")

os.makedirs(UZ_AUDIO_DIR, exist_ok=True)
os.makedirs(KK_AUDIO_DIR, exist_ok=True)


def ffmpeg_to_wav(input_path, output_path):
    """Convert any audio file to 16kHz mono 16-bit PCM WAV using ffmpeg."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", input_path,
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
         output_path],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {input_path}: {r.stderr[:200]}")


def wav_info(path):
    """Return (sample_rate, channels, sample_width_bytes, duration_seconds)."""
    with wave.open(path) as w:
        return (
            w.getframerate(),
            w.getnchannels(),
            w.getsampwidth(),
            w.getnframes() / w.getframerate(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Load manifests
# ═══════════════════════════════════════════════════════════════════════════
print("Loading manifests ...", flush=True)

uz_rows = list(csv.DictReader(open(UZ_MANIFEST, encoding="utf-8")))
kk_rows = list(csv.DictReader(open(KK_MANIFEST, encoding="utf-8")))

uz_targets = {r["utterance_id"]: r for r in uz_rows}
kk_targets = {r["utterance_id"]: r for r in kk_rows}

assert len(uz_targets) == 300, f"Expected 300 Uzbek, got {len(uz_targets)}"
assert len(kk_targets) == 300, f"Expected 300 Kazakh, got {len(kk_targets)}"
print(f"  Uzbek manifest: {len(uz_targets)} utterances", flush=True)
print(f"  Kazakh manifest: {len(kk_targets)} utterances", flush=True)

# Master manifest rows will be built here
master_rows = []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Uzbek audio — HuggingFace streaming
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Uzbek audio (HuggingFace streaming) ──", flush=True)

from datasets import load_dataset, Audio as HFAudio

uz_ds = load_dataset(
    "murodbek/uzbek-speech-corpus",
    split="test",
    streaming=True,
)
uz_ds = uz_ds.select_columns(["id", "audio"]).cast_column("audio", HFAudio(decode=False))

uz_found = 0
uz_errors = []

for row in uz_ds:
    uid = row["id"]
    if uid not in uz_targets:
        continue

    audio_val = row["audio"]
    raw_bytes = audio_val.get("bytes")
    raw_path  = audio_val.get("path", "")

    out_wav = os.path.join(UZ_AUDIO_DIR, f"{uid}.wav")

    # Skip if already converted (resume support)
    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
        uz_found += 1
        if uz_found % 50 == 0:
            print(f"  [resume] {uz_found}/300 done ...", flush=True)
        continue

    try:
        # Determine temp file extension from path hint
        ext = os.path.splitext(raw_path)[1] if raw_path else ".audio"
        if not ext:
            ext = ".audio"

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        ffmpeg_to_wav(tmp_path, out_wav)
        os.unlink(tmp_path)

        uz_found += 1
        if uz_found % 50 == 0:
            print(f"  {uz_found}/300 converted ...", flush=True)

    except Exception as e:
        uz_errors.append((uid, str(e)))
        print(f"  ERROR: {uid} — {e}", flush=True)

    if uz_found >= 300 and len(uz_errors) == 0:
        break  # All found and converted

print(f"  Uzbek done: {uz_found} converted, {len(uz_errors)} errors", flush=True)

# Add Uzbek rows to master manifest
for r in uz_rows:
    uid = r["utterance_id"]
    wav_path = os.path.join(UZ_AUDIO_DIR, f"{uid}.wav")
    if os.path.exists(wav_path):
        sr, ch, sw, dur = wav_info(wav_path)
        master_rows.append({
            "utterance_id":        uid,
            "language":            "uz",
            "speaker_id":          r["speaker_id"],
            "reference_transcript": r["transcript"],
            "canonical_audio_path": wav_path,
            "duration_seconds":    round(dur, 3),
            "source_dataset":      "ISSAI_USC_v1_murodbek_hf",
        })


# ═══════════════════════════════════════════════════════════════════════════
# 3. Kazakh audio — KSC archive streaming
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Kazakh audio (KSC archive streaming) ──", flush=True)
print(f"  Archive: {KSC_ARCHIVE}", flush=True)
print(f"  Targets: {len(kk_targets)} FLAC files to extract and convert", flush=True)

kk_remaining = {
    uid for uid in kk_targets
    if not (os.path.exists(os.path.join(KK_AUDIO_DIR, f"{uid}.wav")) and
            os.path.getsize(os.path.join(KK_AUDIO_DIR, f"{uid}.wav")) > 0)
}
kk_found = len(kk_targets) - len(kk_remaining)
kk_errors = []

if kk_remaining:
    print(f"  Need to extract: {len(kk_remaining)} (already done: {kk_found})", flush=True)
    AUDIO_PREFIX = "ISSAI_KSC_335RS_v1.1_flac/Audios_flac/"

    with tarfile.open(KSC_ARCHIVE, "r:gz") as tar:
        scanned = 0
        for member in tar:
            scanned += 1
            if scanned % 20000 == 0:
                print(
                    f"  Scanned {scanned:,} entries, found {kk_found}/300, "
                    f"remaining {len(kk_remaining)} ...",
                    flush=True,
                )

            if not member.name.startswith(AUDIO_PREFIX):
                continue
            if not member.name.endswith(".flac"):
                continue

            uid = os.path.splitext(os.path.basename(member.name))[0]
            if uid not in kk_remaining:
                continue

            out_wav = os.path.join(KK_AUDIO_DIR, f"{uid}.wav")
            try:
                f = tar.extractfile(member)
                if f is None:
                    raise RuntimeError("extractfile returned None")

                with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
                    tmp.write(f.read())
                    tmp_path = tmp.name

                ffmpeg_to_wav(tmp_path, out_wav)
                os.unlink(tmp_path)

                kk_remaining.discard(uid)
                kk_found += 1

                if kk_found % 50 == 0:
                    print(f"  {kk_found}/300 converted ...", flush=True)

            except Exception as e:
                kk_errors.append((uid, str(e)))
                kk_remaining.discard(uid)
                print(f"  ERROR: {uid} — {e}", flush=True)

            if not kk_remaining:
                print(f"  All 300 Kazakh files found after scanning {scanned:,} entries.", flush=True)
                break
else:
    print(f"  All 300 already done (resume).", flush=True)

if kk_remaining:
    print(f"  WARNING: {len(kk_remaining)} Kazakh files NOT found in archive: {kk_remaining}", flush=True)

print(f"  Kazakh done: {kk_found} converted, {len(kk_errors)} errors", flush=True)

# Add Kazakh rows to master manifest
for r in kk_rows:
    uid = r["utterance_id"]
    wav_path = os.path.join(KK_AUDIO_DIR, f"{uid}.wav")
    if os.path.exists(wav_path):
        sr, ch, sw, dur = wav_info(wav_path)
        master_rows.append({
            "utterance_id":        uid,
            "language":            "kk",
            "speaker_id":          r["speaker_id"],
            "reference_transcript": r["transcript"],
            "canonical_audio_path": wav_path,
            "duration_seconds":    round(dur, 3),
            "source_dataset":      "ISSAI_KSC_v1.1_SLR102",
        })


# ═══════════════════════════════════════════════════════════════════════════
# 4. Verification
# ═══════════════════════════════════════════════════════════════════════════
print("\n── Verification ──", flush=True)

errors = []

uz_master = [r for r in master_rows if r["language"] == "uz"]
kk_master = [r for r in master_rows if r["language"] == "kk"]

# Count checks
if len(master_rows) != 600:
    errors.append(f"Total rows: {len(master_rows)} (expected 600)")
if len(uz_master) != 300:
    errors.append(f"Uzbek rows: {len(uz_master)} (expected 300)")
if len(kk_master) != 300:
    errors.append(f"Kazakh rows: {len(kk_master)} (expected 300)")

# Duplicate IDs
all_ids = [r["utterance_id"] for r in master_rows]
if len(set(all_ids)) != len(all_ids):
    errors.append("Duplicate utterance_id found")

# Per-file checks
bad_sr = bad_ch = bad_sw = bad_dur = bad_tx = 0
for r in master_rows:
    path = r["canonical_audio_path"]
    if not os.path.exists(path):
        errors.append(f"Missing file: {path}")
        continue
    try:
        sr, ch, sw, dur = wav_info(path)
        if sr != 16000: bad_sr += 1
        if ch != 1:     bad_ch += 1
        if sw != 2:     bad_sw += 1
        if dur <= 0:    bad_dur += 1
    except Exception as e:
        errors.append(f"Cannot open {path}: {e}")
    if not r["reference_transcript"]:
        bad_tx += 1

if bad_sr:  errors.append(f"{bad_sr} files with wrong sample rate (not 16000)")
if bad_ch:  errors.append(f"{bad_ch} files not mono")
if bad_sw:  errors.append(f"{bad_sw} files not 16-bit")
if bad_dur: errors.append(f"{bad_dur} files with zero duration")
if bad_tx:  errors.append(f"{bad_tx} files with missing transcript")

if errors:
    print("VERIFICATION FAILED:", flush=True)
    for e in errors:
        print(f"  ✗ {e}", flush=True)
    sys.exit(1)
else:
    print("  All verification checks passed.", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Duration statistics
# ═══════════════════════════════════════════════════════════════════════════
def stats(durations):
    d = sorted(durations)
    n = len(d)
    return {
        "count":   n,
        "total":   sum(d),
        "min":     d[0],
        "max":     d[-1],
        "mean":    sum(d) / n,
        "median":  d[n // 2],
    }

uz_durs = [r["duration_seconds"] for r in uz_master]
kk_durs = [r["duration_seconds"] for r in kk_master]
all_durs = uz_durs + kk_durs

uz_stats = stats(uz_durs)
kk_stats = stats(kk_durs)
all_stats = stats(all_durs)

print(f"\n  Uzbek:  total={uz_stats['total']:.1f}s ({uz_stats['total']/60:.1f} min), "
      f"mean={uz_stats['mean']:.1f}s, min={uz_stats['min']:.1f}s, max={uz_stats['max']:.1f}s", flush=True)
print(f"  Kazakh: total={kk_stats['total']:.1f}s ({kk_stats['total']/60:.1f} min), "
      f"mean={kk_stats['mean']:.1f}s, min={kk_stats['min']:.1f}s, max={kk_stats['max']:.1f}s", flush=True)
print(f"  Total:  {all_stats['total']:.1f}s ({all_stats['total']/60:.1f} min)", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# 6. Write master manifest CSV
# ═══════════════════════════════════════════════════════════════════════════
fieldnames = [
    "utterance_id", "language", "speaker_id", "reference_transcript",
    "canonical_audio_path", "duration_seconds", "source_dataset",
]
with open(OUT_MANIFEST, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(master_rows)

sha256 = hashlib.sha256(open(OUT_MANIFEST, "rb").read()).hexdigest()
print(f"\n  Master manifest: {OUT_MANIFEST}", flush=True)
print(f"  SHA-256: {sha256}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Write statistics markdown
# ═══════════════════════════════════════════════════════════════════════════
def fmt_dur(s):
    m, sec = divmod(int(s), 60)
    h, m   = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"

lines = []
lines.append("# Audio Benchmark Set — Statistics")
lines.append("")
lines.append("**Date:** 2026-08-23")
lines.append(f"**Master manifest:** `research/audio_benchmark_manifest.csv`")
lines.append(f"**Manifest SHA-256:** `{sha256}`")
lines.append("**Status:** Frozen audio set. No STT calls made.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## File Counts")
lines.append("")
lines.append("| Language | Files | Directory |")
lines.append("|---|---|---|")
lines.append(f"| Uzbek | {len(uz_master)} | `benchmark_audio/uzbek/` |")
lines.append(f"| Kazakh | {len(kk_master)} | `benchmark_audio/kazakh/` |")
lines.append(f"| **Total** | **{len(master_rows)}** | — |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Audio Specification")
lines.append("")
lines.append("| Parameter | Value |")
lines.append("|---|---|")
lines.append("| Sample rate | 16,000 Hz |")
lines.append("| Channels | 1 (mono) |")
lines.append("| Bit depth | 16-bit PCM |")
lines.append("| Format | WAV (PCM) |")
lines.append("| Encoding | Linear PCM (uncompressed) |")
lines.append("")
lines.append("All files verified: sample rate, channel count, bit depth, non-zero duration.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Duration Statistics")
lines.append("")
lines.append("| Metric | Uzbek | Kazakh | Combined |")
lines.append("|---|---|---|---|")
lines.append(f"| Total duration | {fmt_dur(uz_stats['total'])} ({uz_stats['total']:.1f}s) | {fmt_dur(kk_stats['total'])} ({kk_stats['total']:.1f}s) | {fmt_dur(all_stats['total'])} ({all_stats['total']:.1f}s) |")
lines.append(f"| Mean per utterance | {uz_stats['mean']:.2f}s | {kk_stats['mean']:.2f}s | {all_stats['mean']:.2f}s |")
lines.append(f"| Median per utterance | {uz_stats['median']:.2f}s | {kk_stats['median']:.2f}s | {all_stats['median']:.2f}s |")
lines.append(f"| Shortest utterance | {uz_stats['min']:.2f}s | {kk_stats['min']:.2f}s | {all_stats['min']:.2f}s |")
lines.append(f"| Longest utterance | {uz_stats['max']:.2f}s | {kk_stats['max']:.2f}s | {all_stats['max']:.2f}s |")
lines.append(f"| Utterance count | {uz_stats['count']} | {kk_stats['count']} | {all_stats['count']} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Source Datasets")
lines.append("")
lines.append("| Language | Source | Format | License |")
lines.append("|---|---|---|---|")
lines.append("| Uzbek | ISSAI USC v1 via `murodbek/uzbek-speech-corpus` (HuggingFace) | Embedded WAV → 16kHz mono WAV | CC BY 4.0 |")
lines.append("| Kazakh | ISSAI KSC v1.1 — OpenSLR SLR102 | FLAC → 16kHz mono WAV | CC BY 4.0 |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Conversion")
lines.append("")
lines.append("All audio converted with ffmpeg 8.1.1:")
lines.append("```")
lines.append("ffmpeg -y -loglevel error -i <input> -ar 16000 -ac 1 -sample_fmt s16 <output.wav>")
lines.append("```")
lines.append("")
lines.append("No pitch, speed, or spectral modifications were applied.")
lines.append("Resampling uses ffmpeg default (sinc interpolation).")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Verification Results")
lines.append("")
lines.append("| Check | Result |")
lines.append("|---|---|")
lines.append(f"| Total files | **{len(master_rows)}** (target: 600) |")
lines.append(f"| Uzbek files | **{len(uz_master)}** (target: 300) |")
lines.append(f"| Kazakh files | **{len(kk_master)}** (target: 300) |")
lines.append(f"| Duplicate utterance IDs | **0** |")
lines.append(f"| Files with wrong sample rate | **{bad_sr}** |")
lines.append(f"| Files not mono | **{bad_ch}** |")
lines.append(f"| Files not 16-bit | **{bad_sw}** |")
lines.append(f"| Files with zero duration | **{bad_dur}** |")
lines.append(f"| Missing transcripts | **{bad_tx}** |")
lines.append(f"| Manifest SHA-256 | `{sha256}` |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("*No STT APIs have been called. No models have been run.*")
lines.append("*This is the frozen audio input set for the benchmark.*")

with open(OUT_STATS, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"  Statistics: {OUT_STATS}", flush=True)

print("\n=== STEP 6A COMPLETE ===")
print(f"600 WAV files ready in benchmark_audio/")
print(f"Master manifest: research/audio_benchmark_manifest.csv")
print(f"Statistics:      research/audio_benchmark_statistics.md")
