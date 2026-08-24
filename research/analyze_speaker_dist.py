"""
STEP 4A — USC test-split speaker distribution analysis.
Loads only id and sentence columns (no audio download).
"""
import sys
import os
from collections import Counter, OrderedDict

# Suppress HuggingFace progress noise
os.environ["HF_DATASETS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from datasets import load_dataset

print("Loading USC test split (id + sentence columns only)...", flush=True)

ds = load_dataset(
    "murodbek/uzbek-speech-corpus",
    split="test",
    streaming=True,
)
# Drop audio column before iteration to avoid requiring torchcodec
ds = ds.select_columns(["id", "sentence"])

utterances = []
for i, row in enumerate(ds):
    utt_id = row["id"]
    sentence = row["sentence"]
    speaker_id = utt_id.split("_")[0]
    utterances.append({"id": utt_id, "speaker_id": speaker_id, "sentence": sentence})
    if (i + 1) % 500 == 0:
        print(f"  Processed {i+1} rows...", flush=True)

print(f"Done. Loaded {len(utterances)} rows.", flush=True)

# --- Analysis ---
total = len(utterances)
speaker_counts = Counter(u["speaker_id"] for u in utterances)
unique_speakers = len(speaker_counts)

counts = sorted(speaker_counts.values())
min_count = counts[0]
max_count = counts[-1]
median_count = counts[unique_speakers // 2]

# Sort speakers by utterance count descending
speaker_table = sorted(speaker_counts.items(), key=lambda x: -x[1])

# Speakers with fewer than 10 utterances
low_speakers = [(spk, cnt) for spk, cnt in speaker_table if cnt < 10]

# Sampling feasibility: can we get 300 utterances from >= 10 speakers
# with no speaker contributing more than, say, 50 utterances?
cap = 50
capped_total = sum(min(cnt, cap) for cnt in speaker_counts.values())
speakers_contributing = sum(1 for cnt in speaker_counts.values() if cnt >= 1)

# With a cap of floor(300/num_speakers) each, how many utterances from each?
target = 300
per_speaker_floor = target // unique_speakers
per_speaker_cap = max(10, per_speaker_floor + 5)
capped_sample = sum(min(cnt, per_speaker_cap) for cnt in speaker_counts.values())

# Output
lines = []
lines.append("# USC Test-Split Speaker Distribution Analysis")
lines.append("")
lines.append("**Date:** 2026-08-23")
lines.append("**Dataset:** murodbek/uzbek-speech-corpus, split=test")
lines.append("**Source corpus:** ISSAI Uzbek Speech Corpus (arXiv:2107.14419)")
lines.append("**Status:** Metadata only — no audio downloaded, no STT calls.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Summary Statistics")
lines.append("")
lines.append(f"| Metric | Value |")
lines.append(f"|---|---|")
lines.append(f"| Total test utterances | {total:,} |")
lines.append(f"| Unique speakers | {unique_speakers} |")
lines.append(f"| Minimum utterances/speaker | {min_count} |")
lines.append(f"| Maximum utterances/speaker | {max_count:,} |")
lines.append(f"| Median utterances/speaker | {median_count} |")
lines.append(f"| Mean utterances/speaker | {total // unique_speakers} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Full Speaker Distribution")
lines.append("")
lines.append("Sorted by utterance count descending.")
lines.append("")
lines.append("| Rank | Speaker ID | Utterances | % of test split | Category |")
lines.append("|---|---|---|---|---|")

for rank, (spk, cnt) in enumerate(speaker_table, 1):
    pct = cnt / total * 100
    if cnt >= 200:
        cat = "dominant (audiobook)"
    elif cnt >= 50:
        cat = "large"
    elif cnt >= 10:
        cat = "medium"
    else:
        cat = "sparse"
    lines.append(f"| {rank} | {spk} | {cnt} | {pct:.1f}% | {cat} |")

lines.append("")
lines.append("---")
lines.append("")
lines.append("## Speakers with Fewer Than 10 Utterances")
lines.append("")
if low_speakers:
    lines.append(f"**{len(low_speakers)} speakers** have fewer than 10 test utterances.")
    lines.append("")
    lines.append("| Speaker ID | Utterances |")
    lines.append("|---|---|")
    for spk, cnt in sorted(low_speakers, key=lambda x: x[1]):
        lines.append(f"| {spk} | {cnt} |")
else:
    lines.append("No speakers have fewer than 10 utterances.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Sampling Feasibility Assessment")
lines.append("")
lines.append(f"**Target:** 300 utterances, ≥10 speakers, no single speaker dominating.")
lines.append("")
lines.append(f"With an uncapped draw, the dominant speaker would contribute:")
lines.append(f"- Speaker {speaker_table[0][0]}: {speaker_table[0][1]} utterances ({speaker_table[0][1]/total*100:.1f}% of test split)")
lines.append("")
lines.append(f"**Capped sampling simulation (cap = {cap} utterances/speaker):**")
lines.append(f"- Total available utterances at cap {cap}: {capped_total}")
lines.append(f"- Speakers with ≥1 utterance: {speakers_contributing}")
lines.append(f"- A 300-utterance sample is feasible with this cap: {'YES' if capped_total >= 300 else 'NO'}")
lines.append("")

# Recommended strategy description
lines.append("## Recommended Sampling Strategy")
lines.append("")
lines.append("**Step 1 — Assign per-speaker quota.**")
lines.append(f"Sort speakers by utterance count ascending. Assign each speaker a quota of")
lines.append(f"min(actual_count, ceil(300 / remaining_speakers_with_quota)) utterances,")
lines.append(f"distributing any remainder to larger speakers. This ensures every speaker")
lines.append(f"with ≥1 utterance is represented while capping the dominant speaker's share.")
lines.append("")
lines.append("**Step 2 — Deterministic row selection.**")
lines.append("Within each speaker's pool, select utterances at evenly-spaced indices")
lines.append("(not random) using `sorted_indices[::step]` where step = len(pool) // quota.")
lines.append("This makes the sample reproducible without a random seed.")
lines.append("")
lines.append("**Step 3 — Verify speaker count.**")
lines.append("After sampling, confirm ≥10 distinct speaker IDs are present.")
lines.append("If any speaker contributes 0 utterances (quota rounds to 0), redistribute")
lines.append("that speaker's slot to the next-largest speaker.")
lines.append("")
lines.append("**Step 4 — Record the sample manifest.**")
lines.append("Save the selected `id` values as a flat list in a manifest file.")
lines.append("The manifest pins the exact 300 utterances before any API call is made.")
lines.append("SHA-256 of the manifest file is recorded as part of benchmark metadata.")
lines.append("")

# Print summary to stdout for user
print("\n=== SUMMARY ===")
print(f"Total test utterances: {total}")
print(f"Unique speakers:       {unique_speakers}")
print(f"Min utterances/spkr:   {min_count}")
print(f"Max utterances/spkr:   {max_count}")
print(f"Median utterances/spkr:{median_count}")
print(f"\nTop 5 speakers:")
for spk, cnt in speaker_table[:5]:
    print(f"  {spk}: {cnt} ({cnt/total*100:.1f}%)")
print(f"\nSpeakers with <10 utterances: {len(low_speakers)}")
print(f"Capped pool (cap=50): {capped_total} utterances available")
print(f"300-utterance sample feasible: {'YES' if capped_total >= 300 and unique_speakers >= 10 else 'NO'}")

# Write markdown
out_path = os.path.join(os.path.dirname(__file__), "uzbek_speaker_distribution.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"\nSaved: {out_path}")
