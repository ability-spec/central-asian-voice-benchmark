"""Adapter for the user's Seed-VC V2 batch CLI; leaves its checkout unchanged.

Run only in SEEDVC_PYTHON, with the Seed-VC checkout as cwd. CPU-offload finishes
before a success reply, so the next Sayro job can safely restore its GPU weights.
"""
import argparse
import gc
import importlib.util
from pathlib import Path
import sys
import time

from tensor_cache import move_model_and_caches
from worker_protocol import serve


def boolean(value):
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def make_parser():
    # Defaults and names match the uploaded inference_v2.py. Do not change
    # sampling / quality parameters when switching between CLI and worker.
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference-script", required=True)
    parser.add_argument("--source-list", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--source", default=None)
    parser.add_argument("--output", default="./output")
    parser.add_argument("--diffusion-steps", type=int, default=30)
    parser.add_argument("--length-adjust", type=float, default=1.0)
    parser.add_argument("--intelligibility-cfg-rate", type=float, default=0.7)
    parser.add_argument("--similarity-cfg-rate", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--repetition-penalty", type=float, default=1.0)
    parser.add_argument("--convert-style", type=boolean, default=False)
    parser.add_argument("--anonymization-only", type=boolean, default=False)
    parser.add_argument("--compile", type=boolean, default=False)
    parser.add_argument("--ar-checkpoint-path", default=None)
    parser.add_argument("--cfm-checkpoint-path", default=None)
    return parser


class SeedVCSession:
    def __init__(self):
        self.module = None
        self.key = None

    def clear(self):
        if self.module is not None:
            self.module.vc_wrapper_v2 = None
        self.module = None
        self.key = None
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def run(self, argv):
        args = make_parser().parse_args(argv)
        if args.compile:
            raise RuntimeError("Compiled Seed-VC graphs cannot be CPU-offloaded by this adapter")
        script = Path(args.inference_script).resolve()
        # A fresh process is used when the environment/cwd changes. Invalidate
        # the in-process cache if the script or explicitly selected weights change.
        def fingerprint(path):
            if path is None:
                return None
            p = Path(path).resolve()
            stat = p.stat()
            return (str(p), stat.st_size, stat.st_mtime_ns)
        key = (fingerprint(script), fingerprint(args.ar_checkpoint_path),
               fingerprint(args.cfm_checkpoint_path))
        start = time.perf_counter()
        if self.module is None or key != self.key:
            self.clear()
            # Preserve imports from the external checkout (modules, hf_utils).
            sys.path.insert(0, str(script.parent))
            spec = importlib.util.spec_from_file_location("birovoz_seedvc_inference", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name in ("load_v2_models", "main", "vc_wrapper_v2", "device"):
                if not hasattr(module, name):
                    raise RuntimeError(f"Seed-VC adapter requires {name} in {script}")
            self.module = module
            module.vc_wrapper_v2 = module.load_v2_models(args)
            self.key = key
            cache_status = "miss"
        else:
            move_model_and_caches(self.module.vc_wrapper_v2, self.module.device)
            cache_status = "hit"
        print(f"[B] seedvc_cache={cache_status}", flush=True)
        print(f"[B] seedvc_acquire_s={time.perf_counter() - start:.3f}", flush=True)
        start = time.perf_counter()
        result = self.module.main(args)
        if result:
            raise RuntimeError(f"Seed-VC main returned {result}")
        print(f"[B] seedvc_conversion_s={time.perf_counter() - start:.3f}", flush=True)
        start = time.perf_counter()
        move_model_and_caches(self.module.vc_wrapper_v2, "cpu")
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print(f"[B] seedvc_offload_s={time.perf_counter() - start:.3f}", flush=True)
        return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("This adapter requires --worker and private stdin requests")
    session = SeedVCSession()
    serve(session.run, session)
