"""Serialized Route B worker client. No torch dependency in the API process."""
import json
import logging
import os
import queue
import signal
import subprocess
import threading
import time
import uuid
from collections import deque

logger = logging.getLogger(__name__)
PREFIX = "BIROVOZ_RESULT "


class RouteBWorker:
    """Caller holds the local-clone lock for run() and close()."""

    def __init__(self, own_process_group=True):
        self.proc = None
        self.key = None
        self.threads = []
        self.own_process_group = own_process_group

    def close(self):
        proc, self.proc = self.proc, None
        self.key = None
        if proc is None:
            return
        # Kill the whole group, including any active Seed-VC subprocess.
        try:
            if os.name == "nt":
                if proc.poll() is None:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                   capture_output=True, timeout=5)
            elif self.own_process_group:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif proc.poll() is None:
                proc.kill()
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            for thread in self.threads:
                thread.join(timeout=2)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()
            self.threads = []

    def _start(self, cmd, cwd, env):
        self.close()
        self.events = queue.Queue()
        self.err_tail = deque(maxlen=5)
        kwargs = ({"start_new_session": True}
                  if os.name != "nt" and self.own_process_group else {})
        self.proc = subprocess.Popen(
            cmd[:2] + ["--worker"], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs)

        def stdout(pipe, events):
            try:
                for line in pipe:
                    events.put(line.rstrip("\r\n"))
            finally:
                events.put(None)

        def stderr(pipe, tail):
            for line in pipe:
                tail.append(line.rstrip("\r\n"))

        self.threads = [
            threading.Thread(target=stdout, args=(self.proc.stdout, self.events), daemon=True),
            threading.Thread(target=stderr, args=(self.proc.stderr, self.err_tail), daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    def run(self, cmd, timeout, cwd, env, parse_markers):
        start = time.monotonic()
        key = (tuple(cmd[:2]), cwd, tuple(sorted(env.items())))
        timings, markers = {"_t0": start}, {}
        tail = deque(maxlen=5)
        try:
            if self.proc is None or self.proc.poll() is not None or self.key != key:
                self._start(cmd, cwd, env)
                self.key = key
            self.err_tail.clear()
            request_id = uuid.uuid4().hex
            self.proc.stdin.write(json.dumps({"id": request_id, "argv": cmd[2:]}) + "\n")
            self.proc.stdin.flush()
            while True:
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise RuntimeError(f"Route B worker timed out after {timeout}s")
                try:
                    line = self.events.get(timeout=remaining)
                except queue.Empty:
                    raise RuntimeError(f"Route B worker timed out after {timeout}s") from None
                if line is None:
                    raise RuntimeError("Route B worker exited before completing the request")
                if line.startswith(PREFIX):
                    reply = json.loads(line[len(PREFIX):])
                    if reply.get("id") != request_id:
                        raise RuntimeError("Route B worker response ID mismatch")
                    if not reply.get("ok"):
                        raise RuntimeError(f"Route B worker failed: {reply.get('error')}")
                    break
                tail.append(line)
                parse_markers(line, timings, markers)
                # Stage progress is now visible while the GPU is working.
                if line.startswith("[B]"):
                    logger.info("route-b: %s", line)
                else:
                    logger.debug("route-b: %s", line)
            total = time.monotonic() - start
            timings.pop("_t0", None)
            timings["total_s"] = round(total, 3)
            return {"timings": timings, "markers": markers, "total_s": total,
                    "stdout_tail": list(tail), "stderr_tail": list(self.err_tail)}
        except BaseException as exc:
            self.close()
            diagnostics = " | ".join(getattr(self, "err_tail", []) or tail)
            if isinstance(exc, Exception):
                raise RuntimeError(f"{exc}; {diagnostics}") from exc
            raise
