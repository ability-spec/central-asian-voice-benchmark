"""
STEP 5B — Stream ISSAI KSC tar.gz to extract metadata and transcripts only.

Strategy: The archive is a sequential gzip tar. We stream it from OpenSLR,
decompress on the fly, and extract only:
  - Any *.csv or *.json (metadata/speaker info)
  - Any *.txt (transcripts)
  - Any README, ABOUT, LICENSE, or similar docs

We skip all audio files (*.flac, *.wav).

A bandwidth cap (CAP_BYTES) stops the download early if the needed files
are all found. If the cap is reached without finding the metadata file,
we report what was found and how much was downloaded.

Set CAP_BYTES to a reasonable limit. Transcripts and metadata are typically
in the first fraction of a large archive if alphabetically ordered
(metadata/ and test/ folders come before train/ alphabetically).

No audio is saved. No STT calls are made.
"""

import os
import io
import sys
import tarfile
import urllib.request

os.environ["PYTHONIOENCODING"] = "utf-8"

ARCHIVE_URL = "https://openslr.trmal.net/resources/102/ISSAI_KSC_335RS_v1.1_flac.tar.gz"

# Output directory for extracted text/metadata files
OUT_DIR = os.path.join(os.path.dirname(__file__), "ksc_extracted")
os.makedirs(OUT_DIR, exist_ok=True)

# Bandwidth cap: 3 GB. Stop if we haven't found what we need by then.
CAP_BYTES = 3 * 1024 * 1024 * 1024

# File extensions to extract (skip audio)
EXTRACT_EXTS = {".csv", ".txt", ".json", ".tsv", ".md", ".README", ""}
SKIP_EXTS = {".flac", ".wav", ".mp3", ".ogg", ".opus"}

# Track what we find
found_files = []
skipped_audio = 0
bytes_downloaded = 0

print(f"Streaming KSC archive from OpenSLR...")
print(f"Bandwidth cap: {CAP_BYTES / 1024**3:.1f} GB")
print(f"Extracting: text/csv/json files only (skipping audio)")
print()


class CappedStream:
    """Wraps a urllib response to track bytes read and enforce a cap."""

    def __init__(self, response, cap):
        self._response = response
        self._cap = cap
        self._read = 0
        self._capped = False

    def read(self, size=-1):
        if self._capped:
            return b""
        if self._read >= self._cap:
            self._capped = True
            print(f"\n[CAP REACHED] {self._read / 1024**3:.2f} GB downloaded. Stopping stream.")
            return b""
        if size == -1:
            chunk = self._response.read()
        else:
            chunk = self._response.read(size)
        self._read += len(chunk)
        return chunk

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return False

    def tell(self):
        return self._read

    @property
    def bytes_read(self):
        return self._read


try:
    req = urllib.request.urlopen(ARCHIVE_URL, timeout=60)
    stream = CappedStream(req, CAP_BYTES)

    with tarfile.open(mode="r|gz", fileobj=stream) as tar:
        for member in tar:
            bytes_downloaded = stream.bytes_read
            name = member.name
            _, ext = os.path.splitext(name.lower())

            # Skip directories
            if member.isdir():
                continue

            # Skip audio
            if ext in SKIP_EXTS:
                skipped_audio += 1
                # Print progress every 1000 audio files skipped
                if skipped_audio % 1000 == 0:
                    print(
                        f"  [{bytes_downloaded / 1024**2:.0f} MB] "
                        f"Skipped {skipped_audio} audio files, "
                        f"extracted {len(found_files)} text files...",
                        flush=True,
                    )
                continue

            # Check if we should extract this file
            should_extract = (
                ext in EXTRACT_EXTS
                or any(
                    kw in name.lower()
                    for kw in ["readme", "license", "metadata", "speaker", "about", "info"]
                )
            )

            if should_extract and member.isfile():
                # Safe path: flatten to OUT_DIR (no path traversal)
                safe_name = name.replace("/", "__").replace("\\", "__")
                out_path = os.path.join(OUT_DIR, safe_name)
                try:
                    f = tar.extractfile(member)
                    if f is not None:
                        content = f.read()
                        with open(out_path, "wb") as out:
                            out.write(content)
                        found_files.append((name, len(content), out_path))
                        print(
                            f"  EXTRACTED: {name} ({len(content):,} bytes)",
                            flush=True,
                        )
                except Exception as e:
                    print(f"  ERROR extracting {name}: {e}", flush=True)

    bytes_downloaded = stream.bytes_read

except Exception as e:
    print(f"\nStream error: {e}", flush=True)
    bytes_downloaded = 0

print()
print("=== EXTRACTION SUMMARY ===")
print(f"Bytes downloaded:     {bytes_downloaded / 1024**2:.1f} MB ({bytes_downloaded / 1024**3:.2f} GB)")
print(f"Audio files skipped:  {skipped_audio}")
print(f"Text/metadata extracted: {len(found_files)}")
print()
if found_files:
    print("Extracted files:")
    for name, size, path in found_files:
        print(f"  {name}  ({size:,} bytes)  → {path}")
else:
    print("No text/metadata files found within the download cap.")
print()
print(f"Extracted files saved to: {OUT_DIR}")
