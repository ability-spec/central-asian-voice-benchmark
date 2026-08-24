"""
STEP 5B — Extract KSC metadata CSVs and all transcripts from the archive.

Archive structure (confirmed by inspect_ksc_archive.py):
  ISSAI_KSC_335RS_v1.1_flac/
    Audios_flac/      — 153,853 FLAC files (all splits, flat)
    Transcriptions/   — 153,853 TXT files (all splits, flat)
    Meta/
      train.csv       — utterance IDs + speaker info for train split
      dev.csv         — utterance IDs + speaker info for dev split
      test.csv        — utterance IDs + speaker info for test split  ← KEY FILE

Extraction targets (no audio):
  - Meta/*.csv   (3 files, tiny — split assignments + speaker metadata)
  - Transcriptions/*.txt  (153,853 files, ~50 bytes each ≈ ~8 MB total)

Audio is NOT extracted here. Test audio (300 files) will be extracted
separately when the benchmark manifest is finalized.

Usage: python extract_ksc_test.py
Output: data/ksc/extracted/
"""

import os
import tarfile

ARCHIVE = "C:/Users/erkin/central-asian-voice-benchmark/data/ksc/ISSAI_KSC_335RS_v1.1_flac.tar.gz"
OUT_DIR = "C:/Users/erkin/central-asian-voice-benchmark/data/ksc/extracted"

os.makedirs(OUT_DIR, exist_ok=True)

ROOT = "ISSAI_KSC_335RS_v1.1_flac"

def should_extract(name):
    # Meta CSV files (split assignments + speaker metadata)
    if name.startswith(f"{ROOT}/Meta/") and name.endswith(".csv"):
        return True
    # All transcript TXT files
    if name.startswith(f"{ROOT}/Transcriptions/") and name.endswith(".txt"):
        return True
    return False


extracted_csv = []
extracted_txt = 0
skipped = 0
total = 0

print(f"Extracting Meta CSVs and Transcriptions from: {ARCHIVE}")
print(f"Output directory: {OUT_DIR}")
print(f"Targets: Meta/*.csv  +  Transcriptions/*.txt  (no audio)")
print()

with tarfile.open(ARCHIVE, "r:gz") as tar:
    for member in tar:
        total += 1
        if total % 20000 == 0:
            print(f"  Processed {total:,} entries, csv={len(extracted_csv)}, txt={extracted_txt}, skipped={skipped}...", flush=True)

        if member.isdir():
            continue

        if should_extract(member.name):
            tar.extract(member, path=OUT_DIR, filter="data")
            if member.name.endswith(".csv"):
                extracted_csv.append(member.name)
                print(f"  CSV: {member.name}", flush=True)
            else:
                extracted_txt += 1
        else:
            skipped += 1

print()
print(f"=== EXTRACTION COMPLETE ===")
print(f"Total archive entries: {total:,}")
print(f"Meta CSVs extracted:   {len(extracted_csv)}")
print(f"Transcripts extracted: {extracted_txt:,}")
print(f"Skipped (audio):       {skipped:,}")
print()
print("CSV files:")
for name in extracted_csv:
    print(f"  {name}")
print()
print(f"Output: {OUT_DIR}")
