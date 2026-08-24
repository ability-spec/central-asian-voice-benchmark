"""
STEP 5C — Build the KSC Kazakh 300-utterance benchmark manifest.

Sampling rule (from STEP 5B analysis):
  Sort speakers by deviceID ascending (as integer).
  First 10 speakers → cap = 11 utterances each.
  Remaining 19 speakers → cap = 10 utterances each.
  Total = 10×11 + 19×10 = 300 exactly.

Deterministic selection within each speaker's pool:
  Pool = all rows for that speaker in test.csv order (file order).
  indices = [i * len(pool) // quota for i in range(quota)]
  (same formula used for the Uzbek USC manifest)

Anomaly handling (deviceID 20872):
  This speaker appears 1× in train.csv and 370× in test.csv.
  The single train uttID is identified and checked.
  If any selected utterance for this speaker is the train uttID,
  it is excluded and replaced by the next utterance not already selected.

No audio is read. No STT calls are made.
"""

import os
import csv
import hashlib
from collections import defaultdict

EXTRACTED = "C:/Users/erkin/central-asian-voice-benchmark/data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac"
META_TEST  = os.path.join(EXTRACTED, "Meta", "test.csv")
META_TRAIN = os.path.join(EXTRACTED, "Meta", "train.csv")
TXT_DIR    = os.path.join(EXTRACTED, "Transcriptions")
OUT_DIR    = "C:/Users/erkin/central-asian-voice-benchmark/research"


# ── 1. Load test.csv ──────────────────────────────────────────────────────
print("Loading test.csv ...", flush=True)
test_rows = []
with open(META_TEST, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=" ")
    for row in reader:
        test_rows.append(row)

total_test = len(test_rows)
assert total_test == 3334, f"Expected 3334 test rows, got {total_test}"
print(f"  Loaded {total_test} rows.", flush=True)

# ── 2. Identify train uttIDs for anomaly check ────────────────────────────
print("Loading train.csv for anomaly check ...", flush=True)
train_utt_ids = set()
with open(META_TRAIN, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=" ")
    for row in reader:
        train_utt_ids.add(row["uttID"].strip())
print(f"  Train uttIDs: {len(train_utt_ids)}", flush=True)

# Check which train uttIDs share a deviceID with test speakers
test_device_ids = {r["deviceID"].strip() for r in test_rows}
anomaly_train_utts = {}   # deviceID → set of train uttIDs for that device
with open(META_TRAIN, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=" ")
    for row in reader:
        dev = row["deviceID"].strip()
        if dev in test_device_ids:
            anomaly_train_utts.setdefault(dev, set()).add(row["uttID"].strip())

print(f"  Train uttIDs belonging to test deviceIDs: "
      f"{sum(len(v) for v in anomaly_train_utts.values())} "
      f"across {len(anomaly_train_utts)} deviceIDs")
for dev, utts in anomaly_train_utts.items():
    print(f"    deviceID={dev}: {len(utts)} train uttIDs — {utts}")
print()

# ── 3. Group test rows by speaker ─────────────────────────────────────────
print("Grouping by speaker ...", flush=True)
speaker_pools = defaultdict(list)
speaker_meta  = {}   # deviceID → metadata from first row
for row in test_rows:
    spk = row["deviceID"].strip()
    speaker_pools[spk].append(row)
    if spk not in speaker_meta:
        speaker_meta[spk] = {
            "gender":     row.get("Gender","").strip(),
            "age":        row.get("Age","").strip(),
            "region":     row.get("Region","").strip(),
            "device":     row.get("Device_Type","").strip(),
            "headphones": row.get("Headphones","").strip(),
        }

unique_speakers = len(speaker_pools)
assert unique_speakers == 29, f"Expected 29 speakers, got {unique_speakers}"
print(f"  {unique_speakers} speakers.", flush=True)

# ── 4. Determine per-speaker cap ──────────────────────────────────────────
# Sort deviceIDs as integers (ascending). First 10 get cap=11, rest get cap=10.
sorted_speakers = sorted(speaker_pools.keys(), key=lambda x: int(x))

cap_assignment = {}
for i, spk in enumerate(sorted_speakers):
    cap_assignment[spk] = 11 if i < 10 else 10

total_check = sum(cap_assignment[spk] for spk in sorted_speakers)
assert total_check == 300, f"Cap sum = {total_check}, not 300"

print("Cap assignments (deviceID → cap):")
for spk in sorted_speakers:
    print(f"  {spk}: cap={cap_assignment[spk]}  (pool={len(speaker_pools[spk])})")
print()

# ── 5. Deterministic selection ────────────────────────────────────────────
print("Selecting utterances ...", flush=True)

selected = []
anomaly_hits = []   # utterances replaced due to train overlap

for spk in sorted_speakers:
    pool  = speaker_pools[spk]
    quota = cap_assignment[spk]
    n     = len(pool)

    # Evenly-spaced indices (same formula as USC manifest)
    indices = [i * n // quota for i in range(quota)]
    chosen  = [pool[idx] for idx in indices]

    # Anomaly check: replace any chosen uttID that appears in train
    train_utts_for_spk = anomaly_train_utts.get(spk, set())
    if train_utts_for_spk:
        chosen_ids = {r["uttID"].strip() for r in chosen}
        conflict   = chosen_ids & train_utts_for_spk
        if conflict:
            print(f"  ANOMALY HIT: deviceID={spk}, conflicting uttIDs={conflict}")
            # Build a replacement set: all test uttIDs for this speaker not already chosen
            # and not in train
            all_pool_ids = [r["uttID"].strip() for r in pool]
            replacement_pool = [r for r in pool
                                if r["uttID"].strip() not in conflict
                                and r["uttID"].strip() not in chosen_ids]
            # Remove the conflicting rows from chosen
            chosen = [r for r in chosen if r["uttID"].strip() not in conflict]
            # Fill back up to quota from replacement_pool
            needed = quota - len(chosen)
            if len(replacement_pool) < needed:
                raise RuntimeError(
                    f"Not enough replacement utterances for speaker {spk}: "
                    f"need {needed}, have {len(replacement_pool)}"
                )
            # Take the first `needed` from replacement_pool (deterministic)
            chosen.extend(replacement_pool[:needed])
            anomaly_hits.append({
                "speaker_id": spk,
                "excluded_uttIDs": list(conflict),
                "replacement_count": needed,
            })

    for row in chosen:
        uid = row["uttID"].strip()
        # Load transcript
        txt_path = os.path.join(TXT_DIR, uid + ".txt")
        if os.path.exists(txt_path):
            with open(txt_path, encoding="utf-8", errors="replace") as f:
                transcript = f.read().strip()
        else:
            transcript = ""

        selected.append({
            "utterance_id": uid,
            "speaker_id":   spk,
            "transcript":   transcript,
            "split":        "test",
            "language":     "kk",
            "source_type":  "studio_crowdsourced",
            "gender":       speaker_meta[spk]["gender"],
            "age":          speaker_meta[spk]["age"],
            "region":       speaker_meta[spk]["region"],
            "device_type":  speaker_meta[spk]["device"],
            "headphones":   speaker_meta[spk]["headphones"],
        })

print(f"Selected {len(selected)} utterances.", flush=True)

# ── 6. Verification ───────────────────────────────────────────────────────
print("\nRunning verification checks ...", flush=True)

assert len(selected) == 300, f"Expected 300, got {len(selected)}"

utt_ids = [r["utterance_id"] for r in selected]
assert len(set(utt_ids)) == 300, "Duplicate utterance IDs detected!"

spk_ids = [r["speaker_id"] for r in selected]
from collections import Counter
spk_counts = Counter(spk_ids)
assert len(spk_counts) == 29, f"Expected 29 speakers, got {len(spk_counts)}"

# Verify caps
for spk, cnt in spk_counts.items():
    expected = cap_assignment[spk]
    assert cnt == expected, f"Speaker {spk}: expected {expected}, got {cnt}"

# Verify all IDs are in test split
test_utt_ids = {r["uttID"].strip() for r in test_rows}
for uid in utt_ids:
    assert uid in test_utt_ids, f"Manifest ID not in test split: {uid}"

# Verify no train contamination
for uid in utt_ids:
    assert uid not in train_utt_ids, f"Manifest ID found in train split: {uid}"

# Verify transcripts present
missing_transcripts = [r for r in selected if not r["transcript"]]
assert len(missing_transcripts) == 0, f"{len(missing_transcripts)} missing transcripts"

# Verify no missing required fields
for r in selected:
    for field in ["utterance_id", "speaker_id", "transcript", "split", "language"]:
        assert r[field], f"Missing field {field!r} in row {r['utterance_id']}"

print("  All verification checks passed.", flush=True)

# ── 7. Write CSV manifest ─────────────────────────────────────────────────
csv_path = os.path.join(OUT_DIR, "kazakh_benchmark_manifest.csv")
fieldnames = [
    "utterance_id", "speaker_id", "transcript", "split", "language",
    "source_type", "gender", "age", "region", "device_type", "headphones",
]
with open(csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(selected)

print(f"\nManifest written: {csv_path}", flush=True)

# SHA-256
with open(csv_path, "rb") as f:
    manifest_sha256 = hashlib.sha256(f.read()).hexdigest()
print(f"Manifest SHA-256: {manifest_sha256}", flush=True)

# ── 8. Build statistics ───────────────────────────────────────────────────
spk_table  = sorted(spk_counts.items(), key=lambda x: -x[1])
spk_values = sorted(spk_counts.values())
min_spk    = spk_values[0]
max_spk    = spk_values[-1]
med_spk    = spk_values[len(spk_values) // 2]

# ── 9. Write statistics markdown ─────────────────────────────────────────
md_path = os.path.join(OUT_DIR, "kazakh_manifest_statistics.md")

lines = []
lines.append("# Kazakh Benchmark Manifest — Selection Rationale and Statistics")
lines.append("")
lines.append("**Date:** 2026-08-23")
lines.append("**Manifest file:** `research/kazakh_benchmark_manifest.csv`")
lines.append(f"**Manifest SHA-256:** `{manifest_sha256}`")
lines.append("**Status:** Manifest only. No audio downloaded. No STT calls made.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Source")
lines.append("")
lines.append("Dataset: ISSAI KSC v1.1 — OpenSLR SLR102")
lines.append("Corpus: ISSAI Kazakh Speech Corpus (EACL 2021), CC BY 4.0")
lines.append("Test split: 3,334 utterances, 29 speakers")
lines.append("Metadata: `Meta/test.csv` (space-separated: uttID deviceID Gender Age Region Device_Type Headphones)")
lines.append("Audio: `Audios_flac/<uttID>.flac` (FLAC lossless, WAV 16 kHz 16-bit equivalent)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Sampling Rule")
lines.append("")
lines.append("### Why a cap is needed")
lines.append("")
lines.append("The raw test split has moderate speaker imbalance:")
lines.append("- Top speaker (deviceID 15872): 434 utterances (13.0% of test split)")
lines.append("- Top 2 speakers: 804 utterances (24.1% of test split)")
lines.append("- Without a cap, a 300-utterance sample would over-represent these 2 speakers")
lines.append("  (e.g., speaker 15872 alone would contribute ~39 utterances at proportional sampling)")
lines.append("")
lines.append("### Cap calculation")
lines.append("")
lines.append("Unlike USC (where a flat cap of 12 gave exactly 300), KSC requires a mixed strategy:")
lines.append("")
lines.append("| Cap | Total utterances |")
lines.append("|---|---|")
lines.append("| 10 | 290 (10 short) |")
lines.append("| 11 | 319 (19 over) |")
lines.append("")
lines.append("**Solution:** Give 10 speakers cap=11 and 19 speakers cap=10.")
lines.append("10×11 + 19×10 = 110 + 190 = **300 exactly**.")
lines.append("")
lines.append("### Which speakers get cap=11")
lines.append("")
lines.append("Sort speakers by `deviceID` ascending (as integer).")
lines.append("Assign cap=11 to the first 10 in this order; cap=10 to the remaining 19.")
lines.append("This rule is transparent (deterministic sort on a stable numeric field),")
lines.append("requires no random seed, and is reproducible from the manifest alone.")
lines.append("")
lines.append("### Utterance selection within each speaker's pool")
lines.append("")
lines.append("Pool = all test.csv rows for that speaker, in file order.")
lines.append("For speaker with pool size `n` and quota `q`:")
lines.append("")
lines.append("```")
lines.append("indices = [i * n // q for i in range(q)]")
lines.append("```")
lines.append("")
lines.append("This spreads selection across the speaker's full row range deterministically.")
lines.append("(Same formula used in the Uzbek USC manifest, STEP 4B.)")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Anomaly: DeviceID 20872 Train/Test Overlap")
lines.append("")
lines.append("DeviceID 20872 appears in both `train.csv` (1 utterance) and `test.csv` (370 utterances).")
lines.append("The paper states 'three sets of non-overlapping speakers'; this is a minor data release error.")
lines.append("")
lines.append("**Mitigation applied:**")
lines.append("Before finalizing selection for speaker 20872, the single train uttID was identified.")
lines.append("All 10 selected utterances for this speaker were checked against the train set.")

if anomaly_hits:
    lines.append("")
    lines.append(f"**ANOMALY HIT: {len(anomaly_hits)} replacement(s) made.**")
    for hit in anomaly_hits:
        lines.append(f"- Speaker {hit['speaker_id']}: excluded uttIDs {hit['excluded_uttIDs']}, "
                     f"replaced with {hit['replacement_count']} next-available test utterance(s).")
else:
    lines.append("")
    lines.append("**Result: No anomaly hit.** None of the 10 evenly-spaced indices for speaker 20872")
    lines.append("landed on the single train uttID. The 10 selected utterances are all test-only.")
    lines.append("The manifest is free of train contamination for this speaker.")

lines.append("")
lines.append("The selected 300 utterances have been verified to contain no train uttIDs.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Verification Results")
lines.append("")
lines.append(f"| Check | Result |")
lines.append(f"|---|---|")
lines.append(f"| Total utterances | **{len(selected)}** (target: 300) |")
lines.append(f"| Unique speakers | **{len(spk_counts)}** (target: 29) |")
lines.append(f"| Duplicate utterance IDs | **0** |")
lines.append(f"| All IDs in KSC test split | **YES** |")
lines.append(f"| Any ID in KSC train split | **NO** |")
lines.append(f"| Missing transcripts | **0** |")
lines.append(f"| Missing required fields | **0** |")
lines.append(f"| Speaker cap compliance | **YES** — all speakers match intended cap |")
lines.append(f"| Minimum utterances/speaker | **{min_spk}** |")
lines.append(f"| Maximum utterances/speaker | **{max_spk}** |")
lines.append(f"| Median utterances/speaker | **{med_spk}** |")
lines.append(f"| Manifest SHA-256 | `{manifest_sha256}` |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Speaker Distribution in Manifest")
lines.append("")
lines.append("| Rank | DeviceID | Utterances | % of benchmark | Cap | Gender | Age | Region | Device | Headphones |")
lines.append("|---|---|---|---|---|---|---|---|---|---|")
for rank, (spk, cnt) in enumerate(spk_table, 1):
    m = speaker_meta[spk]
    cap = cap_assignment[spk]
    lines.append(f"| {rank} | {spk} | {cnt} | {cnt/300*100:.1f}% | {cap} | "
                 f"{m['gender']} | {m['age']} | {m['region']} | {m['device']} | {m['headphones']} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Speaker Metadata Coverage in Manifest")
lines.append("")
genders = Counter(speaker_meta[spk]["gender"] for spk in spk_counts)
regions = Counter(speaker_meta[spk]["region"] for spk in spk_counts)
devices = Counter(speaker_meta[spk]["device"] for spk in spk_counts)
hps     = Counter(speaker_meta[spk]["headphones"] for spk in spk_counts)
ages    = sorted(int(speaker_meta[spk]["age"]) for spk in spk_counts)
lines.append(f"| Field | Distribution |")
lines.append(f"|---|---|")
lines.append(f"| Gender | {', '.join(f'{k}: {v}' for k,v in sorted(genders.items()))} |")
lines.append(f"| Age range | {ages[0]}–{ages[-1]} years (median {ages[len(ages)//2]}) |")
lines.append(f"| Region | {', '.join(f'{k}: {v}' for k,v in sorted(regions.items()))} |")
lines.append(f"| Device type | {', '.join(f'{k}: {v}' for k,v in sorted(devices.items()))} |")
lines.append(f"| Headphones | {', '.join(f'{k}: {v}' for k,v in sorted(hps.items()))} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Source Type")
lines.append("")
lines.append("All utterances: `source_type = studio_crowdsourced`")
lines.append("")
lines.append("KSC v1.1 was collected via a mobile application deployed to crowdsourced volunteers.")
lines.append("Speakers read prompted text in a controlled (studio-quality) mobile-recording environment.")
lines.append("This is READ speech (prompted text), not spontaneous conversational speech.")
lines.append("The source type applies uniformly to all 29 test speakers.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Contamination Risk")
lines.append("")
lines.append("All selected utterances: **CONTAMINATION-RISK: MEDIUM**")
lines.append("")
lines.append("KSC was published in 2021 and has been publicly available since.")
lines.append("Commercial model training data may include KSC audio. This label applies")
lines.append("to every row in the manifest and must appear in all published result tables.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## License")
lines.append("")
lines.append("**CC BY 4.0** — confirmed in EACL 2021 paper text and ISSAI website.")
lines.append("Attribution required. Commercial and research use permitted.")
lines.append("The HuggingFace card for `issai/kazakh_speech_corpus` incorrectly states MIT;")
lines.append("the authoritative license is CC BY 4.0 from the ISSAI website and paper.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("*No audio has been downloaded for benchmarking. No STT calls have been made.*")
lines.append("*This manifest pins the exact 300 utterances for the Kazakh STT benchmark.*")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Statistics written: {md_path}", flush=True)

# ── 10. Console summary ───────────────────────────────────────────────────
print("\n=== MANIFEST SUMMARY ===")
print(f"Total utterances:        {len(selected)}")
print(f"Unique speakers:         {len(spk_counts)}")
print(f"Min utterances/speaker:  {min_spk}")
print(f"Max utterances/speaker:  {max_spk}")
print(f"Dominant speaker share:  {max_spk/300*100:.1f}%")
print(f"Anomaly hits (replaced): {len(anomaly_hits)}")
print(f"Manifest SHA-256:        {manifest_sha256}")
print(f"\nTop 5 speakers in manifest:")
for spk, cnt in spk_table[:5]:
    raw = len(speaker_pools[spk])
    m = speaker_meta[spk]
    print(f"  {spk}: {cnt}/300 ({cnt/300*100:.1f}%)  [raw test: {raw}]  "
          f"G={m['gender']} Age={m['age']} Region={m['region']}")
print(f"\nAll 29 speakers represented: {'YES' if len(spk_counts) == 29 else 'NO'}")
print(f"Train contamination free:    YES")
