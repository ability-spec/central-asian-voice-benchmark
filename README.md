# BirOvoz — Central Asian Voice Benchmark

Research and a local voice demo for Uzbek and Kazakh. The benchmark evaluates
speech recognition, translation and dubbing; the demo runs an STT → LLM → TTS
pipeline with streaming English-to-Uzbek/Kazakh dubbing.

- [Research scope and methodology](PROJECT_BENCHMARK.md)
- [Frozen benchmark report](research/final_benchmark_report.md)
- [Local setup and provider/model configuration](product/README.md)
- [Current handoff and release acceptance](HANDOFF.md)

## Quick start

From the repository root, with Python 3.11+ and ffmpeg on PATH:

```bash
python -m venv product/backend/.venv
# macOS/Linux
source product/backend/.venv/bin/activate
# Windows PowerShell instead: .\product\backend\.venv\Scripts\Activate.ps1
python -m pip install -r product/backend/requirements.txt
```

Copy `product/backend/.env.example` to `product/backend/.env`, then run:

```bash
python -m uvicorn product.backend.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Without an OpenAI key, the demo uses deterministic
mock responses. MOCK results are not real accuracy measurements. Configure
live providers in the local `.env`; keep credentials and voice/model assets
outside version control. Local voice clone currently supports Uzbek only.

## CPU verification

```bash
python -m pip install pytest pytest-asyncio httpx jiwer
python -m pytest tests product/backend/tests -q
```

These tests use provider/model substitutes. Real voice quality, Windows/NVIDIA
compatibility, cold/warm latency and microphone playback acceptance remain
manual checks listed in the handoff. The leaderboard serves frozen research
results and does not recompute them from demo uploads.
