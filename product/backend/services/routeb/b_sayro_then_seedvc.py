#!/usr/bin/env python3
"""
ROUTE B — Sayro speaks correct Uzbek (fixed voice), then Seed-VC repaints YOUR timbre
on top. Two stages, never both models in VRAM at once.

Prereqs (see RUNBOOK.md):
  * hf auth login  + Sayro approval (gated repo)
  * uzbek_normalizer.py downloaded from the Sayro repo "Files" tab into THIS folder
    (it is NOT on PyPI — verified. Script falls back to whitespace cleanup without it)
  * Seed-VC cloned:  git clone https://github.com/Plachtaa/seed-vc  (separate venv!)

Usage (from the voice-lab folder):
  python b_sayro_then_seedvc.py --stage all --clips clips --seedvc-dir ..\\seed-vc
  python b_sayro_then_seedvc.py --stage sayro                          # TTS only
  python b_sayro_then_seedvc.py --stage convert --seedvc-dir ..\\seed-vc  # VC only
  python b_sayro_then_seedvc.py --dry-run                              # plan + exact commands

Output: out/b_sayro/tNN.wav (Sayro voice) and out/b_sayro_vc/tNN.wav (your timbre).
Tuning knobs that matter:
  --intelligibility 0.8   higher = protects Uzbek pronunciation more (V2)
  --similarity      0.8   higher = sounds more like you (V2)
  --auto-f0 False   set True if the output has YOUR timbre but wrong pitch (V1)
"""
import argparse
import gc
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (LAB, filter_kwargs, is_cuda_oom, load_qwen_model,
                    parse_numbered, print_oom_advice, unpack_generation, write_wav)

SAYRO_ID = "uzlm/sayro-tts-1.7B"
SEEDVC_URL = "https://github.com/Plachtaa/seed-vc"


# ---------------------------------------------------------------- stage 1: Sayro TTS
def stage_sayro(args, sentences):
    import torch
    try:
        from uzbek_normalizer import clean_uzbek_text
        print("[B] uzbek_normalizer: found")
    except ImportError:
        clean_uzbek_text = None
        print("[B] WARN uzbek_normalizer NOT found — it is NOT on PyPI (verified).")
        print("        Get uzbek_normalizer.py from the Sayro repo 'Files' tab (you have access)")
        print("        and put it next to this script. Using whitespace-only cleanup for now.")

    def norm(t):
        return clean_uzbek_text(t) if clean_uzbek_text else " ".join(t.split())

    print(f"[B] loading {SAYRO_ID} (gated — needs 'hf auth login')…")
    t0 = time.time()
    try:
        model = load_qwen_model(SAYRO_ID, args.device, args.dtype, args.attn)
    except Exception as e:
        msg = str(e)
        if any(k in msg.lower() for k in ("401", "403", "gated", "access denied", "not authorized")):
            print("[B] gated-repo error -> run 'hf auth login' in this venv, "
                  "and confirm your Sayro approval e-mail")
        if is_cuda_oom(e):
            print_oom_advice()
        raise
    print(f"[B] loaded in {time.time() - t0:.1f}s")

    out_dir = Path(args.out) / "b_sayro"
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = [norm(t) for _, t in sentences]
    manifest = dict(model=SAYRO_ID, items=[])

    gen = getattr(model, "generate_custom_voice", None)
    if gen is None:
        raise SystemExit("[B] this model has no generate_custom_voice() — wrong checkpoint?")
    attempts = [
        dict(text=texts, speaker=["sayro"] * len(texts), instruct=["Neutral"] * len(texts)),
        dict(text=texts, speaker="sayro", instruct="Neutral"),
    ]
    wavs = sr = None
    last_err = None
    for kw in attempts:
        try:
            wavs, sr = unpack_generation(gen(**filter_kwargs(gen, kw)))
            break
        except TypeError as e:
            last_err = e
            continue
        except RuntimeError as e:
            if is_cuda_oom(e):
                print_oom_advice()
            raise
    if wavs is None:
        raise SystemExit(f"[B] generate_custom_voice failed: {last_err}. "
                         "Paste the traceback in the chat and STOP (timebox rule).")
    if len(wavs) != len(sentences):
        raise SystemExit(f"[B] expected {len(sentences)} wavs, got {len(wavs)}")

    for (num, raw), text, wav in zip(sentences, texts, wavs):
        path = out_dir / f"t{num:02d}.wav"
        write_wav(path, wav, sr)
        manifest["items"].append(dict(id=f"t{num:02d}", text=text, file=path.name))
        print(f"[B] t{num:02d} -> {path}")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    try:
        print(f"[B] peak GPU memory: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
    except Exception:
        pass
    del model
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    print("[B] Sayro stage done — VRAM released")


# ---------------------------------------------------------------- stage 2: Seed-VC
def build_seedvc_target(clips_dir, target_path, max_s=30.0):
    import array
    import wave

    clips = sorted(Path(clips_dir).glob("[0-9][0-9].wav"))
    if not clips:
        raise SystemExit(f"[B] no numbered clips in {clips_dir} — run prep_reference.py first")
    buf = array.array("h")
    sr = 16000
    for c in clips:
        with wave.open(str(c), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise SystemExit(f"[B] {c.name}: not 16-bit mono — re-run prep_reference.py")
            sr = w.getframerate()
            data = w.readframes(w.getnframes())
        chunk = array.array("h", data)
        if len(buf) + len(chunk) > max_s * sr:
            chunk = chunk[: max(0, int(max_s * sr) - len(buf))]
            buf.extend(chunk)
            break
        buf.extend(chunk)
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())
    print(f"[B] Seed-VC target: {target_path} ({len(buf) / sr:.1f}s from {len(clips)} clips)")
    return target_path


def find_seedvc_script(seedvc_dir, version):
    p = Path(seedvc_dir)
    v2, v1 = p / "inference_v2.py", p / "inference.py"
    if version == "auto":
        version = "v2" if v2.exists() else "v1"
    script = v2 if version == "v2" else v1
    if not script.exists():
        raise SystemExit(f"[B] {script} not found. Clone Seed-VC first:\n"
                         f"      git clone {SEEDVC_URL}")
    return version, script


def seedvc_cmd(script, version, src, target, outdir, args, python=None):
    cmd = [python or sys.executable, str(script), "--source", str(src), "--target", str(target),
           "--output", str(outdir), "--diffusion-steps", "25", "--length-adjust", "1.0"]
    if version == "v2":
        cmd += ["--intelligibility-cfg-rate", str(args.intelligibility),
                "--similarity-cfg-rate", str(args.similarity),
                "--convert-style", "false",
                "--top-p", "0.9", "--temperature", "1.0"]
    else:
        cmd += ["--inference-cfg-rate", str(args.inference_cfg),
                "--f0-condition", "False",
                "--auto-f0-adjust", str(args.auto_f0),
                "--semi-tone-shift", "0"]
        if args.fp16:
            cmd += ["--fp16", "True"]
    return cmd


def seedvc_batch_cmd_v2(script, target, source_list_json, args, python=None):
    """Build argv for the persistent-process V2 batch mode. Same quality
    parameters as the single-source V2 command (25 steps, 0.8/0.8,
    length-adjust 1.0, no style conversion); replaces --source/--output
    with --source-list for multi-source sequential conversion in one
    Python process."""
    cmd = [python or sys.executable, str(script),
           "--source-list", str(source_list_json),
           "--target", str(target),
           "--diffusion-steps", "25", "--length-adjust", "1.0",
           "--intelligibility-cfg-rate", str(args.intelligibility),
           "--similarity-cfg-rate", str(args.similarity),
           "--convert-style", "false",
           "--top-p", "0.9", "--temperature", "1.0"]
    return cmd


def _run_seedvc_once(cmd, cwd, version, fp16_retry=None):
    """Run one Seed-VC subprocess, handling the ModuleNotFoundError
    wrong-venv message and the V1 --fp16 retry uniformly.
    Returns the CompletedProcess; raises SystemExit on failure."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0 and "ModuleNotFoundError" in (r.stdout + r.stderr):
        print(r.stderr[-800:])
        raise SystemExit(
            "[B][vc] Seed-VC ran with the WRONG python. Seed-VC needs its own venv.\n"
            "      Re-run convert with:  --seedvc-python <path-to-.venv-vc>\\Scripts\\python.exe")
    if r.returncode != 0 and version == "v1" and "--fp16" in cmd and callable(fp16_retry):
        print("[B][vc] failed with --fp16, retrying without…")
        r = subprocess.run(fp16_retry(), capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        print(r.stdout[-1500:])
        print(r.stderr[-1500:])
        raise SystemExit("[B][vc] Seed-VC failed — see output above. If it is an unknown-flag "
                         "error, the repo changed: paste the message in the chat and STOP.")
    return r


def _collect_and_copy_vc_output(tmp_dir, dest_wav):
    """Find the newest wav in tmp_dir, copy it to dest_wav, remove tmp_dir.
    Raises SystemExit if no wav was written. Mirrors the original loop."""
    outs = sorted(tmp_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not outs:
        raise SystemExit(f"[B][vc] Seed-VC wrote no wav into {tmp_dir}")
    shutil.copyfile(outs[0], dest_wav)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def stage_convert(args):
    version, script = find_seedvc_script(args.seedvc_dir, args.seedvc_version)
    # Seed-VC opens "configs/v2/vc_wrapper.yaml" as a CWD-relative path (hardcoded
    # in inference_v2.py), so the subprocess MUST run with cwd = repo root — and
    # every path we pass it must be absolute to survive that CWD change.
    cwd = Path(args.seedvc_dir).resolve()
    py = str(Path(args.seedvc_python or sys.executable).resolve())
    if Path(py) != Path(sys.executable).resolve():
        print(f"[B] Seed-VC python: {py}")
    script = Path(script).resolve()
    print(f"[B] Seed-VC: {version} via {script}")
    print(f"[B] Seed-VC subprocess cwd: {cwd}")
    target = Path(args.target).resolve() if args.target else Path(build_seedvc_target(
        args.clips, Path(args.out).parent / "refs" / "seedvc_target.wav")).resolve()
    if not Path(target).exists():
        raise SystemExit(f"[B] target ref not found: {target}")

    src_dir = Path(args.out) / "b_sayro"
    sources = sorted(src_dir.glob("t*.wav"))
    if not sources:
        raise SystemExit(f"[B] no Sayro outputs in {src_dir} — run --stage sayro first")
    vc_dir = Path(args.out) / "b_sayro_vc"
    vc_dir.mkdir(parents=True, exist_ok=True)

    if version == "v2":
        # V2 PERSISTENT WORKER: launch inference_v2.py ONCE with a JSON
        # source-list covering every Sayro wav. inference_v2.py keeps
        # vc_wrapper_v2 as a module-global, so models load exactly once
        # and all sources are converted sequentially in that one process.
        items = []
        tmp_dirs = {}
        for src in sources:
            tmp = vc_dir / (src.stem + "_in")
            tmp.mkdir(exist_ok=True)
            tmp_dirs[src.name] = tmp
            items.append({
                "source": str(src.resolve()),
                "output": str(tmp.resolve()),
                "name": src.stem,
            })
        source_list_path = vc_dir / "_source_list.json"
        source_list_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        cmd = seedvc_batch_cmd_v2(script, target.resolve(), source_list_path.resolve(),
                                  args, python=py)
        n = len(sources)
        print(f"[B][vc] launching ONE persistent Seed-VC v2 process for {n} source(s) ...")
        _run_seedvc_once(cmd, cwd, version)
        for src in sources:
            tmp = tmp_dirs[src.name]
            _collect_and_copy_vc_output(tmp, vc_dir / src.name)
            print(f"[B][vc] {src.name} -> b_sayro_vc/{src.name}")
        try:
            source_list_path.unlink()
        except OSError:
            pass
    else:
        # V1: one subprocess per source (V1 script has no module-global
        # model cache and no batch CLI; that's out of scope here).
        for src in sources:
            tmp = vc_dir / (src.stem + "_in")
            tmp.mkdir(exist_ok=True)
            cmd = seedvc_cmd(script, version, src.resolve(), Path(target).resolve(),
                             tmp.resolve(), args, python=py)
            print(f"[B][vc] {src.name} …")

            def _retry_no_fp16(cmd=cmd, script=script, src=src, target_p=target,
                               tmp=tmp, args=args, py=py):
                c = seedvc_cmd(script, version, src.resolve(), Path(target_p).resolve(),
                               tmp.resolve(), args, python=py)
                if "--fp16" in c:
                    idx = c.index("--fp16")
                    del c[idx:idx + 2]
                return c

            _run_seedvc_once(cmd, cwd, version, fp16_retry=_retry_no_fp16)
            _collect_and_copy_vc_output(tmp, vc_dir / src.name)
            print(f"[B][vc] {src.name} -> b_sayro_vc/{src.name}")
    print(f"[B] convert stage done -> {vc_dir}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["sayro", "convert", "all"], default="all")
    ap.add_argument("--clips", default=str(LAB / "clips"))
    ap.add_argument("--out", default=str(LAB / "out"))
    ap.add_argument("--sentences", default=str(LAB / "test_sentences.txt"))
    ap.add_argument("--only", default=None, help="comma-separated ids, e.g. 01,02,03")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--attn", default="sdpa", choices=["sdpa", "flash_attention_2", "eager"])
    ap.add_argument("--seedvc-dir", default=str(LAB.parent / "seed-vc"))
    ap.add_argument("--seedvc-python", default=None,
                    help="python of the Seed-VC venv, e.g. .venv-vc\\Scripts\\python.exe "
                         "(needed for --stage all when Seed-VC has its own venv)")
    ap.add_argument("--seedvc-version", choices=["auto", "v1", "v2"], default="auto",
                    help="v1 = lighter (<6 GB), v2 = better, needs ~8 GB")
    ap.add_argument("--target", default=None, help="override Seed-VC target audio")
    ap.add_argument("--intelligibility", default="0.8", help="V2: higher protects Uzbek phonemes")
    ap.add_argument("--similarity", default="0.8", help="V2: higher sounds more like you")
    ap.add_argument("--inference-cfg", default="0.8", help="V1 overall conversion strength")
    ap.add_argument("--auto-f0", default="False", help="V1: True if pitch sounds wrong")
    ap.add_argument("--fp16", default=True, help="V1: --fp16 True")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sentences = parse_numbered(args.sentences)
    if args.only:
        want = {int(x) for x in args.only.split(",") if x.strip().isdigit()}
        sentences = [s for s in sentences if s[0] in want]

    if args.dry_run:
        print(f"[B] DRY RUN — stage={args.stage}, {len(sentences)} sentence(s)")
        print(f"[B] sayro   : {SAYRO_ID} on {args.device} ({args.dtype}, {args.attn})")
        print(f"[B] normalizer: uzbek_normalizer.py "
              f"({'FOUND' if (LAB / 'uzbek_normalizer.py').exists() else 'MISSING — copy from gated Sayro repo'})")
        print(f"[B] seed-vc : {args.seedvc_dir} (version={args.seedvc_version})")
        vp = Path(args.seedvc_dir)
        print(f"[B]   inference_v2.py {'FOUND' if (vp / 'inference_v2.py').exists() else 'missing'}"
              f" | inference.py {'FOUND' if (vp / 'inference.py').exists() else 'missing'}")
        version, script = (None, None)
        try:
            version, script = find_seedvc_script(args.seedvc_dir, args.seedvc_version)
            demo = seedvc_cmd(script, version, "<sayro_out>/t01.wav", "refs/seedvc_target.wav",
                              "<tmp>", args,
                              python=str(Path(args.seedvc_python).resolve())
                              if args.seedvc_python else None)
            print("[B] convert command per clip would be:\n      " + " ".join(demo))
            print(f"[B]   subprocess cwd: {Path(args.seedvc_dir).resolve()} "
                  f"(Seed-VC resolves configs/ relative to it)")
            if not args.seedvc_python:
                print("[B]   NOTE: add --seedvc-python <seed-vc venv python> for --stage all")
        except SystemExit as e:
            print(f"[B]   (cannot preview command: {e})")
        return 0

    if args.stage in ("sayro", "all"):
        stage_sayro(args, sentences)
    if args.stage in ("convert", "all"):
        stage_convert(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
