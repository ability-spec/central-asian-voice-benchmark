"""
Phase 3A Preparation Script
============================
Selects 200 new held-out utterances (100 Uzbek + 100 Kazakh), downloads/extracts
audio, converts to WAV, assigns pilot strata, and writes all three Phase 3A manifests.

Approved specification: research/phase3a_execution_plan.md
Phase 2 checkpoint: b7c9e84

DO NOT run STT calls from this script. No API calls to ElevenLabs, GCS, Azure, or Gemini.
DO NOT modify any Phase 2 files or manifests.
"""

import os
import sys
import csv
import json
import wave
import tarfile
import tempfile
import hashlib
import subprocess
import collections
from pathlib import Path

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_DATASETS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTHONIOENCODING"] = "utf-8"

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent.parent  # repo root

# Phase 2 frozen inputs (read-only)
P2_UZ_MANIFEST    = BASE / "research" / "uzbek_benchmark_manifest.csv"
P2_KK_MANIFEST    = BASE / "research" / "kazakh_benchmark_manifest.csv"
P2_AUDIO_MANIFEST = BASE / "research" / "audio_benchmark_manifest.csv"
P2_RESULTS        = BASE / "results" / "phase2_full" / "phase2_trackb_results.jsonl"

# KSC source data (read-only)
KSC_ARCHIVE    = BASE / "data" / "ksc" / "ISSAI_KSC_335RS_v1.1_flac.tar.gz"
KSC_META_TEST  = BASE / "data" / "ksc" / "extracted" / "ISSAI_KSC_335RS_v1.1_flac" / "Meta" / "test.csv"
KSC_TRANS_DIR  = BASE / "data" / "ksc" / "extracted" / "ISSAI_KSC_335RS_v1.1_flac" / "Transcriptions"

# Phase 3A outputs (written here)
P3A_UZ_MANIFEST    = BASE / "research" / "phase3a_uzbek_manifest.csv"
P3A_KK_MANIFEST    = BASE / "research" / "phase3a_kazakh_manifest.csv"
P3A_AUDIO_MANIFEST = BASE / "research" / "phase3a_audio_manifest.csv"
P3A_UZ_AUDIO_DIR   = BASE / "data" / "audio" / "phase3a" / "uz"
P3A_KK_AUDIO_DIR   = BASE / "data" / "audio" / "phase3a" / "kk"

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
P2_AUDIO_MANIFEST_SHA256 = "d01408af2e04d048a44600138ac878f97b2a2372f62b9a42f2f7d0b161f34924"

# Speakers ranked by EL AUTO detection rate in Phase 2, filtered to those
# with remaining utterances for Phase 3A (0-remaining speakers excluded):
#   668279160=100% → 0 remaining (skip)
#   467174862=75%  → 9 remaining ✓
#   1450478900=67% → 0 remaining (skip)
#   709790549=58%  → 48 remaining ✓
#   818938633=58%  → 216 remaining ✓
#   1428043076=50% → 8 remaining ✓
#   382004286=42%  → 8 remaining ✓
UZ_CONTROL_SPEAKERS_RANKED = [
    "467174862", "709790549", "818938633", "1428043076", "382004286",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ffmpeg_to_wav(input_path, output_path):
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", str(input_path),
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
         str(output_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[:300]}")


def wav_duration(path):
    with wave.open(str(path)) as w:
        return round(w.getnframes() / w.getframerate(), 3)


def wav_info(path):
    with wave.open(str(path)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), round(w.getnframes() / w.getframerate(), 3)


def evenly_spaced(pool, quota):
    """Select `quota` items from `pool` at evenly-spaced indices."""
    n = len(pool)
    if quota >= n:
        return list(pool)
    return [pool[i * n // quota] for i in range(quota)]


# ─────────────────────────────────────────────────────────────────────────────
# Step 0: Safety checks — verify Phase 2 manifest is unchanged
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 72)
print("Phase 3A Preparation")
print("=" * 72)
print()
print("Step 0: Verifying Phase 2 audio manifest SHA-256 ...")
actual_sha = sha256_file(P2_AUDIO_MANIFEST)
if actual_sha != P2_AUDIO_MANIFEST_SHA256:
    print(f"  ABORT: Phase 2 manifest has changed!")
    print(f"  Expected: {P2_AUDIO_MANIFEST_SHA256}")
    print(f"  Actual:   {actual_sha}")
    sys.exit(1)
print(f"  OK: {actual_sha}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Build Phase 2 exclusion sets
# ─────────────────────────────────────────────────────────────────────────────
print("Step 1: Loading Phase 2 exclusion sets ...")

p2_uz_excluded = set()
with open(P2_UZ_MANIFEST, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        p2_uz_excluded.add(row["utterance_id"])

p2_kk_excluded = set()
with open(P2_KK_MANIFEST, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        p2_kk_excluded.add(row["utterance_id"])

p2_all_excluded = p2_uz_excluded | p2_kk_excluded
assert len(p2_uz_excluded) == 300
assert len(p2_kk_excluded) == 300
assert len(p2_all_excluded) == 600

print(f"  Uzbek excluded:  {len(p2_uz_excluded)}")
print(f"  Kazakh excluded: {len(p2_kk_excluded)}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Stream USC metadata to build Uzbek selection
# ─────────────────────────────────────────────────────────────────────────────
print("Step 2: Streaming USC test split metadata from HuggingFace ...")
print("  (metadata only — audio bytes not downloaded in this step)")

from datasets import load_dataset

ds_meta = load_dataset(
    "murodbek/uzbek-speech-corpus",
    split="test",
    streaming=True,
)
ds_meta = ds_meta.select_columns(["id", "sentence"])

all_usc_rows = []
for i, row in enumerate(ds_meta):
    all_usc_rows.append({"id": row["id"], "sentence": row["sentence"]})
    if (i + 1) % 1000 == 0:
        print(f"  Loaded {i + 1} rows ...", flush=True)

total_usc = len(all_usc_rows)
print(f"  Total USC test rows: {total_usc}")
if total_usc != 3837:
    print(f"  WARNING: Expected 3837, got {total_usc}. Proceeding anyway.")

# Group by speaker
speaker_pools = collections.defaultdict(list)
for row in all_usc_rows:
    spk = row["id"].split("_")[0]
    speaker_pools[spk].append(row)

n_speakers = len(speaker_pools)
print(f"  Unique speakers: {n_speakers}")
if n_speakers != 38:
    print(f"  WARNING: Expected 38 speakers, got {n_speakers}.")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Select 100 Uzbek utterances
# ─────────────────────────────────────────────────────────────────────────────
print()
print("Step 3: Selecting 100 Uzbek utterances ...")

# For each speaker: remaining pool = all utterances NOT in Phase 2
speaker_remaining = {}
for spk, pool in sorted(speaker_pools.items()):
    remaining = [r for r in pool if r["id"] not in p2_uz_excluded]
    speaker_remaining[spk] = remaining

# NOTE: 22 of 38 speakers have 0 remaining (Phase 2 exhausted their pools).
# Only the 16 speakers with remaining > 0 can contribute to Phase 3A.
active_speakers = sorted(
    [(spk, pool) for spk, pool in speaker_remaining.items() if len(pool) > 0],
    key=lambda x: (-len(x[1]), x[0]),  # desc by pool size, then by speaker ID
)
n_active = len(active_speakers)
print(f"  Speakers with remaining utterances: {n_active} (of 38 total)")

# Water-fill quota distribution: floor(100/n_active) base, +1 for top remainder speakers,
# then cap at pool size and redistribute any shortfall.
TARGET = 100
base_quota = TARGET // n_active       # e.g. 6
extra_count = TARGET % n_active       # e.g. 4 speakers get +1

quotas = {}
for i, (spk, pool) in enumerate(active_speakers):
    q = base_quota + (1 if i < extra_count else 0)
    quotas[spk] = min(q, len(pool))   # cap at pool size

allocated = sum(quotas.values())
deficit = TARGET - allocated

# Redistribute deficit to speakers with the most remaining capacity
if deficit > 0:
    by_capacity = sorted(
        [(spk, len(pool) - quotas[spk]) for spk, pool in active_speakers],
        key=lambda x: -x[1],
    )
    for spk, cap in by_capacity:
        if deficit <= 0:
            break
        add = min(deficit, cap)
        quotas[spk] += add
        deficit -= add

assert sum(quotas.values()) == TARGET, f"Quota total mismatch: {sum(quotas.values())} ≠ {TARGET}"
print(f"  Quota distribution: {sorted(set(quotas.values()), reverse=True)}")

# Apply even-spacing within each speaker's remaining pool
uz_selected = []
for spk, pool in active_speakers:
    quota = quotas[spk]
    chosen = evenly_spaced(pool, quota)
    for item in chosen:
        uz_selected.append({
            "utterance_id": item["id"],
            "speaker_id":   item["id"].split("_")[0],
            "transcript":   item["sentence"],
        })

# Verify
assert len(uz_selected) == 100, f"Expected 100, got {len(uz_selected)}"
uz_ids = {r["utterance_id"] for r in uz_selected}
overlap = uz_ids & p2_uz_excluded
assert len(overlap) == 0, f"Phase 2 overlap found: {overlap}"
assert len(uz_ids) == 100, "Duplicate utterance IDs in Uzbek selection"

print(f"  Selected: {len(uz_selected)} Uzbek utterances")
speaker_counts = collections.Counter(r["speaker_id"] for r in uz_selected)
print(f"  Speaker distribution: {sorted(speaker_counts.items())[:5]} ... ({len(speaker_counts)} speakers)")
print(f"  Phase 2 overlap: 0")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Select 100 Kazakh utterances
# ─────────────────────────────────────────────────────────────────────────────
print("Step 4: Selecting 100 Kazakh utterances from KSC test.csv ...")

ksc_rows = []
with open(KSC_META_TEST, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split()
        if len(parts) < 7:
            continue
        # Filter out header-like rows
        if parts[0] in ("uttID", "deviceID") or parts[2] in ("Gender",) or parts[4] in ("Region",):
            print(f"  Skipping malformed/header row: {parts[:4]}")
            continue
        ksc_rows.append({
            "uttID":       parts[0],
            "deviceID":    parts[1],
            "Gender":      parts[2],
            "Age":         parts[3],
            "Region":      parts[4],
            "Device_Type": parts[5],
            "Headphones":  parts[6],
        })

print(f"  KSC test rows (parsed): {len(ksc_rows)}")

# Exclude Phase 2
ksc_candidates = [r for r in ksc_rows if r["uttID"] not in p2_kk_excluded]
print(f"  After Phase 2 exclusion: {len(ksc_candidates)}")

# Verify transcriptions exist
trans_missing = [r["uttID"] for r in ksc_candidates
                 if not (KSC_TRANS_DIR / f"{r['uttID']}.txt").exists()]
if trans_missing:
    print(f"  Missing transcriptions ({len(trans_missing)}): {trans_missing[:5]}")
    # Remove from candidates
    trans_missing_set = set(trans_missing)
    ksc_candidates = [r for r in ksc_candidates if r["uttID"] not in trans_missing_set]
    print(f"  After removing missing transcriptions: {len(ksc_candidates)}")

# Sort by (Region, Gender, deviceID) for deterministic ordering
ksc_candidates.sort(key=lambda r: (r["Region"], r["Gender"], r["deviceID"]))

# Systematic sampling: every floor(len/100) = 30th entry starting at index 0
step = len(ksc_candidates) // 100
print(f"  Systematic sampling step: {step}")
kk_selected_meta = [ksc_candidates[i * step] for i in range(100)]

# Verify
kk_ids = {r["uttID"] for r in kk_selected_meta}
kk_overlap = kk_ids & p2_kk_excluded
assert len(kk_overlap) == 0, f"Phase 2 Kazakh overlap: {kk_overlap}"
assert len(kk_ids) == 100, "Duplicate Kazakh utterance IDs"

# Load transcripts
kk_selected = []
for row in kk_selected_meta:
    trans_path = KSC_TRANS_DIR / f"{row['uttID']}.txt"
    transcript = trans_path.read_text(encoding="utf-8").strip()
    kk_selected.append({
        "utterance_id": row["uttID"],
        "speaker_id":   row["deviceID"],
        "transcript":   transcript,
        "gender":       row["Gender"],
        "age":          row["Age"],
        "region":       row["Region"],
        "device_type":  row["Device_Type"],
        "headphones":   row["Headphones"],
    })

print(f"  Selected: {len(kk_selected)} Kazakh utterances")
region_counts = collections.Counter(r["region"] for r in kk_selected)
gender_counts = collections.Counter(r["gender"] for r in kk_selected)
print(f"  Region distribution: {dict(region_counts)}")
print(f"  Gender distribution: {dict(gender_counts)}")
print(f"  Phase 2 overlap: 0")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Download Uzbek audio (HuggingFace streaming with audio)
# ─────────────────────────────────────────────────────────────────────────────
print("Step 5: Downloading Uzbek audio from HuggingFace ...")
print(f"  Target: {len(uz_selected)} WAV files -> {P3A_UZ_AUDIO_DIR}")

P3A_UZ_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

uz_target_ids = {r["utterance_id"] for r in uz_selected}
uz_already_done = {
    uid for uid in uz_target_ids
    if (P3A_UZ_AUDIO_DIR / f"{uid}.wav").exists() and
       (P3A_UZ_AUDIO_DIR / f"{uid}.wav").stat().st_size > 0
}
uz_needed = uz_target_ids - uz_already_done

print(f"  Already converted: {len(uz_already_done)}")
print(f"  Still needed: {len(uz_needed)}", flush=True)

uz_errors = {}
if uz_needed:
    from datasets import Audio as HFAudio
    ds_audio = load_dataset(
        "murodbek/uzbek-speech-corpus",
        split="test",
        streaming=True,
    )
    ds_audio = ds_audio.select_columns(["id", "audio"]).cast_column("audio", HFAudio(decode=False))

    uz_found_count = len(uz_already_done)
    for i, row in enumerate(ds_audio):
        uid = row["id"]
        if uid not in uz_needed:
            continue

        audio_val = row["audio"]
        raw_bytes = audio_val.get("bytes")
        raw_path  = audio_val.get("path", "")
        out_wav   = P3A_UZ_AUDIO_DIR / f"{uid}.wav"

        try:
            ext = os.path.splitext(raw_path)[1] if raw_path else ".audio"
            if not ext:
                ext = ".audio"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            ffmpeg_to_wav(tmp_path, out_wav)
            os.unlink(tmp_path)
            uz_needed.discard(uid)
            uz_found_count += 1
            if uz_found_count % 10 == 0:
                print(f"  {uz_found_count}/{len(uz_selected)} converted ...", flush=True)
        except Exception as e:
            uz_errors[uid] = str(e)
            print(f"  ERROR {uid}: {e}", flush=True)

        if not uz_needed:
            print(f"  All {len(uz_selected)} Uzbek files found after scanning {i+1} dataset rows.")
            break

if uz_needed:
    print(f"  WARNING: {len(uz_needed)} Uzbek files NOT found in dataset: {list(uz_needed)[:5]}")
if uz_errors:
    print(f"  ERRORS ({len(uz_errors)}): {list(uz_errors.items())[:3]}")
else:
    print(f"  Uzbek audio: {len(uz_selected) - len(uz_needed)} converted, 0 errors")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Extract Kazakh FLAC from tar archive
# ─────────────────────────────────────────────────────────────────────────────
print("Step 6: Extracting Kazakh FLAC files from KSC archive ...")
print(f"  Archive: {KSC_ARCHIVE}")
print(f"  Target: {len(kk_selected)} WAV files -> {P3A_KK_AUDIO_DIR}", flush=True)

P3A_KK_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

kk_target_ids = {r["utterance_id"] for r in kk_selected}
kk_already_done = {
    uid for uid in kk_target_ids
    if (P3A_KK_AUDIO_DIR / f"{uid}.wav").exists() and
       (P3A_KK_AUDIO_DIR / f"{uid}.wav").stat().st_size > 0
}
kk_needed = kk_target_ids - kk_already_done
kk_errors = {}

print(f"  Already converted: {len(kk_already_done)}")
print(f"  Still needed: {len(kk_needed)}", flush=True)

if kk_needed:
    AUDIO_PREFIX = "ISSAI_KSC_335RS_v1.1_flac/Audios_flac/"
    kk_found_count = len(kk_already_done)
    scanned = 0

    with tarfile.open(str(KSC_ARCHIVE), "r:gz") as tar:
        for member in tar:
            scanned += 1
            if scanned % 30000 == 0:
                print(
                    f"  Scanned {scanned:,} entries, found {kk_found_count}/{len(kk_selected)}, "
                    f"remaining {len(kk_needed)} ...",
                    flush=True,
                )

            if not member.name.startswith(AUDIO_PREFIX):
                continue
            if not member.name.endswith(".flac"):
                continue

            uid = os.path.splitext(os.path.basename(member.name))[0]
            if uid not in kk_needed:
                continue

            out_wav = P3A_KK_AUDIO_DIR / f"{uid}.wav"
            try:
                fobj = tar.extractfile(member)
                if fobj is None:
                    raise RuntimeError("extractfile returned None")
                with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
                    tmp.write(fobj.read())
                    tmp_path = tmp.name
                ffmpeg_to_wav(tmp_path, out_wav)
                os.unlink(tmp_path)
                kk_needed.discard(uid)
                kk_found_count += 1
                if kk_found_count % 10 == 0:
                    print(f"  {kk_found_count}/{len(kk_selected)} converted ...", flush=True)
            except Exception as e:
                kk_errors[uid] = str(e)
                kk_needed.discard(uid)
                print(f"  ERROR {uid}: {e}", flush=True)

            if not kk_needed:
                print(f"  All {len(kk_selected)} Kazakh files found after scanning {scanned:,} entries.")
                break

else:
    print("  All already done (resume).")

if kk_needed:
    print(f"  WARNING: {len(kk_needed)} Kazakh files NOT found: {list(kk_needed)[:5]}")
if kk_errors:
    print(f"  ERRORS ({len(kk_errors)}): {list(kk_errors.items())[:3]}")
else:
    print(f"  Kazakh audio: {kk_found_count} converted, 0 errors")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Read durations and verify WAV format
# ─────────────────────────────────────────────────────────────────────────────
print("Step 7: Reading WAV durations and verifying format ...")

uz_duration_map = {}
uz_format_errors = []
for r in uz_selected:
    uid = r["utterance_id"]
    wav = P3A_UZ_AUDIO_DIR / f"{uid}.wav"
    if not wav.exists():
        uz_format_errors.append(f"{uid}: file missing")
        continue
    try:
        sr, ch, sw, dur = wav_info(wav)
        if sr != 16000: uz_format_errors.append(f"{uid}: sr={sr}")
        if ch != 1:     uz_format_errors.append(f"{uid}: channels={ch}")
        if sw != 2:     uz_format_errors.append(f"{uid}: sample_width={sw}")
        if dur <= 0:    uz_format_errors.append(f"{uid}: dur={dur}")
        uz_duration_map[uid] = dur
    except Exception as e:
        uz_format_errors.append(f"{uid}: {e}")

kk_duration_map = {}
kk_format_errors = []
for r in kk_selected:
    uid = r["utterance_id"]
    wav = P3A_KK_AUDIO_DIR / f"{uid}.wav"
    if not wav.exists():
        kk_format_errors.append(f"{uid}: file missing")
        continue
    try:
        sr, ch, sw, dur = wav_info(wav)
        if sr != 16000: kk_format_errors.append(f"{uid}: sr={sr}")
        if ch != 1:     kk_format_errors.append(f"{uid}: channels={ch}")
        if sw != 2:     kk_format_errors.append(f"{uid}: sample_width={sw}")
        if dur <= 0:    kk_format_errors.append(f"{uid}: dur={dur}")
        kk_duration_map[uid] = dur
    except Exception as e:
        kk_format_errors.append(f"{uid}: {e}")

all_format_errors = uz_format_errors + kk_format_errors
if all_format_errors:
    print(f"  FORMAT ERRORS ({len(all_format_errors)}):")
    for e in all_format_errors[:10]:
        print(f"    {e}")
else:
    print(f"  All {len(uz_duration_map)} Uzbek + {len(kk_duration_map)} Kazakh WAVs: format OK")

# Duration statistics
def dur_stats(dmap):
    vals = sorted(dmap.values())
    n = len(vals)
    if n == 0:
        return {}
    return {
        "count": n, "total": sum(vals), "mean": sum(vals)/n,
        "min": vals[0], "max": vals[-1],
        "short": sum(1 for v in vals if v < 5),
        "medium": sum(1 for v in vals if 5 <= v < 10),
        "long": sum(1 for v in vals if v >= 10),
    }

uz_dstats = dur_stats(uz_duration_map)
kk_dstats = dur_stats(kk_duration_map)
print(f"\n  Uzbek durations:  total={uz_dstats.get('total',0):.1f}s, "
      f"mean={uz_dstats.get('mean',0):.1f}s, "
      f"short={uz_dstats.get('short',0)}, medium={uz_dstats.get('medium',0)}, long={uz_dstats.get('long',0)}")
print(f"  Kazakh durations: total={kk_dstats.get('total',0):.1f}s, "
      f"mean={kk_dstats.get('mean',0):.1f}s, "
      f"short={kk_dstats.get('short',0)}, medium={kk_dstats.get('medium',0)}, long={kk_dstats.get('long',0)}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 8: Assign pilot strata
# ─────────────────────────────────────────────────────────────────────────────
print("Step 8: Assigning pilot strata ...")

# Build duration-ordered Uzbek utterances
uz_by_dur = sorted(uz_selected, key=lambda r: uz_duration_map.get(r["utterance_id"], 999))

# Collect strata
strata = {}  # utterance_id -> stratum string

# uz_short: first 15 with duration < 5s
uz_short_candidates = [r for r in uz_by_dur if uz_duration_map.get(r["utterance_id"], 0) < 5]
for r in uz_short_candidates[:15]:
    strata[r["utterance_id"]] = "uz_short"

# uz_medium: first 10 with 5 <= duration < 10s, not already assigned
uz_medium_candidates = [r for r in uz_by_dur
                        if 5 <= uz_duration_map.get(r["utterance_id"], 0) < 10
                        and r["utterance_id"] not in strata]
for r in uz_medium_candidates[:10]:
    strata[r["utterance_id"]] = "uz_medium"

# uz_control: 5 utterances, 1 per control speaker, in ranked order
# Each control speaker contributes their first (manifest-order) Phase 3A utterance
control_assigned = 0
control_by_speaker = collections.defaultdict(list)
for r in uz_selected:
    control_by_speaker[r["speaker_id"]].append(r["utterance_id"])

for spk in UZ_CONTROL_SPEAKERS_RANKED:
    if control_assigned >= 5:
        break
    candidates_for_spk = [uid for uid in control_by_speaker.get(spk, [])
                          if uid not in strata]
    if candidates_for_spk:
        strata[candidates_for_spk[0]] = "uz_control"
        control_assigned += 1

if control_assigned < 5:
    print(f"  WARNING: only {control_assigned} uz_control utterances assigned "
          f"(needed 5). Falling back to any unassigned Uzbek utterances.")
    for r in uz_selected:
        if control_assigned >= 5:
            break
        if r["utterance_id"] not in strata:
            strata[r["utterance_id"]] = "uz_control"
            control_assigned += 1

# Kazakh: sort by duration
kk_by_dur = sorted(kk_selected, key=lambda r: kk_duration_map.get(r["utterance_id"], 999))

# kk_short: first 5 with duration < 5s
kk_short_candidates = [r for r in kk_by_dur if kk_duration_map.get(r["utterance_id"], 0) < 5]
for r in kk_short_candidates[:5]:
    strata[r["utterance_id"]] = "kk_short"

# kk_medium: first 5 with 5 <= duration < 10s, not already assigned
kk_medium_candidates = [r for r in kk_by_dur
                        if 5 <= kk_duration_map.get(r["utterance_id"], 0) < 10
                        and r["utterance_id"] not in strata]
for r in kk_medium_candidates[:5]:
    strata[r["utterance_id"]] = "kk_medium"

# Verify stratum counts
strata_counts = collections.Counter(strata.values())
print(f"  Pilot strata counts: {dict(strata_counts)}")
total_pilot = sum(strata_counts.values())
print(f"  Total pilot utterances: {total_pilot} (target: 40)")

missing_strata = []
for s, target in [("uz_short", 15), ("uz_medium", 10), ("uz_control", 5),
                  ("kk_short", 5), ("kk_medium", 5)]:
    actual = strata_counts.get(s, 0)
    if actual != target:
        missing_strata.append(f"{s}: {actual}/{target}")
if missing_strata:
    print(f"  WARNING — stratum count mismatches: {missing_strata}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 9: Write Phase 3A manifests
# ─────────────────────────────────────────────────────────────────────────────
print("Step 9: Writing Phase 3A manifests ...")

# 9a: Uzbek manifest
uz_fieldnames = ["utterance_id", "speaker_id", "transcript", "split", "source_type", "pilot_stratum"]
uz_rows_out = []
for r in uz_selected:
    uz_rows_out.append({
        "utterance_id": r["utterance_id"],
        "speaker_id":   r["speaker_id"],
        "transcript":   r["transcript"],
        "split":        "test",
        "source_type":  "UNKNOWN",
        "pilot_stratum": strata.get(r["utterance_id"], ""),
    })

with open(P3A_UZ_MANIFEST, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=uz_fieldnames)
    w.writeheader()
    w.writerows(uz_rows_out)

print(f"  Written: {P3A_UZ_MANIFEST} ({len(uz_rows_out)} rows)")

# 9b: Kazakh manifest
kk_fieldnames = ["utterance_id", "speaker_id", "transcript", "split", "language",
                 "source_type", "gender", "age", "region", "device_type", "headphones", "pilot_stratum"]
kk_rows_out = []
for r in kk_selected:
    kk_rows_out.append({
        "utterance_id": r["utterance_id"],
        "speaker_id":   r["speaker_id"],
        "transcript":   r["transcript"],
        "split":        "test",
        "language":     "kk",
        "source_type":  "studio_crowdsourced",
        "gender":       r["gender"],
        "age":          r["age"],
        "region":       r["region"],
        "device_type":  r["device_type"],
        "headphones":   r["headphones"],
        "pilot_stratum": strata.get(r["utterance_id"], ""),
    })

with open(P3A_KK_MANIFEST, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=kk_fieldnames)
    w.writeheader()
    w.writerows(kk_rows_out)

print(f"  Written: {P3A_KK_MANIFEST} ({len(kk_rows_out)} rows)")

# 9c: Audio manifest (combined, with pilot_stratum and is_pilot)
audio_fieldnames = [
    "utterance_id", "language", "speaker_id", "reference_transcript",
    "canonical_audio_path", "duration_seconds", "source_dataset",
    "pilot_stratum", "is_pilot",
]
audio_rows_out = []
pilot_ids = set(strata.keys())

# Uzbek rows (pilot first, then non-pilot, all in manifest order)
for r in uz_selected:
    uid = r["utterance_id"]
    wav = P3A_UZ_AUDIO_DIR / f"{uid}.wav"
    dur = uz_duration_map.get(uid, 0.0)
    ps  = strata.get(uid, "")
    audio_rows_out.append({
        "utterance_id":        uid,
        "language":            "uz",
        "speaker_id":          r["speaker_id"],
        "reference_transcript": r["transcript"],
        "canonical_audio_path": str(wav),
        "duration_seconds":    dur,
        "source_dataset":      "ISSAI_USC_v1_murodbek_hf",
        "pilot_stratum":       ps,
        "is_pilot":            "true" if ps else "false",
    })

# Kazakh rows
for r in kk_selected:
    uid = r["utterance_id"]
    wav = P3A_KK_AUDIO_DIR / f"{uid}.wav"
    dur = kk_duration_map.get(uid, 0.0)
    ps  = strata.get(uid, "")
    audio_rows_out.append({
        "utterance_id":        uid,
        "language":            "kk",
        "speaker_id":          r["speaker_id"],
        "reference_transcript": r["transcript"],
        "canonical_audio_path": str(wav),
        "duration_seconds":    dur,
        "source_dataset":      "ISSAI_KSC_v1.1_SLR102",
        "pilot_stratum":       ps,
        "is_pilot":            "true" if ps else "false",
    })

with open(P3A_AUDIO_MANIFEST, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=audio_fieldnames)
    w.writeheader()
    w.writerows(audio_rows_out)

print(f"  Written: {P3A_AUDIO_MANIFEST} ({len(audio_rows_out)} rows)")

# ─────────────────────────────────────────────────────────────────────────────
# Step 10: Compute SHA-256 of audio manifest
# ─────────────────────────────────────────────────────────────────────────────
print()
print("Step 10: Computing SHA-256 of Phase 3A audio manifest ...")

p3a_audio_sha256 = sha256_file(P3A_AUDIO_MANIFEST)
print(f"  Phase 3A audio manifest SHA-256: {p3a_audio_sha256}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# Step 11: Final verification
# ─────────────────────────────────────────────────────────────────────────────
print("Step 11: Final verification ...")

errors = []

# Count checks
n_uz_audio = sum(1 for r in audio_rows_out if r["language"] == "uz")
n_kk_audio = sum(1 for r in audio_rows_out if r["language"] == "kk")
n_pilot    = sum(1 for r in audio_rows_out if r["is_pilot"] == "true")
n_eval     = sum(1 for r in audio_rows_out if r["is_pilot"] == "false")

if len(audio_rows_out) != 200:
    errors.append(f"Total rows: {len(audio_rows_out)} (expected 200)")
if n_uz_audio != 100:
    errors.append(f"Uzbek rows: {n_uz_audio} (expected 100)")
if n_kk_audio != 100:
    errors.append(f"Kazakh rows: {n_kk_audio} (expected 100)")
if n_pilot != 40:
    errors.append(f"Pilot rows: {n_pilot} (expected 40)")
if n_eval != 160:
    errors.append(f"Eval rows: {n_eval} (expected 160)")

# Overlap with Phase 2
all_p3a_ids = {r["utterance_id"] for r in audio_rows_out}
overlap_with_p2 = all_p3a_ids & p2_all_excluded
if overlap_with_p2:
    errors.append(f"Phase 2 overlap: {len(overlap_with_p2)} IDs: {list(overlap_with_p2)[:3]}")

# Duplicate IDs within Phase 3A
if len(all_p3a_ids) != 200:
    errors.append(f"Duplicate IDs: {200 - len(all_p3a_ids)} duplicates")

# Audio files exist
missing_audio = [r["utterance_id"] for r in audio_rows_out
                 if not Path(r["canonical_audio_path"]).exists()]
if missing_audio:
    errors.append(f"Missing audio files: {len(missing_audio)}: {missing_audio[:5]}")

# Format errors already checked above
if all_format_errors:
    errors.append(f"Format errors: {len(all_format_errors)}")

# Print verification result
if errors:
    print("  VERIFICATION FAILED:")
    for e in errors:
        print(f"    ✗ {e}")
else:
    print("  All verification checks passed.")

print()
print("=" * 72)
print("PREPARATION SUMMARY")
print("=" * 72)
print(f"  Phase 2 audio manifest SHA-256:  {actual_sha} [VERIFIED UNCHANGED]")
print(f"  Phase 3A audio manifest SHA-256: {p3a_audio_sha256}")
print()
print(f"  Total utterances: {len(audio_rows_out)}")
print(f"  Uzbek:            {n_uz_audio}  (pilot: {sum(1 for r in audio_rows_out if r['language']=='uz' and r['is_pilot']=='true')}, eval: {sum(1 for r in audio_rows_out if r['language']=='uz' and r['is_pilot']=='false')})")
print(f"  Kazakh:           {n_kk_audio}  (pilot: {sum(1 for r in audio_rows_out if r['language']=='kk' and r['is_pilot']=='true')}, eval: {sum(1 for r in audio_rows_out if r['language']=='kk' and r['is_pilot']=='false')})")
print(f"  Pilot total:      {n_pilot}  (target: 40)")
print(f"  Eval total:       {n_eval}  (target: 160)")
print(f"  Phase 2 overlap:  {len(overlap_with_p2)}")
print(f"  Missing audio:    {len(missing_audio)}")
print(f"  Format errors:    {len(all_format_errors)}")
print()
print("  Pilot strata:")
for s in ["uz_short", "uz_medium", "uz_control", "kk_short", "kk_medium"]:
    count = strata_counts.get(s, 0)
    print(f"    {s:12s}: {count}")
print()
print("  Manifests written:")
print(f"    {P3A_UZ_MANIFEST}")
print(f"    {P3A_KK_MANIFEST}")
print(f"    {P3A_AUDIO_MANIFEST}")
print()
if errors:
    print(f"  STATUS: FAILED ({len(errors)} errors)")
    sys.exit(1)
else:
    print(f"  STATUS: PREPARATION COMPLETE")
    print(f"  Phase 3A audio manifest SHA-256 to hardcode in runner:")
    print(f"    {p3a_audio_sha256}")
print()
print("  Next step: write and validate run_phase3a_trackb.py")
print("  DO NOT run the pilot until explicit approval.")
