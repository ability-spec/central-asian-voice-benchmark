"""Keep Sayro in RAM between jobs; give Seed-VC exclusive use of model VRAM."""
import gc
import time

from common import load_qwen_model


class SayroCache:
    def __init__(self):
        self.model = None
        self.key = None
        self.seed_worker = None

    def close_seed_worker(self):
        if self.seed_worker is not None:
            self.seed_worker.close()
            self.seed_worker = None

    def get_seed_worker(self):
        if self.seed_worker is None:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from route_b_worker import RouteBWorker
            # Inherit the outer wrapper's process group, so the backend's
            # timeout/shutdown kills BOTH workers and any descendants.
            self.seed_worker = RouteBWorker(own_process_group=False)
        return self.seed_worker

    def _move(self, device):
        import torch
        device = torch.device(device)
        model = self.model
        # Qwen3TTSModel and Qwen3TTSTokenizer are wrappers, not nn.Modules.
        # Moving only model.model leaves the separate audio tokenizer on GPU.
        model.model.to(device)
        model.device = device
        tokenizer = model.model.speech_tokenizer
        tokenizer.model.to(device)
        tokenizer.device = device

    def acquire(self, args):
        from b_sayro_then_seedvc import SAYRO_ID
        key = (SAYRO_ID, args.device, args.dtype, args.attn)
        start = time.perf_counter()
        if self.model is None or self.key != key:
            self.clear()
            self.model = load_qwen_model(*key)
            self.key = key
            print(f"[B] sayro_cache=miss model_load_s={time.perf_counter() - start:.3f}")
        else:
            self._move(args.device)
            print(f"[B] sayro_cache=hit restore_s={time.perf_counter() - start:.3f}")
        return self.model

    def park(self):
        import torch
        start = time.perf_counter()
        self._move("cpu")
        gc.collect()
        torch.cuda.empty_cache()
        print(f"[B] sayro_offload_s={time.perf_counter() - start:.3f}")

    def clear(self):
        self.close_seed_worker()
        self.model = None
        self.key = None
        gc.collect()
        # clear() is also called before torch has been imported on the first job.
        import sys
        torch = sys.modules.get("torch")
        if torch is not None:
            torch.cuda.empty_cache()
