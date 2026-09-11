"""
POST /api/turn — the main pipeline endpoint.

Takes audio + conversation_id + language (+ mode + source_language since
DUB1), returns transcript + AI response (or dub translation) + audio.

Two flows:
  chat/benchmark (mode omitted or 'chat'): original behaviour, optionally
    with an explicit source_language for the STT stage.
  dubbing (mode='dub'): English audio -> English transcript -> stateless
    translation to 'uz'/'kk' -> TTS of the translated text.
"""

import io
import json
import logging
import asyncio
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from product.backend.config import settings
from product.backend.models import TurnRequest, TurnResponse
from product.backend.services.stt import transcribe
from product.backend.services.llm import respond, translate, translate_multi, split_sentences
from product.backend.services.tts import synthesize_b64, concat_wav_b64
from product.backend.services.score import score as score_transcript
from product.backend.services.session import session_manager
from product.backend.services.log_jsonl import log_turn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["turn"])

# Allowed audio MIME types
ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/x-m4a",
    "audio/mp4",
}


async def _to_wav(src_path: Path, dst_path: Path) -> None:
    """Normalize any browser audio to 16 kHz mono 16-bit PCM WAV via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src_path),
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        "-f", "wav",
        str(dst_path),
    ]
    proc = await asyncio.get_running_loop().run_in_executor(
        None, lambda: subprocess.run(cmd, capture_output=True, text=True)
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()}")
    if not dst_path.exists() or dst_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced empty output WAV")


def _get_audio_duration_seconds(file_bytes: bytes, content_type: str) -> float:
    """Estimate audio duration via ffprobe for accuracy."""
    import tempfile, os
    if "wav" not in content_type:
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
                capture_output=True, text=True, timeout=5
            )
            val = result.stdout.strip()
            return float(val) if val else 0.0
        except Exception:
            return 0.0
        finally:
            try: os.unlink(tmp_path)
            except Exception: pass
    data_bytes = max(0, len(file_bytes) - 44)
    return data_bytes / 32000.0


@router.post("/turn")
async def handle_turn(
    audio: UploadFile = File(...),
    conversation_id: str = Form(...),
    language: str = Form(...),
    reference_text: str = Form(""),
    mode: str = Form(""),
    source_language: str = Form(""),
):
    """Process one turn of the voice pipeline.

    Modes:
      - benchmark chat (default, mode omitted/'chat'): STT in `language`,
        conversational LLM reply in `language`. Identical to pre-DUB1.
      - dubbing (mode='dub'): STT in English, stateless translation to
        `language` ('uz'/'kk'), TTS of the translated text.

    Pipeline: Audio Upload → STT → LLM → TTS → Response
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info("[%s] Turn start | conv=%s lang=%s", request_id, conversation_id, language)

    # --- 1. Validate language ---
    if language not in ("uz", "kk"):
        raise HTTPException(status_code=400, detail=f"Invalid language '{language}'. Must be 'uz' or 'kk'.")

    # --- 1b. Validate mode / source_language (DUB1) ---
    mode = mode.strip().lower()
    source_language = source_language.strip().lower()
    if mode not in ("", "chat", "dub"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Must be 'dub', 'chat' or empty.",
        )
    if source_language and source_language not in ("en", "uz", "kk"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_language '{source_language}'. Must be 'en', 'uz', 'kk' or empty.",
        )
    is_dub = mode == "dub"
    if is_dub and source_language not in ("", "en"):
        raise HTTPException(
            status_code=400,
            detail="Dub mode (DUB1) accepts English source speech only.",
        )
    # STT language: forced English in dub mode; otherwise honour an explicit
    # source_language, falling back to `language` (preserves benchmark behaviour).
    stt_lang = "en" if is_dub else (source_language or language)
    logger.info("[%s] Mode=%s stt_lang=%s", request_id, "dub" if is_dub else "chat", stt_lang)

    # --- 2. Validate content type ---
    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_TYPES:
        logger.warning("[%s] Unusual content-type: %s", request_id, audio.content_type)
        # Don't block — let the provider handle unknown types

    # --- 3. Read and validate audio ---
    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    if len(audio_bytes) > settings.max_audio_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large. Max {settings.max_audio_size_mb} MB.",
        )

    # Rough duration check
    estimated_duration = _get_audio_duration_seconds(audio_bytes, audio.content_type or "audio/wav")
    if estimated_duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too long ({estimated_duration:.1f}s). Max {settings.max_audio_duration_seconds}s.",
        )
    logger.info("[%s] Audio received: %d bytes (est. %.1fs)", request_id, len(audio_bytes), estimated_duration)

    # --- 4. Check session limits ---
    if session_manager.is_max_turns_reached(conversation_id):
        raise HTTPException(
            status_code=429,
            detail=f"Session '{conversation_id}' has reached the maximum of {settings.max_turns_per_session} turns.",
        )

    # --- 5. Save uploaded audio ---
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ext = "webm" if audio.content_type and "webm" in audio.content_type else "wav"
    safe_filename = f"{request_id}_{conversation_id}_{language}_raw.{ext}"
    raw_path = settings.upload_dir / safe_filename
    wav_path = settings.upload_dir / f"{request_id}_{conversation_id}_{language}_norm.wav"
    with open(raw_path, "wb") as f:
        f.write(audio_bytes)
    logger.info("[%s] Audio saved to %s (%s, %d bytes)", request_id, raw_path, audio.content_type, len(audio_bytes))

    # Normalize to 16 kHz mono 16-bit PCM WAV for STT
    try:
        await _to_wav(raw_path, wav_path)
    except Exception as e:
        logger.error("[%s] Audio conversion failed: %s", request_id, str(e))
        raise HTTPException(status_code=422, detail="Audio conversion failed. Please check your recording.")

    # --- 6. STT (in stt_lang: 'en' for dubbing, else the target language) ---
    t0 = time.time()
    try:
        transcript = transcribe(wav_path, stt_lang, "audio/wav")
    except Exception as e:
        logger.error("[%s] STT failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail="Speech transcription failed. Please try again.")
    stt_time = time.time() - t0
    logger.info("[%s] STT (%s): %.2fs | transcript=%r", request_id, stt_lang, stt_time, transcript[:80])

    # --- 7. LLM: dub mode translates (stateless), chat mode converses ---
    t0 = time.time()
    dub_parts: list = []
    try:
        if is_dub:
            # DUB3: per-sentence translations enable overlapping per-part TTS.
            # Single sentence -> exactly the DUB1 behaviour.
            dub_parts = translate_multi(transcript, stt_lang, language)
            response_text = " ".join(dub_parts)
            # Dubbing itself is stateless, but we still record the exchange so
            # turn numbering and the per-session turn cap keep working for the UI.
            session_manager.add_turn(conversation_id, "user", transcript)
            session_manager.add_turn(conversation_id, "assistant", response_text)
        else:
            response_text = respond(conversation_id, transcript, language)
    except Exception as e:
        logger.error("[%s] LLM failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail="Response generation failed. Please try again.")
    llm_time = time.time() - t0
    logger.info("[%s] LLM (%s): %.2fs | response=%r", request_id, language, llm_time, response_text[:80])

    # --- 8. TTS (DUB3: dub parts are synthesized concurrently in the
    #     default executor — same thread-pool pattern as _to_wav — so the
    #     wall time is ~ the longest sentence, not the sum of all of them) ---
    t0 = time.time()
    audio_parts: list = []
    try:
        if is_dub and len(dub_parts) > 1:
            loop = asyncio.get_running_loop()
            audio_parts = list(
                await asyncio.gather(
                    *(
                        loop.run_in_executor(
                            None, synthesize_b64, part, language
                        )
                        for part in dub_parts
                    )
                )
            )
            # Backward-compatible single-audio field: the full concatenated dub.
            audio_b64 = concat_wav_b64(audio_parts)
        else:
            audio_b64 = synthesize_b64(response_text, language)
    except Exception as e:
        logger.error("[%s] TTS failed: %s", request_id, str(e))
        raise HTTPException(status_code=502, detail="Audio synthesis failed. Please try again.")
    tts_time = time.time() - t0
    logger.info("[%s] TTS: %.2fs | parts=%d | audio size=%d bytes",
                request_id, tts_time, len(audio_parts), len(audio_b64))

    # --- 9. Score transcript against the optional reference ---
    scoring = score_transcript(reference_text, transcript)

    # --- 10. Build response ---
    turn_number = session_manager.get_turn_count(conversation_id)
    stt_ms = round(stt_time * 1000)
    llm_ms = round(llm_time * 1000)
    tts_ms = round(tts_time * 1000)

    response = TurnResponse(
        conversation_id=conversation_id,
        turn_number=turn_number,
        transcript=transcript,
        response_text=response_text,
        audio=audio_b64,
        audio_parts=(audio_parts or None),
        language=language,
        provider_info={
            "stt": f"{settings.stt_provider}/{settings.stt_model}",
            "llm": f"{settings.llm_provider}/{settings.llm_model}",
            "tts": f"{settings.tts_provider}/{settings.tts_model}",
            "mock_mode": settings.mock_mode,
            # DUB1 observability: which flow produced this turn.
            "mode": "dub" if is_dub else "chat",
            "source_language": stt_lang,
            # DUB3: how many dub sentence parts the queue carries (0 = chat).
            "dub_sentences": len(dub_parts),
        },
        wer=scoring["wer"],
        cer=scoring["cer"],
        scored=scoring["scored"],
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=tts_ms,
        total_ms=stt_ms + llm_ms + tts_ms,
    )

    logger.info(
        "[%s] Done | turn=%d | stt=%.2fs llm=%.2fs tts=%.2fs total=%.2fs",
        request_id, turn_number,
        stt_time, llm_time, tts_time,
        stt_time + llm_time + tts_time,
    )

    # --- 11. Structured JSONL log (non-blocking, best-effort) ---
    log_turn(
        request_id=request_id,
        conversation_id=conversation_id,
        language=language,
        turn_number=turn_number,
        stt_ms=stt_ms,
        llm_ms=llm_ms,
        tts_ms=tts_ms,
        transcript_len=len(transcript),
        response_len=len(response_text),
        audio_bytes=len(audio_b64),
        mock_mode=settings.mock_mode,
    )

    # --- 12. Clean up temp audio files ---
    for _path in (raw_path, wav_path):
        try:
            _path.unlink(missing_ok=True)
        except Exception:
            pass

    return response


# =========================================================================
# DUB2 — minimal streaming transport (NDJSON) over POST.
#
# Same validation and pipeline as /api/turn, but each dub sentence part is
# delivered the moment it is ready (meta → part* → done). /api/turn is
# preserved untouched for legacy clients. No WebSockets, no new deps.
# =========================================================================


class DubJobRunner:
    """Order-preserving per-sentence job runner with pending-work cancel.

    Each job runs translate→TTS for one sentence in a worker thread. The
    consumer awaits futures IN ORDER, so parts arrive ordered even though
    work happens in parallel. cancel_pending() cancels jobs that have not
    started yet (in-flight threads are left to finish and are discarded).
    """

    def __init__(self, items, job_fn, max_workers: int = 4):
        self._ex = ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items))))
        self._lock = threading.Lock()
        self.started = 0
        self._futures = [self._ex.submit(self._run, job_fn, it) for it in items]

    def _run(self, fn, item):
        with self._lock:
            self.started += 1
        return fn(item)

    def future(self, i: int):
        return self._futures[i]

    def cancel_pending(self) -> int:
        """Return the number of not-yet-started jobs that were cancelled."""
        n = 0
        for f in self._futures:
            if f.cancel():
                n += 1
        return n

    def shutdown(self):
        self._ex.shutdown(wait=False)


def _ndjson(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


@router.post("/turn/stream")
async def handle_turn_stream(
    audio: UploadFile = File(...),
    conversation_id: str = Form(...),
    language: str = Form(...),
    reference_text: str = Form(""),
    mode: str = Form("dub"),
    source_language: str = Form(""),
):
    """Streaming counterpart of /api/turn (DUB2). NDJSON events:
       {"type":"meta", transcript, stt_ms, ...}
       {"type":"part", index, text, audio}      (as soon as each is ready)
       {"type":"done", response_text, audio, *_ms, wer, cer, scored, ...}
       {"type":"error", detail}                  (after headers were sent)
    """
    request_id = uuid.uuid4().hex[:8]
    logger.info("[%s] Stream turn start | conv=%s lang=%s", request_id, conversation_id, language)

    # --- Same validation as /api/turn (before the response starts) ---
    if language not in ("uz", "kk"):
        raise HTTPException(status_code=400, detail=f"Invalid language '{language}'. Must be 'uz' or 'kk'.")
    mode = mode.strip().lower()
    source_language = source_language.strip().lower()
    if mode not in ("", "chat", "dub"):
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}'. Must be 'dub', 'chat' or empty.")
    if source_language and source_language not in ("en", "uz", "kk"):
        raise HTTPException(status_code=400, detail=f"Invalid source_language '{source_language}'. Must be 'en', 'uz', 'kk' or empty.")
    is_dub = mode == "dub"
    if is_dub and source_language not in ("", "en"):
        raise HTTPException(status_code=400, detail="Dub mode (DUB1) accepts English source speech only.")
    stt_lang = "en" if is_dub else (source_language or language)

    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(audio_bytes) > settings.max_audio_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Audio too large. Max {settings.max_audio_size_mb} MB.")
    estimated_duration = _get_audio_duration_seconds(audio_bytes, audio.content_type or "audio/wav")
    if estimated_duration > settings.max_audio_duration_seconds:
        raise HTTPException(status_code=413, detail=f"Audio too long ({estimated_duration:.1f}s). Max {settings.max_audio_duration_seconds}s.")

    if session_manager.is_max_turns_reached(conversation_id):
        raise HTTPException(
            status_code=429,
            detail=f"Session '{conversation_id}' has reached the maximum of {settings.max_turns_per_session} turns.",
        )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    ext = "webm" if audio.content_type and "webm" in audio.content_type else "wav"
    raw_path = settings.upload_dir / f"{request_id}_{conversation_id}_{language}_sraw.{ext}"
    wav_path = settings.upload_dir / f"{request_id}_{conversation_id}_{language}_snorm.wav"
    with open(raw_path, "wb") as f:
        f.write(audio_bytes)
    try:
        await _to_wav(raw_path, wav_path)
    except Exception as e:
        logger.error("[%s] Audio conversion failed: %s", request_id, str(e))
        raise HTTPException(status_code=422, detail="Audio conversion failed. Please check your recording.")

    async def generate():
        loop = asyncio.get_running_loop()
        runner = None
        t_all = time.time()
        try:
            t0 = time.time()
            try:
                transcript = await loop.run_in_executor(None, transcribe, wav_path, stt_lang, "audio/wav")
            except Exception as e:
                logger.error("[%s] Stream STT failed: %s", request_id, str(e))
                yield _ndjson({"type": "error", "detail": "Speech transcription failed. Please try again."})
                return
            stt_ms = round((time.time() - t0) * 1000)
            yield _ndjson({"type": "meta", "request_id": request_id, "transcript": transcript,
                           "language": language, "mode": "dub" if is_dub else "chat",
                           "source_language": stt_lang, "stt_ms": stt_ms})

            texts, parts_b64, tr_ms, ts_ms = [], [], 0, 0
            t1 = time.time()
            if is_dub:
                sents = split_sentences(transcript) or [transcript]

                def _job(sent):
                    a = time.time()
                    txt = translate(sent, stt_lang, language)
                    b = time.time()
                    wav_b64 = synthesize_b64(txt, language)
                    c = time.time()
                    return {"text": txt, "audio": wav_b64,
                            "tr_ms": round((b - a) * 1000), "ts_ms": round((c - b) * 1000)}

                runner = DubJobRunner(sents, _job, max_workers=4)
                try:
                    for i in range(len(sents)):
                        fut = runner.future(i)
                        while not fut.done():
                            await asyncio.sleep(0.02)
                        part = fut.result()
                        texts.append(part["text"])
                        parts_b64.append(part["audio"])
                        tr_ms += part["tr_ms"]
                        ts_ms += part["ts_ms"]
                        # ordered delivery: part i is emitted only after i-1
                        yield _ndjson({"type": "part", "index": i,
                                       "text": part["text"], "audio": part["audio"],
                                       "at_ms": round((time.time() - t_all) * 1000)})
                finally:
                    if runner is not None:
                        # Normal end: nothing left to cancel. Client gone /
                        # failure mid-stream: drop every not-yet-started job.
                        runner.cancel_pending()
                        runner.shutdown()
                        runner = None
                response_text = " ".join(texts)
                session_manager.add_turn(conversation_id, "user", transcript)
                session_manager.add_turn(conversation_id, "assistant", response_text)
                audio_b64 = concat_wav_b64(parts_b64)
            else:
                reply = await loop.run_in_executor(None, respond, conversation_id, transcript, language)
                audio_b64 = await loop.run_in_executor(None, synthesize_b64, reply, language)
                response_text, texts, parts_b64 = reply, [reply], [audio_b64]
                yield _ndjson({"type": "part", "index": 0, "text": reply,
                               "audio": audio_b64,
                               "at_ms": round((time.time() - t_all) * 1000)})

            pipeline_ms = round((time.time() - t1) * 1000)
            llm_ms = tr_ms if is_dub else pipeline_ms
            tts_ms = ts_ms if is_dub else 0
            scoring = score_transcript(reference_text, transcript)
            turn_number = session_manager.get_turn_count(conversation_id)
            provider = {
                "stt": f"{settings.stt_provider}/{settings.stt_model}",
                "llm": f"{settings.llm_provider}/{settings.llm_model}",
                "tts": f"{settings.tts_provider}/{settings.tts_model}",
                "mock_mode": settings.mock_mode,
                "mode": "dub" if is_dub else "chat",
                "source_language": stt_lang,
                "dub_sentences": len(texts),
            }
            yield _ndjson({"type": "done", "conversation_id": conversation_id,
                           "turn_number": turn_number, "response_text": response_text,
                           "audio": audio_b64, "audio_parts": parts_b64 if len(parts_b64) > 1 else None,
                           "language": language, "provider_info": provider,
                           "wer": scoring["wer"], "cer": scoring["cer"], "scored": scoring["scored"],
                           "stt_ms": stt_ms, "llm_ms": llm_ms, "tts_ms": tts_ms,
                           "total_ms": stt_ms + pipeline_ms})
            log_turn(
                request_id=request_id, conversation_id=conversation_id,
                language=language, turn_number=turn_number, stt_ms=stt_ms,
                llm_ms=llm_ms, tts_ms=tts_ms,
                transcript_len=len(transcript), response_len=len(response_text),
                audio_bytes=len(audio_b64), mock_mode=settings.mock_mode,
            )
            logger.info("[%s] Stream done | parts=%d", request_id, len(parts_b64))
        except (asyncio.CancelledError, GeneratorExit):
            # DUB2: client went away (barge-in / end session) — stop pending work.
            if runner is not None:
                cancelled = runner.cancel_pending()
                runner.shutdown()
                logger.info("[%s] Stream cancelled by client; %d pending jobs dropped",
                            request_id, cancelled)
            raise
        except Exception as e:
            logger.error("[%s] Stream pipeline failed: %s", request_id, str(e))
            try:
                yield _ndjson({"type": "error", "detail": "Response generation failed. Please try again."})
            except Exception:
                pass
        finally:
            for _path in (raw_path, wav_path):
                try:
                    _path.unlink(missing_ok=True)
                except Exception:
                    pass

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})