"""Build the installable extension ZIP using only the Python standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "product" / "chrome-extension"
FILES = (
    "manifest.json", "background.js", "sidepanel.html", "panel.css", "panel.js",
    "core.mjs", "microphone.html", "microphone.js", "README.md",
)


def build(destination):
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest["manifest_version"] != 3:
        raise ValueError("Expected Manifest V3")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for filename in FILES:
            data = (SOURCE / filename).read_bytes()
            entry = zipfile.ZipInfo(f"BirOvoz-Chrome-Local/{filename}", date_time=(2026, 10, 13, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "downloads" / "BirOvoz-Chrome-Local.zip"))
    args = parser.parse_args()
    print(build(args.out))
