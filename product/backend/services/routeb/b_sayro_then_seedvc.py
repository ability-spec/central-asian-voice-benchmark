#!/usr/bin/env python3
"""
ROUTE B — Sayro speaks correct Uzbek (fixed voice), then Seed-VC repaints YOUR
timbre on top. Two stages. In --daemon mode both models stay resident for
low-latency per-utterance synthesis (powers BirOvoz's hot path).

Usage:
  python b_sayro_then_seedvc.py --stage all ...       # one-shot CLI (unchanged)
  python b_sayro_then_seedvc.py --daemon [args...]   # persistent JSONL worker

Daemon protocol:
  * Stdin:  one JSON object per line: {id, text, target, work_dir}
  * Stdout: one JSON object per line: {id, ok, wav_b64, path, elapsed_s[, error, traceback]}
  * stderr: free-form [B] log lines (flushed).
  * All pipes use binary writes with explicit newline + flush to avoid
    Windows C-runtime buffering deadlocks.
"""
import argparse
import atexit
import base64
import gc
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (LAB, filter_kwargs, is_cuda_oom, load_qwen_model,
                    parse_numbered, print_oom_advice, unpack_generation, write_wav)

SAYRO_ID = "uzlm/sayro-tts-1.7B"
SEEDVC_URL = "https://github.com/Plachtaa/seed-vc"


def _norm_factory():
    try:
        from uzbek_normalizer import clean_uzbek_text
        print("[B] uzbek_normalizer: found", flush=True)
        return clean_uzbek_text
    except ImportError:
        print("[B] WARN uzbek_normalizer NOT found — NOT on PyPI.", flush=True)
        print("        Get uzbek_normalizer.py from the Sayro repo 'Files' tab "
              "and put it next to this script.", flush=True)
        return None


_clean_uzbek = [None]

# In daemon mode stdout is a strict JSONL protocol stream. Keep the original
# binary stdout handle for _emit(), then route the text-mode stdout used by
# incidental/imported logging to stderr. The one-shot CLI keeps its existing
# human-readable stdout behavior.
_DAEMON_STDOUT = None


def _norm(t):
    if _clean_uzbek[0] is None:
        _clean_uzbek[0] = _norm_factory()
    fn = _clean_uzbek[0]
    return fn(t) if fn else " ".join(t.split())


def _emit(obj):
    """Emit one JSON result line on the daemon's stdout protocol stream."""
    out = _DAEMON_STDOUT or sys.stdout.buffer
    out.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    out.flush()


def _emit_ready():
    """Emit the one non-JSON stdout control line allowed by the protocol."""
    out = _DAEMON_STDOUT or sys.stdout.buffer
    out.write(b"[B] routeb daemon ready (Sayro + Seed-VC will load on first job)\n")
    out.flush()


def _kill_proc_tree(proc):
    """Cross-platform process-tree kill. On Windows we MUST use taskkill /T
    to kill the grandchild inference_v2.py, otherwise we leak CUDA
    processes on reload/crash. On POSIX we rely on start_new_session +
    killpg (set by the parent when spawning us)."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            if os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    proc.kill()
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
        # Also wait for an already-exited child so replacement/repeated
        # shutdown reaps it instead of leaving a POSIX zombie.
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------- Sayro

def _clear_sayro_cuda() -> None:
    """Drop released Sayro references and return unused CUDA blocks.

    This is deliberately best-effort: cleanup must never hide the original
    model-load or generation exception, and the wrapper may be running in a
    CPU-only test environment where torch/CUDA is unavailable.
    """
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


class SayroModel:
    def __init__(self, args):
        self.args = args
        self.model = None
        self.sr = None
        self._load_lock = threading.Lock()

    def _reset(self) -> None:
        """Discard valid, invalid, or partially initialized model state."""
        self.model = None
        self.sr = None
        _clear_sayro_cuda()

    def load(self):
        if self.model is not None:
            return
        with self._load_lock:
            if self.model is not None:
                return
            # Print BEFORE importing torch so the parent sees a progress
            # line immediately — torch import + CUDA init on Windows can
            # be silent for 10-45s cold, which makes async readers appear
            # hung if they block on EndOfStream/wait for data.
            print(f"[B] loading {SAYRO_ID} (gated — needs 'hf auth login')…",
                  flush=True)
            t0 = time.time()
            import torch
            candidate = None
            try:
                candidate = load_qwen_model(
                    SAYRO_ID, self.args.device, self.args.dtype, self.args.attn
                )
                if not callable(getattr(candidate, "generate_custom_voice", None)):
                    raise RuntimeError(
                        "this model has no generate_custom_voice() — wrong checkpoint?"
                    )
                self.model = candidate
                candidate = None
            except Exception as e:
                # Ensure a failed/invalid candidate cannot poison the next
                # request, and release any CUDA blocks left by from_pretrained.
                candidate = None
                self._reset()
                msg = str(e)
                if any(k in msg.lower() for k in (
                    "401", "403", "gated", "access denied", "not authorized"
                )):
                    print("[B] gated-repo error -> run 'hf auth login' in "
                          "this venv.", flush=True)
                if is_cuda_oom(e):
                    print_oom_advice()
                raise
            print(f"[B] Sayro loaded in {time.time() - t0:.1f}s", flush=True)

    def synthesize(self, texts):
        self.load()
        gen = getattr(self.model, "generate_custom_voice", None)
        if not callable(gen):
            gen = None
            self._reset()
            raise RuntimeError(
                "this model has no generate_custom_voice() — wrong checkpoint?"
            )
        attempts = [
            dict(text=texts, speaker=["sayro"] * len(texts),
                 instruct=["Neutral"] * len(texts)),
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
                    gen = None
                    self._reset()
                raise
        if wavs is None:
            raise RuntimeError(f"generate_custom_voice failed: {last_err}")
        return wavs, sr


# ---------------------------------------------------------------- Seed-VC persistent child

class SeedVCDaemon:
    """Long-lived inference_v2.py --daemon child. All pipes are binary; we
    use a threaded stdout drain + queue to avoid deadlocks."""

    def __init__(self, script_path: Path, seedvc_dir: Path, seedvc_python: str,
                 target: Path, args):
        self.script_path = Path(script_path).resolve()
        self.seedvc_dir = Path(seedvc_dir).resolve()
        self.seedvc_python = seedvc_python
        self.target = Path(target).resolve()
        self.args = args
        self.proc = None
        self._stderr_t = None
        self._stdout_t = None
        self._responses: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()
        self._dead_error = None

    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            return
        # A previous child may have exited without going through stop().
        # Reap/close its pipes and join its readers before replacing the
        # process reference; reader threads are permanently bound to the
        # Popen/pipe instance they were created for.
        if self.proc is not None:
            self.stop()
        # Pass the REAL target at startup (required by argparse) and to
        # keep Seed-VC's reference feature cache hot across jobs.
        cmd = [
            self.seedvc_python, str(self.script_path),
            "--daemon",
            "--target", str(self.target),
            "--diffusion-steps", str(self.args.diffusion_steps),
            "--length-adjust", str(self.args.length_adjust),
            "--intelligibility-cfg-rate", str(self.args.intelligibility),
            "--similarity-cfg-rate", str(self.args.similarity),
            "--convert-style", "false",
            "--top-p", "0.9",
            "--temperature", "1.0",
            "--repetition-penalty", "1.0",
            "--anonymization-only", "false",
            "--output", str(Path(tempfile.gettempdir()) / "__seedvc_out"),
        ]
        print(f"[B][vc] starting persistent Seed-VC v2 daemon: cwd={self.seedvc_dir}",
              flush=True)
        t0 = time.time()
        popen_kwargs = dict(
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.seedvc_dir),
            bufsize=0,  # unbuffered binary
        )
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
        responses: "queue.Queue[dict]" = queue.Queue()
        self.proc = proc
        self._responses = responses
        self._stderr_t = threading.Thread(
            target=self._drain_stderr,
            args=(proc, proc.stderr),
            daemon=True,
            name="seedvc-stderr",
        )
        self._stderr_t.start()
        self._stdout_t = threading.Thread(
            target=self._drain_stdout,
            args=(proc, proc.stdout, responses),
            daemon=True,
            name="seedvc-stdout",
        )
        self._stdout_t.start()
        # Wait for "[B][vc] daemon ready". Cold load of Seed-VC is not
        # done here — we defer to first job per the protocol — but the
        # Python import + arg parse + first line of output must arrive
        # within a short window to prove the child is healthy.
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            if self.proc.poll() is not None:
                tail = self._recent_stderr_tail()
                raise RuntimeError(
                    f"seed-vc daemon exited early (rc={self.proc.returncode}): {tail}"
                )
            try:
                msg = self._responses.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg.get("type") == "ready":
                ready = True
                break
        if not ready:
            self.stop()
            raise RuntimeError("seed-vc daemon did not become ready within 60s")
        print(f"[B][vc] Seed-VC v2 daemon ready in {time.time() - t0:.1f}s",
              flush=True)

    def _recent_stderr_tail(self, n=5):
        # stderr is logged to our real stderr directly; capture is
        # best-effort.
        return "(see stderr)"

    def _drain_stderr(self, proc, stderr):
        """Drain one specific Seed-VC stderr pipe until that child exits.

        Do not dereference self.proc here: restart can replace it while
        this reader is still unwinding. Binding the Popen/pipe at thread
        creation prevents an old reader from consuming a new child's data.
        """
        try:
            for raw in iter(stderr.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    print(f"[vc:err] {line}", file=sys.stderr, flush=True)
        except (ValueError, OSError):
            pass
        finally:
            try:
                stderr.close()
            except Exception:
                pass

    def _drain_stdout(self, proc, stdout, responses):
        """Drain one specific Seed-VC stdout pipe into one specific queue."""
        try:
            buf = b""
            while True:
                ch = stdout.read(1)
                if not ch:
                    break
                if ch == b"\n":
                    line_bytes = buf
                    buf = b""
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    if "daemon ready" in line:
                        responses.put({"type": "ready"})
                        continue
                    if not line.startswith("{"):
                        # Non-JSON chatter from the Seed-VC child MUST go to
                        # stderr. Routing this to stdout would interleave with
                        # the wrapper's own JSONL response stream (the parent
                        # client parses stdout one-line-per-JSON and would
                        # hit "bad JSON" or silently drop responses under
                        # load — see P1-1 in the production audit).
                        print(f"[vc] {line}", file=sys.stderr, flush=True)
                        continue
                    try:
                        responses.put(
                            {"type": "result", "data": json.loads(line)}
                        )
                    except Exception as e:
                        print(f"[vc] bad json: {e}: {line[:200]}",
                              file=sys.stderr, flush=True)
                else:
                    buf += ch
                    if len(buf) > 10_000_000:  # guard against runaway
                        buf = b""
        except (ValueError, OSError):
            pass
        finally:
            try:
                stdout.close()
            except Exception:
                pass

    def convert(self, source_wav: Path, out_dir: Path, job_id: str) -> str:
        """Convert one source wav; return path to converted WAV on disk."""
        self.start()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        req = {
            "id": job_id,
            "source": str(Path(source_wav).resolve()),
            "target": str(self.target),
            "output": str(out_dir.resolve()),
        }
        data = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            assert self.proc and self.proc.stdin
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            self._dead_error = f"seed-vc daemon broken pipe: {e}"
            self.stop()
            raise RuntimeError(self._dead_error)
        deadline = time.time() + max(600, self.args.diffusion_steps * 30)
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self._dead_error = f"seed-vc daemon died rc={self.proc.returncode}"
                raise RuntimeError(self._dead_error)
            try:
                msg = self._responses.get(timeout=0.5)
            except queue.Empty:
                continue
            if msg.get("type") != "result":
                continue
            d = msg["data"]
            if d.get("id") == job_id:
                if not d.get("ok"):
                    raise RuntimeError(
                        f"seed-vc failed: {d.get('error')}\n{d.get('traceback', '')}"
                    )
                p = d.get("path")
                if p and Path(p).is_file():
                    return p
                raise RuntimeError("seed-vc returned ok but no output file")
        raise RuntimeError("seed-vc job timed out")

    def stop(self):
        """Stop this child and boundedly join its pipe readers.

        The operation is idempotent: callers may stop an already-dead or
        already-cleared child repeatedly without touching a replacement.
        """
        proc = self.proc
        stdout_t = self._stdout_t
        stderr_t = self._stderr_t
        _kill_proc_tree(proc)
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
        deadline = time.monotonic() + 2.0
        for thread in (stdout_t, stderr_t):
            if thread is None or thread is threading.current_thread():
                continue
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():
                print("[vc] reader thread did not terminate during shutdown",
                      file=sys.stderr, flush=True)
        self.proc = None
        self._stdout_t = None
        self._stderr_t = None


# ---------------------------------------------------------------- Setup

def _resolve_target(args) -> Path:
    target = Path(args.target).resolve() if args.target else Path(
        build_seedvc_target(
            args.clips, Path(args.out).parent / "refs" / "seedvc_target.wav"
        )
    ).resolve()
    if not target.exists():
        raise SystemExit(f"[B] target ref not found: {target}")
    return target


def _resolve_seedvc(args):
    version, script = find_seedvc_script(args.seedvc_dir, args.seedvc_version)
    cwd = Path(args.seedvc_dir).resolve()
    py = str(Path(args.seedvc_python or sys.executable).resolve())
    print(f"[B] Seed-VC: {version} via {Path(script).resolve()}", flush=True)
    print(f"[B] Seed-VC cwd: {cwd}", flush=True)
    print(f"[B] Seed-VC python: {py}", flush=True)
    return version, Path(script).resolve(), cwd, py


def build_seedvc_target(clips_dir, target_path, max_s=30.0):
    import array
    import wave
    clips = sorted(Path(clips_dir).glob("[0-9][0-9].wav"))
    if not clips:
        raise SystemExit(
            f"[B] no numbered clips in {clips_dir} — run prep_reference.py first"
        )
    buf = array.array("h")
    sr = 16000
    for c in clips:
        with wave.open(str(c), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise SystemExit(
                    f"[B] {c.name}: not 16-bit mono — re-run prep_reference.py"
                )
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
    print(f"[B] Seed-VC target: {target_path} ({len(buf)/sr:.1f}s from "
          f"{len(clips)} clips)", flush=True)
    return target_path


def find_seedvc_script(seedvc_dir, version):
    p = Path(seedvc_dir)
    v2, v1 = p / "inference_v2.py", p / "inference.py"
    if version == "auto":
        version = "v2" if v2.exists() else "v1"
    script = v2 if version == "v2" else v1
    if not script.exists():
        raise SystemExit(
            f"[B] {script} not found. Clone Seed-VC first:\n"
            f"      git clone {SEEDVC_URL}"
        )
    return version, script


# ---------------------------------------------------------------- Stages

def _sayro_to_wav(sayro: SayroModel, text: str, out_wav: Path) -> None:
    t0 = time.time()
    wavs, sr = sayro.synthesize([_norm(text)])
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    write_wav(out_wav, wavs[0], sr)
    print(f"[B] sayro done: {out_wav} in {time.time() - t0:.2f}s", flush=True)


def run_one_shot(args, sentences):
    if args.stage in ("sayro", "all"):
        stage_sayro_cli(args, sentences)
    if args.stage in ("convert", "all"):
        stage_convert(args)


def stage_sayro_cli(args, sentences):
    import torch
    model = None
    gen = None
    completed = False
    try:
        print(f"[B] loading {SAYRO_ID} (gated — needs 'hf auth login')…", flush=True)
        t0 = time.time()
        try:
            model = load_qwen_model(SAYRO_ID, args.device, args.dtype, args.attn)
        except Exception as e:
            msg = str(e)
            if any(k in msg.lower() for k in (
                "401", "403", "gated", "access denied", "not authorized"
            )):
                print("[B] gated-repo error -> run 'hf auth login' in this venv.",
                      flush=True)
            if is_cuda_oom(e):
                print_oom_advice()
            raise
        print(f"[B] loaded in {time.time() - t0:.1f}s", flush=True)
        out_dir = Path(args.out) / "b_sayro"
        out_dir.mkdir(parents=True, exist_ok=True)
        texts = [_norm(t) for _, t in sentences]
        gen = getattr(model, "generate_custom_voice", None)
        if not callable(gen):
            raise SystemExit(
                "[B] this model has no generate_custom_voice() — wrong checkpoint?"
            )
        attempts = [
            dict(text=texts, speaker=["sayro"] * len(texts),
                 instruct=["Neutral"] * len(texts)),
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
            raise SystemExit(f"[B] generate_custom_voice failed: {last_err}.")
        for (num, _raw), wav in zip(sentences, wavs):
            path = out_dir / f"t{num:02d}.wav"
            write_wav(path, wav, sr)
            print(f"[B] t{num:02d} -> {path}", flush=True)
        try:
            print(f"[B] peak GPU memory: {torch.cuda.max_memory_allocated()/1e9:.2f} GB",
                  flush=True)
        except Exception:
            pass
        completed = True
    finally:
        # The one-shot path must release model state on failure as well as
        # success; otherwise a later stage/request can inherit stale CUDA
        # allocations from a failed load or generation.
        gen = None
        model = None
        _clear_sayro_cuda()
        if completed:
            print("[B] Sayro stage done — VRAM released", flush=True)


def _collect_vc_output(tmp_dir, dest_wav):
    outs = sorted(Path(tmp_dir).glob("*.wav"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not outs:
        raise RuntimeError(f"[B][vc] Seed-VC wrote no wav into {tmp_dir}")
    shutil.copyfile(outs[0], dest_wav)


def stage_convert(args):
    version, script, cwd, py = _resolve_seedvc(args)
    target = _resolve_target(args)
    src_dir = Path(args.out) / "b_sayro"
    sources = sorted(src_dir.glob("t*.wav"))
    if not sources:
        raise SystemExit(
            f"[B] no Sayro outputs in {src_dir} — run --stage sayro first"
        )
    vc_dir = Path(args.out) / "b_sayro_vc"
    vc_dir.mkdir(parents=True, exist_ok=True)
    if version == "v2":
        items, tmp_dirs = [], {}
        for src in sources:
            tmp = vc_dir / (src.stem + "_in")
            tmp.mkdir(exist_ok=True)
            tmp_dirs[src.name] = tmp
            items.append({"source": str(src.resolve()),
                          "output": str(tmp.resolve()),
                          "name": src.stem})
        sl = vc_dir / "_source_list.json"
        sl.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        cmd = [py, str(script), "--source-list", str(sl.resolve()),
               "--target", str(target),
               "--diffusion-steps", str(args.diffusion_steps),
               "--length-adjust", str(args.length_adjust),
               "--intelligibility-cfg-rate", str(args.intelligibility),
               "--similarity-cfg-rate", str(args.similarity),
               "--convert-style", "false", "--top-p", "0.9",
               "--temperature", "1.0"]
        print(f"[B][vc] launching ONE persistent Seed-VC v2 process for "
              f"{len(sources)} source(s)...", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
        if r.returncode != 0:
            print(r.stdout[-1500:])
            print(r.stderr[-1500:])
            raise SystemExit("[B][vc] Seed-VC failed.")
        for src in sources:
            _collect_vc_output(tmp_dirs[src.name], vc_dir / src.name)
            print(f"[B][vc] {src.name} -> b_sayro_vc/{src.name}", flush=True)
        try:
            sl.unlink()
        except OSError:
            pass
    else:
        for src in sources:
            tmp = vc_dir / (src.stem + "_in")
            tmp.mkdir(exist_ok=True)
            cmd = [py, str(script), "--source", str(src.resolve()),
                   "--target", str(target), "--output", str(tmp.resolve()),
                   "--diffusion-steps", "25", "--length-adjust", "1.0",
                   "--inference-cfg-rate", str(args.inference_cfg),
                   "--f0-condition", "False",
                   "--auto-f0-adjust", str(args.auto_f0),
                   "--semi-tone-shift", "0"]
            if args.fp16:
                cmd += ["--fp16", "True"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
            if r.returncode != 0:
                print(r.stdout[-1500:])
                print(r.stderr[-1500:])
                raise SystemExit("[B][vc] Seed-VC V1 failed.")
            _collect_vc_output(tmp, vc_dir / src.name)
            print(f"[B][vc] {src.name} -> b_sayro_vc/{src.name}", flush=True)
    print(f"[B] convert stage done -> {vc_dir}", flush=True)


# ---------------------------------------------------------------- Daemon

def run_daemon(args):
    global _DAEMON_STDOUT
    # Capture stdout's binary pipe before redirecting the text stream. All
    # human-readable wrapper/library logs must go to stderr in daemon mode;
    # only _emit() JSONL responses and the ready handshake may use stdout.
    _DAEMON_STDOUT = getattr(sys.stdout, "buffer", sys.stdout)
    sys.stdout = sys.stderr
    # Explicitly force UTF-8 for the parent -> wrapper stdin pipe. On
    # Windows, a pipe otherwise uses the system ANSI codepage (often
    # cp1252), silently corrupting Uzbek diacritics such as Oʻ and Gʻ.
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", line_buffering=True)
        except Exception:
            pass

    version, script_path, cwd, py = _resolve_seedvc(args)
    if version != "v2":
        raise SystemExit(f"[B] --daemon requires Seed-VC v2 (got {version})")
    target = _resolve_target(args)
    sayro = SayroModel(args)
    # Defer model loads to first job so the daemon reports ready fast and
    # doesn't pin GPU memory until a real request arrives.
    vc = SeedVCDaemon(script_path, cwd, py, target, args)

    def _cleanup(*_a):
        try:
            vc.stop()
        except Exception:
            pass
    atexit.register(_cleanup)
    if os.name != "nt":
        # SIGTERM/SIGINT trigger normal Python cleanup -> atexit fires.
        try:
            signal.signal(signal.SIGTERM, _cleanup)
            signal.signal(signal.SIGINT, _cleanup)
        except Exception:
            pass
    else:
        # Windows Console control handler so Ctrl+C / uvicorn reload
        # triggers _cleanup and kills the Seed-VC grandchild instead of
        # orphaning it with CUDA still held.
        try:
            import ctypes
            _HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong)
            k32 = ctypes.windll.kernel32

            @_HandlerRoutine
            def _win_ctrl(ctrl_type):
                _cleanup()
                return 0  # fall through to default handler
            k32.SetConsoleCtrlHandler(_win_ctrl, True)
        except Exception:
            pass

    # Ready is the one non-JSON control line permitted on stdout; every
    # subsequent human-readable log is routed to stderr by the redirect
    # above. The parent client uses this handshake before sending jobs.
    _emit_ready()

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        t_job = time.time()
        try:
            job = json.loads(line)
        except Exception as e:
            _emit({"ok": False, "error": f"bad json: {e}"})
            continue
        job_id = job.get("id", "")
        text = job.get("text", "")
        job_target = job.get("target")
        work_dir = Path(
            job.get("work_dir") or tempfile.mkdtemp(prefix="routeb_")
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        # If the caller sent a different target, honor it (forces a
        # re-load of Seed-VC's reference cache for that job). Normal
        # BirOvoz hot-path always sends the same reference WAV, so the
        # cached reference inside inference_v2 stays hot.
        if job_target and Path(job_target).resolve() != vc.target:
            # Stop + respawn the Seed-VC child with new target.
            print(f"[B] target changed ({vc.target} -> {job_target}); "
                  f"restarting Seed-VC daemon", flush=True)
            vc.stop()
            vc.target = Path(job_target).resolve()
        try:
            sayro_out = work_dir / "sayro" / "t01.wav"
            _sayro_to_wav(sayro, text, sayro_out)
            vc_out_dir = work_dir / "vc"
            vc_wav = Path(vc.convert(sayro_out, vc_out_dir, job_id))
            data = vc_wav.read_bytes()
            _emit({
                "ok": True, "id": job_id,
                "wav_b64": base64.b64encode(data).decode("ascii"),
                "path": str(vc_wav),
                "elapsed_s": round(time.time() - t_job, 3),
                "timings": {
                    "total_s": round(time.time() - t_job, 3),
                },
            })
        except Exception as e:
            # If VC child died, discard it so next job respawns.
            try:
                if vc.proc is not None and vc.proc.poll() is not None:
                    vc.stop()
            except Exception:
                pass
            _emit({
                "ok": False, "id": job_id,
                "error": str(e), "traceback": traceback.format_exc(),
                "elapsed_s": round(time.time() - t_job, 3),
            })


# ---------------------------------------------------------------- main

def main():
    # multiprocessing safety on Windows / pyinstaller: must be called before
    # any heavy imports that may trigger torch/CUDA worker spawning. Without
    # this, spawned multiprocessing children can re-enter main() and produce
    # "duplicate daemon" processes.
    try:
        import multiprocessing
        multiprocessing.freeze_support()
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--stage", choices=["sayro", "convert", "all"],
                    default="all")
    ap.add_argument("--clips", default=str(LAB / "clips"))
    ap.add_argument("--out", default=str(LAB / "out"))
    ap.add_argument("--sentences", default=str(LAB / "test_sentences.txt"))
    ap.add_argument("--only", default=None, help="comma-separated ids")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--dtype", default="bfloat16",
                    choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--attn", default="sdpa",
                    choices=["sdpa", "flash_attention_2", "eager"])
    ap.add_argument("--seedvc-dir", default=str(LAB.parent / "seed-vc"))
    ap.add_argument("--seedvc-python", default=None)
    ap.add_argument("--seedvc-version",
                    choices=["auto", "v1", "v2"], default="auto")
    ap.add_argument("--target", default=None)
    ap.add_argument("--diffusion-steps", type=int, default=15)
    ap.add_argument("--length-adjust", type=float, default=1.0)
    ap.add_argument("--intelligibility", default="0.8")
    ap.add_argument("--similarity", default="0.8")
    ap.add_argument("--inference-cfg", default="0.8")
    ap.add_argument("--auto-f0", default="False")
    ap.add_argument("--fp16", default=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--daemon", action="store_true",
                    help="Persistent JSONL worker (loads Sayro/Seed-VC once).")
    args = ap.parse_args()

    if args.daemon:
        run_daemon(args)
        return 0

    sentences = parse_numbered(args.sentences)
    if args.only:
        want = {int(x) for x in args.only.split(",") if x.strip().isdigit()}
        sentences = [s for s in sentences if s[0] in want]

    if args.dry_run:
        print(f"[B] DRY RUN — stage={args.stage}, {len(sentences)} sentence(s)")
        print(f"[B] sayro   : {SAYRO_ID} on {args.device} "
              f"({args.dtype}, {args.attn})")
        norm_path = LAB / "uzbek_normalizer.py"
        print(f"[B] normalizer: uzbek_normalizer.py "
              f"({'FOUND' if norm_path.exists() else 'MISSING'})")
        print(f"[B] seed-vc : {args.seedvc_dir} "
              f"(version={args.seedvc_version})")
        vp = Path(args.seedvc_dir)
        print(f"[B]   inference_v2.py "
              f"{'FOUND' if (vp/'inference_v2.py').exists() else 'missing'}"
              f" | inference.py "
              f"{'FOUND' if (vp/'inference.py').exists() else 'missing'}")
        try:
            version, script = find_seedvc_script(
                args.seedvc_dir, args.seedvc_version
            )
            demo = [sys.executable, str(script), "--source", "<src>",
                    "--target", "<tgt>", "--output", "<tmp>",
                    "--diffusion-steps", str(args.diffusion_steps),
                    "--length-adjust", str(args.length_adjust)]
            if version == "v2":
                demo += [
                    "--intelligibility-cfg-rate", str(args.intelligibility),
                    "--similarity-cfg-rate", str(args.similarity),
                ]
            print("[B] convert command per clip would be:\n      "
                  + " ".join(demo))
        except SystemExit as e:
            print(f"[B]   (cannot preview: {e})")
        return 0

    run_one_shot(args, sentences)
    return 0


if __name__ == "__main__":
    sys.exit(main())
