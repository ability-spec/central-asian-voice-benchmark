"""
STEP 5B — KSC test-split speaker distribution analysis.

Uses confirmed archive structure:
  Meta/test.csv       — space-separated: uttID deviceID Gender Age Region Device_Type Headphones
  Transcriptions/<uttID>.txt — one transcript per file

Speaker ID = deviceID field.
No audio is read. No STT calls are made.
"""

import os
import csv
import json
import hashlib
from collections import defaultdict, Counter

EXTRACTED = "C:/Users/erkin/central-asian-voice-benchmark/data/ksc/extracted/ISSAI_KSC_335RS_v1.1_flac"
META_TEST  = os.path.join(EXTRACTED, "Meta", "test.csv")
META_DEV   = os.path.join(EXTRACTED, "Meta", "dev.csv")
META_TRAIN = os.path.join(EXTRACTED, "Meta", "train.csv")
TXT_DIR    = os.path.join(EXTRACTED, "Transcriptions")
OUT_DIR    = "C:/Users/erkin/central-asian-voice-benchmark/research"

print("Loading test.csv ...")

# ── 1. Parse test.csv ────────────────────────────────────────────────────
test_rows = []
with open(META_TEST, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=" ")
    for row in reader:
        test_rows.append(row)

print(f"  Rows: {len(test_rows)}")
print(f"  Columns: {list(test_rows[0].keys())}")
print(f"  Sample: {test_rows[0]}")
print()

# ── 2. Load transcripts for test utterances ──────────────────────────────
print("Loading test transcripts ...")
utt_transcripts = {}
missing_txt = 0
for row in test_rows:
    uid = row["uttID"].strip()
    txt_path = os.path.join(TXT_DIR, uid + ".txt")
    if os.path.exists(txt_path):
        with open(txt_path, encoding="utf-8", errors="replace") as f:
            utt_transcripts[uid] = f.read().strip()
    else:
        utt_transcripts[uid] = ""
        missing_txt += 1
print(f"  Loaded: {len(utt_transcripts) - missing_txt} transcripts, {missing_txt} missing")
print()

# ── 3. Verify speaker and utterance IDs from other splits don't overlap ──
print("Verifying speaker disjointness ...")

def load_speaker_ids(path):
    ids = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=" ")
        for row in reader:
            ids.add(row["deviceID"].strip())
    return ids

test_speakers  = {r["deviceID"].strip() for r in test_rows}
dev_speakers   = load_speaker_ids(META_DEV)
train_speakers = load_speaker_ids(META_TRAIN)

overlap_test_dev   = test_speakers & dev_speakers
overlap_test_train = test_speakers & train_speakers
overlap_dev_train  = dev_speakers  & train_speakers

print(f"  Test speakers:  {len(test_speakers)}")
print(f"  Dev speakers:   {len(dev_speakers)}")
print(f"  Train speakers: {len(train_speakers)}")
print(f"  Test ∩ Dev:     {len(overlap_test_dev)}  {'OVERLAP DETECTED' if overlap_test_dev else 'DISJOINT ✓'}")
print(f"  Test ∩ Train:   {len(overlap_test_train)}  {'OVERLAP DETECTED' if overlap_test_train else 'DISJOINT ✓'}")
print(f"  Dev ∩ Train:    {len(overlap_dev_train)}  {'OVERLAP DETECTED' if overlap_dev_train else 'DISJOINT ✓'}")
print()

# ── 4. Build speaker pools ───────────────────────────────────────────────
speaker_pools = defaultdict(list)
for row in test_rows:
    spk = row["deviceID"].strip()
    uid = row["uttID"].strip()
    speaker_pools[spk].append({
        "uttID": uid,
        "gender": row.get("Gender","").strip(),
        "age": row.get("Age","").strip(),
        "region": row.get("Region","").strip(),
        "device": row.get("Device_Type","").strip(),
        "headphones": row.get("Headphones","").strip(),
        "transcript": utt_transcripts.get(uid, ""),
    })

# ── 5. Distribution statistics ───────────────────────────────────────────
speaker_counts = {spk: len(utts) for spk, utts in speaker_pools.items()}
total_test     = sum(speaker_counts.values())
unique_speakers = len(speaker_counts)
counts_sorted  = sorted(speaker_counts.values())
min_count      = counts_sorted[0]
max_count      = counts_sorted[-1]
median_count   = counts_sorted[unique_speakers // 2]
mean_count     = total_test // unique_speakers

speaker_table = sorted(speaker_counts.items(), key=lambda x: -x[1])

print("=== TEST SPLIT SUMMARY ===")
print(f"Total test utterances:  {total_test}")
print(f"Unique speakers:        {unique_speakers}")
print(f"Min utterances/speaker: {min_count}")
print(f"Max utterances/speaker: {max_count}")
print(f"Median utt/speaker:     {median_count}")
print(f"Mean utt/speaker:       {mean_count}")
print()
print("Full per-speaker distribution:")
for rank, (spk, cnt) in enumerate(speaker_table, 1):
    sample = speaker_pools[spk][0]
    print(f"  {rank:2d}. deviceID={spk:6s}  {cnt:4d} utts ({cnt/total_test*100:.1f}%)  "
          f"G={sample['gender']} Age={sample['age']} Region={sample['region']} "
          f"Dev={sample['device']} HP={sample['headphones']}")
print()

# ── 6. Sampling feasibility ───────────────────────────────────────────────
TARGET = 300
print(f"=== SAMPLING FEASIBILITY (target={TARGET}) ===")
for cap in range(1, max_count + 1):
    total_at_cap = sum(min(cnt, cap) for cnt in speaker_counts.values())
    if total_at_cap >= TARGET:
        print(f"  Flat cap={cap}: total={total_at_cap} from {unique_speakers} speakers", end="")
        if total_at_cap == TARGET:
            print("  *** EXACT MATCH ***")
        else:
            under = sum(min(cnt, cap-1) for cnt in speaker_counts.values())
            print(f"  (cap={cap-1} gives {under}, {TARGET-under} short; cap={cap} gives {total_at_cap}, {total_at_cap-TARGET} over)")
        break

# Check each cap systematically for exact match
print()
print("Searching for any cap giving exactly 300:")
found_exact = False
for cap in range(1, max_count + 1):
    total_at_cap = sum(min(cnt, cap) for cnt in speaker_counts.values())
    if total_at_cap == TARGET:
        print(f"  EXACT: flat cap={cap} → {total_at_cap} utterances from {unique_speakers} speakers")
        found_exact = True
if not found_exact:
    print("  No flat cap gives exactly 300. Mixed strategy needed.")
    # Find the two caps that straddle 300
    for cap in range(1, max_count + 1):
        total_at_cap = sum(min(cnt, cap) for cnt in speaker_counts.values())
        if total_at_cap > TARGET:
            under = sum(min(cnt, cap-1) for cnt in speaker_counts.values())
            over  = total_at_cap
            print(f"  cap={cap-1}: {under} utterances ({TARGET-under} short)")
            print(f"  cap={cap}:   {over} utterances ({over-TARGET} over)")
            # Mixed strategy: use cap for some speakers, cap-1 for others
            # Number of speakers that need cap (vs cap-1) to reach exactly 300
            # speakers at cap-1 gives (under) utterances; need (300-under) more
            # each such speaker contributes 1 extra utterance at cap vs cap-1
            extras_needed = TARGET - under
            # Find which speakers have enough utterances for the cap level
            eligible = [(spk, cnt) for spk, cnt in speaker_counts.items() if cnt >= cap]
            print(f"  Mixed strategy: {len(eligible)} speakers have ≥{cap} utterances")
            print(f"  Assign cap={cap} to {extras_needed} of them, cap={cap-1} to the rest")
            print(f"  Result: {under - (len(eligible) - extras_needed)*(cap-1 - (cap-1))} + ... = 300")
            print(f"  Simplest rule: sort speakers by deviceID; first {extras_needed} eligible speakers get cap={cap}, rest get cap={cap-1}")
            break
print()

# ── 7. Save JSON summary ─────────────────────────────────────────────────
summary = {
    "total_test_utterances": total_test,
    "unique_speakers": unique_speakers,
    "min_per_speaker": min_count,
    "max_per_speaker": max_count,
    "median_per_speaker": median_count,
    "mean_per_speaker": mean_count,
    "disjoint_test_dev":   len(overlap_test_dev) == 0,
    "disjoint_test_train": len(overlap_test_train) == 0,
    "speaker_distribution": [
        {
            "rank": rank,
            "speaker_id": spk,
            "utterances": cnt,
            "pct": round(cnt / total_test * 100, 1),
            "gender": speaker_pools[spk][0]["gender"],
            "age": speaker_pools[spk][0]["age"],
            "region": speaker_pools[spk][0]["region"],
            "device": speaker_pools[spk][0]["device"],
            "headphones": speaker_pools[spk][0]["headphones"],
        }
        for rank, (spk, cnt) in enumerate(speaker_table, 1)
    ],
}

summary_path = os.path.join(OUT_DIR, "ksc_test_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"Summary saved: {summary_path}")
