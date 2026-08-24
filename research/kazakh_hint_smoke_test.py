"""
Kazakh HINT smoke test (STEP 6D).
One utterance: 5f2b074881760 (8.79 s, speaker 15872)
Reference: қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды

Tests:
  1. gpt-4o-transcribe    AUTO          (json format — verbose_json rejected for gpt-4o variants)
  2. gpt-4o-transcribe    prompt=Kazakh
  3. gpt-4o-mini-transcribe AUTO
  4. gpt-4o-mini-transcribe prompt=Kazakh
  5. whisper-1            AUTO          (verbose_json)
  6. whisper-1            language=kk
  7. whisper-1            prompt=Kazakh

gpt-4o variants use response_format="json" — verbose_json is rejected (HTTP 400 unsupported_value,
confirmed in first run of this script).
"""

import os
import sys
import time
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import openai

AUDIO_PATH = r"C:\Users\erkin\central-asian-voice-benchmark\benchmark_audio\kazakh\5f2b074881760.wav"
REFERENCE = "қазір болған аумаққа қаладағы коммуналдық қызмет толық жұмылдырылды"
DURATION_S = 8.789
USD_PER_MIN = {"gpt-4o-transcribe": 0.006, "gpt-4o-mini-transcribe": 0.003, "whisper-1": 0.006}

client = openai.OpenAI()

def cost(model):
    return DURATION_S / 60 * USD_PER_MIN[model]

def run(label, model, fmt="json", **kwargs):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"  model={model}  fmt={fmt}  kwargs={kwargs}")
    t0 = time.monotonic()
    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
                response_format=fmt,
                **kwargs
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        # verbose_json → resp has .text and .language attributes
        # json → resp has .text; .language may or may not be present
        # text → resp is a plain string
        if fmt == "text":
            transcript = resp
            detected = None
        else:
            transcript = getattr(resp, "text", str(resp))
            detected = getattr(resp, "language", None)
        print(f"  STATUS:     OK")
        print(f"  LATENCY:    {latency_ms} ms")
        print(f"  FORMAT:     {fmt}")
        print(f"  DETECTED:   {detected}")
        print(f"  TRANSCRIPT: {transcript}")
        print(f"  COST_EST:   ${cost(model):.6f}")
        # print all available attributes for debugging
        if fmt != "text" and hasattr(resp, "__dict__"):
            attrs = {k: v for k, v in vars(resp).items() if not k.startswith("_") and k != "text"}
            if attrs:
                print(f"  RESP_ATTRS: {attrs}")
        return {"ok": True, "transcript": transcript, "detected": detected,
                "latency_ms": latency_ms, "cost_est": cost(model), "fmt": fmt}
    except openai.BadRequestError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        print(f"  STATUS:   BadRequestError (HTTP 400)")
        print(f"  LATENCY:  {latency_ms} ms")
        print(f"  ERROR:    {e}")
        return {"ok": False, "error": str(e), "latency_ms": latency_ms, "cost_est": 0.0, "fmt": fmt}
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        print(f"  STATUS:   EXCEPTION {type(e).__name__}")
        print(f"  LATENCY:  {latency_ms} ms")
        print(f"  ERROR:    {e}")
        return {"ok": False, "error": str(e), "latency_ms": latency_ms, "cost_est": 0.0, "fmt": fmt}

print("KAZAKH HINT SMOKE TEST — STEP 6D (run 2)")
print(f"Utterance:  5f2b074881760")
print(f"Duration:   {DURATION_S} s")
print(f"Reference:  {REFERENCE}")
print("Note: gpt-4o variants use response_format=json (verbose_json rejected)")

results = {}

# gpt-4o-transcribe — json format
results["gpt4o_auto"]   = run("gpt-4o-transcribe / AUTO",          "gpt-4o-transcribe",       fmt="json")
results["gpt4o_prompt"] = run("gpt-4o-transcribe / prompt=Kazakh", "gpt-4o-transcribe",        fmt="json", prompt="Kazakh")

# gpt-4o-mini-transcribe — json format
results["mini_auto"]    = run("gpt-4o-mini-transcribe / AUTO",          "gpt-4o-mini-transcribe", fmt="json")
results["mini_prompt"]  = run("gpt-4o-mini-transcribe / prompt=Kazakh", "gpt-4o-mini-transcribe", fmt="json", prompt="Kazakh")

# whisper-1 — verbose_json (confirmed working in run 1)
results["w1_auto"]      = run("whisper-1 / AUTO",        "whisper-1", fmt="verbose_json")
results["w1_lang_kk"]   = run("whisper-1 / language=kk", "whisper-1", fmt="verbose_json", language="kk")
results["w1_prompt"]    = run("whisper-1 / prompt=Kazakh","whisper-1", fmt="verbose_json", prompt="Kazakh")

total_cost = sum(r["cost_est"] for r in results.values())
print(f"\n{'='*60}")
print(f"TOTAL ESTIMATED COST: ${total_cost:.6f}")
print(f"REFERENCE:            {REFERENCE}")

print("\n--- SUMMARY ---")
for k, v in results.items():
    status = "OK" if v["ok"] else "FAIL"
    if v["ok"]:
        print(f"  {k:20s} {status}  detected={v['detected']}  transcript={v['transcript'][:70]}")
    else:
        print(f"  {k:20s} {status}  {v['error'][:90]}")
