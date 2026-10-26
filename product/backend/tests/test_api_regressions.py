"""Regression tests for voice enrollment and streaming latency reporting."""

import asyncio
import json
import time

from product.backend.config import settings
from product.backend.routers import health as health_router
from product.backend.routers import turn as turn_router
from product.backend.routers import voice as voice_router
from product.backend.services import voice_clone


def test_voice_enrollment_does_not_block_health(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr(voice_clone, "status", lambda: {"provider": "elevenlabs"})

    def slow_enroll(*args, **kwargs):
        time.sleep(0.35)
        return {"voice_id": "test-voice-id"}

    monkeypatch.setattr(voice_clone, "enroll", slow_enroll)

    async def exercise():
        started = time.perf_counter()
        enrollment = asyncio.create_task(
            voice_router.enroll_voice(audio=[], consent="yes", name="test")
        )

        async def check_health():
            await asyncio.sleep(0.02)
            return await health_router.health()

        health_task = asyncio.create_task(check_health())
        health_response = await health_task
        elapsed = time.perf_counter() - started
        result = await enrollment

        assert health_response.status == "ok"
        assert result["enrolled"] is True
        assert elapsed < 0.2

    asyncio.run(exercise())


def test_stream_total_ms_matches_reported_stage_latencies(monkeypatch, tmp_path):
    monkeypatch.setattr(turn_router.settings, "upload_dir", tmp_path)
    monkeypatch.setattr(turn_router.settings, "max_audio_size_mb", 1)
    monkeypatch.setattr(turn_router.settings, "max_audio_duration_seconds", 30)
    monkeypatch.setattr(turn_router.session_manager, "is_max_turns_reached", lambda *_: False)
    monkeypatch.setattr(turn_router.session_manager, "add_turn", lambda *_: None)
    monkeypatch.setattr(turn_router.session_manager, "get_turn_count", lambda *_: 1)

    class FakeUpload:
        content_type = "audio/wav"

    async def read_bounded_audio(_audio):
        return b"audio"

    async def to_wav(_source, destination):
        destination.write_bytes(b"wav")

    async def blocking(fn, *_args):
        if fn is turn_router.transcribe:
            return "First sentence. Second sentence."
        if fn is turn_router._check_normalized_duration:
            return None
        return 1.0

    monkeypatch.setattr(turn_router, "_read_bounded_audio", read_bounded_audio)
    monkeypatch.setattr(turn_router, "_to_wav", to_wav)
    monkeypatch.setattr(turn_router, "_blocking", blocking)
    monkeypatch.setattr(turn_router, "split_sentences", lambda _text: ["First sentence.", "Second sentence."])

    def translate(_sentence, *_args):
        time.sleep(0.05)
        return "translated"

    def synthesize(_text, _language):
        time.sleep(0.05)
        return "audio-part"

    monkeypatch.setattr(turn_router, "translate", translate)
    monkeypatch.setattr(turn_router, "synthesize_b64", synthesize)
    monkeypatch.setattr(turn_router, "take_last_report", lambda: {})
    monkeypatch.setattr(turn_router, "_merge_part_reports", lambda _reports: {})
    monkeypatch.setattr(turn_router, "concat_wav_b64", lambda _parts: "combined-audio")
    monkeypatch.setattr(
        turn_router, "score_transcript",
        lambda *_args: {"wer": None, "cer": None, "scored": False},
    )
    monkeypatch.setattr(voice_clone, "tts_label", lambda *_args: "mock")
    monkeypatch.setattr(turn_router, "log_turn", lambda **_kwargs: None)

    async def exercise():
        response = await turn_router.handle_turn_stream(
            audio=FakeUpload(),
            conversation_id="test-session",
            language="uz",
            reference_text="",
            mode="dub",
            source_language="",
        )
        events = []
        async for chunk in response.body_iterator:
            events.extend(
                json.loads(line)
                for line in chunk.decode("utf-8").splitlines()
                if line.strip()
            )
        return next(event for event in events if event["type"] == "done")

    done = asyncio.run(exercise())
    assert done["total_ms"] == done["stt_ms"] + done["llm_ms"] + done["tts_ms"]
