"""
Post-download: list the KSC archive contents without extracting anything.
Prints all filenames grouped by extension/folder to understand structure.
"""

import tarfile
import os
from collections import defaultdict

ARCHIVE = "C:/Users/erkin/central-asian-voice-benchmark/data/ksc/ISSAI_KSC_335RS_v1.1_flac.tar.gz"

ext_counts = defaultdict(int)
top_dirs = defaultdict(int)
non_audio_files = []
all_names_sample = []
total = 0

print(f"Listing archive contents: {ARCHIVE}")
print("(This reads the archive sequentially — may take a few minutes)")
print()

with tarfile.open(ARCHIVE, "r:gz") as tar:
    for member in tar:
        total += 1
        name = member.name
        _, ext = os.path.splitext(name.lower())
        ext_counts[ext] += 1

        # Top-level directory
        parts = name.split("/")
        top_dirs[parts[0]] += 1

        # Collect non-audio filenames
        if ext not in (".flac", ".wav", ".mp3"):
            non_audio_files.append(name)

        # Sample first 20 files total
        if total <= 20:
            all_names_sample.append(name)

        if total % 10000 == 0:
            print(f"  Processed {total:,} entries...", flush=True)

print(f"\nTotal entries: {total:,}")
print()

print("=== BY EXTENSION ===")
for ext, cnt in sorted(ext_counts.items(), key=lambda x: -x[1]):
    print(f"  {ext or '(no ext)':15s}  {cnt:,}")

print()
print("=== TOP-LEVEL DIRECTORIES ===")
for d, cnt in sorted(top_dirs.items(), key=lambda x: -x[1]):
    print(f"  {d:40s}  {cnt:,} entries")

print()
print("=== FIRST 20 ENTRIES ===")
for name in all_names_sample:
    print(f"  {name}")

print()
print("=== ALL NON-AUDIO FILES ===")
for name in non_audio_files:
    print(f"  {name}")
