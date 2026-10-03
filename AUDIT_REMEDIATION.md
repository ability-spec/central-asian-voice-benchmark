# October audit remediation

Base: `fix/route-b-diffusion-cli` at `47e092f` (not master).

| Finding | Change |
|---|---|
| V01 | Define the daemon shutdown function before assigning its compatibility alias; imports no longer raise NameError. |
| V02 | Run synchronous STT, LLM and TTS calls outside the event loop, preserving thread-local provider reports. |
| V03 | Remove raw and normalized uploads in failure/success cleanup. Cancellation waits for file-using worker threads; ffmpeg is killed and reaped before cleanup. |
| V04 | Read at most the application upload limit plus one byte instead of allocating the entire upload. |
| V05 | Measure streamed chat LLM and TTS stages separately; preserve total pipeline wall time. |
| Additional regression | Pass configured diffusion steps and length adjustment to Seed-VC v1 too; its conversion path still hardcoded 25/1.0. |

## Verification

CPU-only mocked suite: **146 passed**. It includes current daemon integration, CLI propagation, stage failures, responsiveness, cancellation cleanup, bounded reads and timing tests.

```bash
python -m pip install -r product/backend/requirements.txt pytest pytest-asyncio httpx jiwer
python -m pytest tests/test_pipeline_reliability.py tests/test_dub2_stream.py tests/test_dub3.py tests/test_dub_api.py tests/test_local_clone.py tests/test_voice_clone.py tests/test_routeb_cli.py product/backend/tests/test_routeb_daemon.py -q
```

The broader historical suite is not fully green: `test_route_b_worker.py` and `test_seedvc_worker.py` still target removed pre-daemon configuration fields. Six benchmark-data tests also failed in the text-only audit snapshot because their research fixtures were absent. Those results are not counted as passes; this change does not replace benchmark data or redesign legacy tests.

## Limits

No GPU/model/real-provider benchmark was run. Cancelling synchronous inference cannot forcibly stop its thread; file cleanup waits for it to finish. Put an HTTP body limit at ingress too: Starlette can spool multipart data before the application reads it. Temp-file deletion is best effort if the filesystem refuses unlink. Existing FastAPI lifecycle deprecation warnings remain.
