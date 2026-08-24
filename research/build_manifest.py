"""
STEP 4B — Build the USC Uzbek 300-utterance benchmark manifest.

Sampling rule: flat cap of 12 utterances per speaker.
  - Speakers with >=12 utterances: take exactly 12, evenly spaced by index.
  - Speakers with <12 utterances: take all utterances.
  - Total = exactly 300 across all 38 speakers.

Selection is deterministic: no random seed. Within each speaker's pool
(in the order rows appear in the dataset), items are chosen at positions
[i * len(pool) // quota for i in range(quota)].

No audio is downloaded. No STT calls are made.
"""

import os
import csv
import hashlib
from collections import defaultdict

os.environ["HF_DATASETS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from datasets import load_dataset

# ── 1. Load test split metadata (id + sentence only) ──────────────────────
print("Loading USC test split metadata...", flush=True)
ds = load_dataset(
    "murodbek/uzbek-speech-corpus",
    split="test",
    streaming=True,
)
ds = ds.select_columns(["id", "sentence"])

rows = []
for i, row in enumerate(ds):
    rows.append({"id": row["id"], "sentence": row["sentence"]})
    if (i + 1) % 500 == 0:
        print(f"  Loaded {i+1} rows...", flush=True)

print(f"Loaded {len(rows)} rows total.", flush=True)

# ── 2. Group by speaker ───────────────────────────────────────────────────
speaker_pools = defaultdict(list)
for row in rows:
    spk = row["id"].split("_")[0]
    speaker_pools[spk].append(row)

# Verify counts match STEP 4A findings
assert len(rows) == 3837, f"Expected 3837, got {len(rows)}"
assert len(speaker_pools) == 38, f"Expected 38 speakers, got {len(speaker_pools)}"

# ── 3. Determine per-speaker quota with flat cap of 12 ───────────────────
CAP = 12

# Verify the cap produces exactly 300
total_check = sum(min(len(pool), CAP) for pool in speaker_pools.values())
assert total_check == 300, f"Cap={CAP} gives {total_check} utterances, not 300"

print(f"Flat cap of {CAP} utterances/speaker → exactly {total_check} utterances.", flush=True)

# ── 4. Deterministic selection ────────────────────────────────────────────
selected = []
for spk, pool in sorted(speaker_pools.items()):
    quota = min(len(pool), CAP)
    n = len(pool)
    if quota == n:
        chosen = pool  # take all
    else:
        # Evenly-spaced indices: [i * n // quota for i in range(quota)]
        indices = [i * n // quota for i in range(quota)]
        chosen = [pool[idx] for idx in indices]
    for item in chosen:
        selected.append({
            "utterance_id": item["id"],
            "speaker_id": item["id"].split("_")[0],
            "transcript": item["sentence"],
            "split": "test",
            "source_type": "UNKNOWN",
        })

# ── 5. Verification ───────────────────────────────────────────────────────
assert len(selected) == 300, f"Expected 300 items, got {len(selected)}"

utt_ids = [r["utterance_id"] for r in selected]
assert len(set(utt_ids)) == 300, "Duplicate utterance IDs detected!"

speaker_ids = [r["speaker_id"] for r in selected]
from collections import Counter
spk_counts = Counter(speaker_ids)
assert len(spk_counts) >= 10, f"Only {len(spk_counts)} unique speakers"

# Verify all IDs are from the original test split rows
test_ids = {r["id"] for r in rows}
for uid in utt_ids:
    assert uid in test_ids, f"Manifest ID not found in test split: {uid}"

print(f"All verifications passed.", flush=True)

# ── 6. Write CSV manifest ─────────────────────────────────────────────────
out_dir = os.path.dirname(__file__)
csv_path = os.path.join(out_dir, "uzbek_benchmark_manifest.csv")

with open(csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["utterance_id", "speaker_id", "transcript", "split", "source_type"])
    writer.writeheader()
    writer.writerows(selected)

print(f"Manifest written: {csv_path}", flush=True)

# SHA-256 of manifest
with open(csv_path, "rb") as f:
    manifest_sha256 = hashlib.sha256(f.read()).hexdigest()
print(f"Manifest SHA-256: {manifest_sha256}", flush=True)

# ── 7. Compute statistics ─────────────────────────────────────────────────
spk_table = sorted(spk_counts.items(), key=lambda x: -x[1])
spk_values = sorted(spk_counts.values())
min_spk = spk_values[0]
max_spk = spk_values[-1]
median_spk = spk_values[len(spk_values) // 2]

# ── 8. Write statistics markdown ─────────────────────────────────────────
md_path = os.path.join(out_dir, "uzbek_manifest_statistics.md")

lines = []
lines.append("# Uzbek Benchmark Manifest — Selection Rationale and Statistics")
lines.append("")
lines.append("**Date:** 2026-08-23")
lines.append("**Manifest file:** `research/uzbek_benchmark_manifest.csv`")
lines.append(f"**Manifest SHA-256:** `{manifest_sha256}`")
lines.append("**Status:** Manifest only. No audio downloaded. No STT calls made.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Selection Rationale")
lines.append("")
lines.append("### Source")
lines.append("")
lines.append("Dataset: `murodbek/uzbek-speech-corpus`, split=`test`")
lines.append("Corpus: ISSAI Uzbek Speech Corpus, arXiv:2107.14419, CC BY 4.0")
lines.append("Test split: 3,837 utterances, 38 speakers")
lines.append("")
lines.append("### Problem")
lines.append("")
lines.append("The raw test split has extreme speaker imbalance due to two data sources")
lines.append("(audiobook narrators + crowdsourced volunteers):")
lines.append("")
lines.append("- Top 3 speakers hold 74.2% of all test utterances.")
lines.append("- The single dominant speaker has 1,467 utterances (38.2%).")
lines.append("- Without a cap, a naive 300-utterance sample would be dominated by")
lines.append("  2–3 audiobook narrators and contain no representation from the other 35 speakers.")
lines.append("")
lines.append("### Solution: Flat per-speaker cap of 12")
lines.append("")
lines.append("A flat cap of **12 utterances per speaker** was chosen because:")
lines.append("")
lines.append("1. It produces **exactly 300 utterances** with no rounding or adjustment:")
lines.append("   - 18 speakers have ≥12 utterances → each contributes exactly 12 (216 total).")
lines.append("   - 20 speakers have <12 utterances → each contributes their full count (84 total).")
lines.append("   - 216 + 84 = 300.")
lines.append("")
lines.append("2. It represents **all 38 speakers** (every speaker contributes at least 1 utterance).")
lines.append("")
lines.append("3. The dominant speaker's share drops from **38.2% → 4.0%** (12/300).")
lines.append("   No single speaker contributes more than 4.0%.")
lines.append("")
lines.append("4. The rule is simple and transparent: no adaptive formula, no random seed.")
lines.append("")
lines.append("### Deterministic selection within each speaker's pool")
lines.append("")
lines.append("For speakers contributing their full pool (quota = actual count): all rows taken.")
lines.append("")
lines.append("For speakers capped at 12 (quota < actual count): 12 rows are selected at")
lines.append("evenly-spaced positions in the speaker's row order:")
lines.append("")
lines.append("```")
lines.append("indices = [i * len(pool) // 12 for i in range(12)]")
lines.append("```")
lines.append("")
lines.append("This spreads the selection across the speaker's full contribution range")
lines.append("(avoiding clustering at the start) and is fully reproducible from the manifest ID list alone.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Verification Results")
lines.append("")
lines.append(f"| Check | Result |")
lines.append(f"|---|---|")
lines.append(f"| Total utterances | **{len(selected)}** (target: 300) |")
lines.append(f"| Unique speakers | **{len(spk_counts)}** (target: ≥10) |")
lines.append(f"| Duplicate utterance IDs | **0** |")
lines.append(f"| All IDs in USC test split | **YES** |")
lines.append(f"| Minimum utterances/speaker | **{min_spk}** |")
lines.append(f"| Maximum utterances/speaker | **{max_spk}** |")
lines.append(f"| Median utterances/speaker | **{median_spk}** |")
lines.append(f"| Manifest SHA-256 | `{manifest_sha256}` |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Speaker Distribution in Manifest")
lines.append("")
lines.append("| Rank | Speaker ID | Utterances | % of benchmark | Utterances in raw test |")
lines.append("|---|---|---|---|---|")
for rank, (spk, cnt) in enumerate(spk_table, 1):
    raw_count = len(speaker_pools[spk])
    lines.append(f"| {rank} | {spk} | {cnt} | {cnt/300*100:.1f}% | {raw_count} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Source Type")
lines.append("")
lines.append("All utterances are labelled `source_type = UNKNOWN`.")
lines.append("")
lines.append("The paper describes two collection methods: (a) crowdsourcing via Telegram bot,")
lines.append("and (b) audiobooks (20 narrators, 30-min excerpts each). However, the released")
lines.append("dataset does not include a source-type field. Speaker IDs are Telegram user IDs")
lines.append("(numeric) for both sources. The audiobook speakers likely correspond to the")
lines.append("high-utterance-count speakers in the distribution, but this mapping is not")
lines.append("documented in the dataset card, paper, or GitHub repo. Assigning source_type")
lines.append("from utterance count alone would be speculation; UNKNOWN is the correct label.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Contamination Risk")
lines.append("")
lines.append("All selected utterances: **CONTAMINATION-RISK: MEDIUM**")
lines.append("")
lines.append("The USC was published in 2021 and has been publicly available since.")
lines.append("Commercial model training data may include USC audio. This label applies")
lines.append("to every row in the manifest and must appear in all published result tables.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("*No audio has been downloaded. No STT calls have been made.*")
lines.append("*This manifest pins the exact 300 utterances for the Uzbek STT benchmark.*")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Statistics written: {md_path}", flush=True)

# ── 9. Console summary ────────────────────────────────────────────────────
print("\n=== MANIFEST SUMMARY ===")
print(f"Total utterances:        {len(selected)}")
print(f"Unique speakers:         {len(spk_counts)}")
print(f"Min utterances/speaker:  {min_spk}")
print(f"Max utterances/speaker:  {max_spk}")
print(f"Median utterances/spkr:  {median_spk}")
print(f"Dominant speaker share:  {max_spk/300*100:.1f}%")
print(f"Manifest SHA-256:        {manifest_sha256}")
print(f"\nTop 5 speakers in manifest:")
for spk, cnt in spk_table[:5]:
    raw = len(speaker_pools[spk])
    print(f"  {spk}: {cnt}/300 ({cnt/300*100:.1f}%)  [raw test: {raw}]")
print(f"\nAll 38 speakers represented: {'YES' if len(spk_counts) == 38 else 'NO'}")
