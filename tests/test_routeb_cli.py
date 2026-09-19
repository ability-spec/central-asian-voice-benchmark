"""Exercise the real backend -> wrapper -> child CLI without loading GPU models.

The child is a recording stub, not a validation of the external Seed-VC fork.
Both the V1 single-source and V2 batch paths must forward the configured steps.
"""

import json
import os
import subprocess
import sys

import pytest

from product.backend.config import settings
from product.backend.services import voice_clone


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize("steps", [15, 7])
def test_backend_argv_reaches_seedvc_with_configured_steps(tmp_path, monkeypatch, version, steps):
    seed_dir = tmp_path / "seed vc"
    seed_dir.mkdir()
    # Record every child invocation and produce a file for the real wrapper to
    # discover/copy. No claim about actual model inference or audio quality.
    stub = '''import json
from pathlib import Path
import sys

argv = sys.argv[1:]
with Path("argv.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
if "--source-list" in argv:
    items = json.loads(Path(argv[argv.index("--source-list") + 1]).read_text())
else:
    items = [{"source": argv[argv.index("--source") + 1],
              "output": argv[argv.index("--output") + 1]}]
for item in items:
    output = Path(item["output"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "converted.wav").write_bytes(Path(item["source"]).read_bytes())
'''
    (seed_dir / ("inference_v2.py" if version == "v2" else "inference.py")).write_text(stub)
    sentences = tmp_path / "sentences.txt"
    sentences.write_text("1. Salom dunyo\n2. Rahmat\n", encoding="utf-8")
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference stub")
    output = tmp_path / "output"
    source_dir = output / "b_sayro"
    source_dir.mkdir(parents=True)
    for name in ("t01.wav", "t02.wav"):
        (source_dir / name).write_bytes(name.encode())

    for key, value in {
        "sayro_script": str(voice_clone._VENDORED_WRAPPER),
        "sayro_python": sys.executable,
        "seedvc_python": sys.executable,
        "seedvc_dir": str(seed_dir),
        "seedvc_reference_wav": str(reference),
        "seedvc_version": version,
        "route_b_diffusion_steps": steps,
        "route_b_intelligibility": 0.8,
        "route_b_similarity": 0.8,
        "route_b_extra_args": "",
    }.items():
        monkeypatch.setattr(settings, key, value)
    cmd = voice_clone._build_route_b_cmd(sentences, output)
    # Supply existing Sayro outputs so the actual conversion orchestration can
    # run without torch or a GPU. Everything else is the backend's real argv.
    cmd[cmd.index("--stage") + 1] = "convert"
    result = subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True,
                            encoding="utf-8", timeout=20,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in (seed_dir / "argv.jsonl").read_text().splitlines()]
    assert len(calls) == (1 if version == "v2" else 2)
    for argv in calls:
        assert argv[argv.index("--diffusion-steps") + 1] == str(steps)
        assert argv[argv.index("--length-adjust") + 1] == "1.0"
        if version == "v2":
            assert argv[argv.index("--intelligibility-cfg-rate") + 1] == "0.8"
            assert argv[argv.index("--similarity-cfg-rate") + 1] == "0.8"
            assert "--source-list" in argv
            assert "--fp16" not in argv
    for name in ("t01.wav", "t02.wav"):
        assert (output / "b_sayro_vc" / name).read_bytes() == name.encode()
