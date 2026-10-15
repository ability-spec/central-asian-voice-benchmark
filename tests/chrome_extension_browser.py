"""Offline panel acceptance in Chromium using a Chrome API test adapter.

The HTTP fixture only returns deterministic WAVs; no provider/model is imported.
Run with Python + Playwright and CHROMIUM_PATH, or installed /usr/bin/chromium.
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer, SimpleHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "product" / "chrome-extension"
state = {"mock": True, "scenario": "normal", "requests": [], "provider": "local-clone"}


def wav(seconds=0.3):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        # Quiet deterministic fixture, not generated speech.
        w.writeframes(struct.pack("<h", 200) * int(seconds * 16000))
    return out.getvalue()


AUDIO = base64.b64encode(wav()).decode()


def voice():
    return {"resolved_provider": state["provider"],
            "local_clone": {"configured": True, "languages": ["uz"]},
            "elevenlabs": {"configured": False}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_headers(204)

    def do_GET(self):
        state["requests"].append(("GET", self.path))
        if self.path == "/health":
            self.send_headers()
            self.wfile.write(json.dumps({"status": "ok", "mock_mode": state["mock"],
                "audio_tools_ready": True, "max_audio_duration_seconds": 30,
                "max_audio_size_mb": 10, "max_turns_per_session": 20}).encode())
        elif self.path == "/api/voice/status":
            self.send_headers()
            self.wfile.write(json.dumps(voice()).encode())
        else:
            self.send_headers(404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/api/voice/provider":
            state["provider"] = json.loads(raw)["provider"]
            state["requests"].append(("POST", self.path))
            self.send_headers()
            self.wfile.write(json.dumps(voice()).encode())
            return
        state["requests"].append(("POST", self.path))
        assert self.path == "/api/turn/stream", self.path
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw)
        fields = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True)
                  for p in message.iter_parts()}
        assert fields["mode"] == b"dub"
        assert fields["source_language"] == b"en"
        assert fields["language"] in (b"uz", b"kk")
        assert fields["audio"]
        assert set(fields) == {"mode", "source_language", "language", "audio", "conversation_id"}
        scenario = state["scenario"]
        if scenario == "http-error":
            self.send_headers(413)
            self.wfile.write(b'{"detail":"Audio too long"}')
            return
        self.send_headers(content_type="application/x-ndjson; charset=utf-8")
        events = [
            {"type": "meta", "transcript": "Fixture English phrase."},
            {"type": "part", "index": 0, "text": "Salom.", "audio": AUDIO},
            {"type": "part", "index": 1, "text": "Qalaysiz?", "audio": AUDIO},
            {"type": "done", "response_text": "Salom. Qalaysiz?", "audio": AUDIO,
             "provider_info": {"mock_mode": state["mock"], "tts": "openai/tts-1 (fallback)",
                               "stt": "fixture", "llm": "fixture"},
             "stt_ms": 2, "llm_ms": 3, "tts_ms": 4, "total_ms": 9},
        ]
        if scenario == "truncated":
            events = events[:2]
        elif scenario == "server-error":
            events = [events[0], {"type": "error", "detail": "No speech detected."}]
        try:
            if scenario == "delayed":
                time.sleep(2)
            for event in events:
                # Split byte chunks through multi-byte text / JSON lines.
                payload = (json.dumps(event, ensure_ascii=False) + "\n").encode()
                for chunk in [payload[:5], payload[5:]]:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                time.sleep(0.07)
        except (BrokenPipeError, ConnectionResetError):
            pass


def turns():
    return sum(path == "/api/turn/stream" for _, path in state["requests"])


def run():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    class PanelHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(EXTENSION), **kwargs)

        def log_message(self, *_):
            pass

        def end_headers(self):
            self.send_header("Content-Security-Policy", "script-src 'self'; object-src 'none'; connect-src 'self' http://127.0.0.1:* http://localhost:*; media-src 'self' blob:")
            super().end_headers()

    panel_server = ThreadingHTTPServer(("127.0.0.1", 8123), PanelHandler)
    threading.Thread(target=panel_server.serve_forever, daemon=True).start()
    failures = []
    checks = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                headless=True, args=["--no-sandbox", "--disable-breakpad", "--disable-crash-reporter",
                      "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            context = browser.new_context(viewport={"width": 390, "height": 900}, accept_downloads=True)
            context.add_init_script("""window.chrome = {
                storage: {local: {
                  get: async keys => {
                    const saved = JSON.parse(localStorage.getItem('chrome-test-settings') || '{}');
                    return Object.fromEntries(keys.filter(k => k in saved).map(k => [k, saved[k]]));
                  },
                  set: async data => localStorage.setItem('chrome-test-settings',
                    JSON.stringify({...JSON.parse(localStorage.getItem('chrome-test-settings') || '{}'), ...data}))
                }},
                runtime: {getURL: path => location.origin + '/' + path},
                tabs: {create: async options => window.open(options.url, '_blank')}
            };""")
            page = context.new_page()
            page.on("pageerror", lambda e: failures.append(str(e)))
            page.goto("http://127.0.0.1:8123/sidepanel.html")
            expect(page.locator("#connectionLabel")).to_contain_text("MOCK")
            expect(page.locator("#voice")).to_have_value("local-clone")
            page.locator("#language").select_option("kk")
            expect(page.locator("#voiceHint")).to_contain_text("стандартный OpenAI")
            page.locator("#language").select_option("uz")
            checks.append("health, provider availability and truthful Kazakh limitation")

            # The built-in demo must cause zero network requests.
            page.locator(".preferences").evaluate("el => el.open = true")
            before = len(state["requests"])
            page.locator("#demo").click()
            expect(page.locator("#resultBadge")).to_contain_text("DEMO")
            expect(page.locator("#download")).to_be_visible()
            assert len(state["requests"]) == before
            page.wait_for_timeout(700)
            page.locator("#newSession").click()
            expect(page.locator("#result")).to_be_hidden()
            checks.append("built-in demo without API calls and new-session cleanup")

            # Actual MediaRecorder, fake physical device, no uploads until Send.
            before = turns()
            page.locator("#record").click()
            expect(page.locator("#sendRecording")).to_be_visible()
            page.wait_for_timeout(700)
            page.locator("#sendRecording").click()
            expect(page.locator("#send")).to_be_enabled(timeout=10000)
            assert turns() == before
            assert page.evaluate("document.querySelector('#inputPreview').duration") > 0
            checks.append("MediaRecorder WebM duration validation; no automatic upload")
            page.locator("#send").click()
            expect(page.locator("#download")).to_be_visible()
            expect(page.locator("#resultBadge")).to_contain_text("MOCK")
            expect(page.locator("#translation")).to_have_text("Salom. Qalaysiz?")
            with page.expect_download() as downloaded:
                page.locator("#download").click()
            assert Path(downloaded.value.path()).read_bytes() == wav()
            page.wait_for_timeout(500)
            page.locator("#replay").click()
            expect(page.locator("#stop")).to_be_enabled()
            page.locator("#stop").click()
            assert page.evaluate("document.querySelector('#player').paused")
            checks.append("real multipart/NDJSON, ordered playback, WAV download and replay Stop")

            page.locator("#file").set_input_files({"name": "long.wav", "mimeType": "audio/wav", "buffer": wav(31)})
            expect(page.locator("#statusTitle")).to_have_text("Аудио не принято")
            expect(page.locator("#send")).to_be_disabled()
            checks.append("31-second audio rejected before sending")
            page.locator("#file").set_input_files({"name": "short.wav", "mimeType": "audio/wav", "buffer": wav()})
            expect(page.locator("#send")).to_be_enabled()

            # A server changing mock->live cannot silently start a paid request.
            state["mock"] = False
            before = turns()
            page.locator("#send").click()
            expect(page.locator("#statusTitle")).to_have_text("Запрос не завершён")
            expect(page.locator("#costBox")).to_be_visible()
            assert turns() == before
            page.locator("#consent").check()
            expect(page.locator("#send")).to_be_enabled()
            page.locator("#send").click()
            expect(page.locator("#resultBadge")).to_contain_text("FALLBACK")
            expect(page.locator("#download")).to_be_visible()
            page.wait_for_timeout(800)
            checks.append("mock->live consent gate and actual fallback label (fixture only)")

            # Stop a delayed stream, immediately send another; old response
            # must not reset new state, inject audio or overwrite transcript.
            state["scenario"] = "delayed"
            page.locator("#send").click()
            expect(page.locator("#statusTitle")).to_have_text("Обрабатываем аудио")
            page.wait_for_timeout(150)
            page.locator("#stop").click()
            state["scenario"] = "normal"
            page.locator("#send").click()
            expect(page.locator("#download")).to_be_visible()
            page.wait_for_timeout(2300)
            expect(page.locator("#translation")).to_have_text("Salom. Qalaysiz?")
            checks.append("Stop while processing, immediate next request and no stale callbacks")

            for scenario in ["truncated", "server-error", "http-error"]:
                state["scenario"] = scenario
                page.locator("#send").click()
                expect(page.locator("#statusTitle")).to_have_text("Запрос не завершён")
                expect(page.locator("#download")).to_be_hidden()
                expect(page.locator("#send")).to_be_enabled()
            checks.append("truncated stream, provider error and HTTP error are not completed WAVs")
            state["scenario"] = "normal"
            page.locator("#newSession").click()
            page.locator("#backendUrl").fill("https://example.com")
            page.locator("#saveSettings").click()
            expect(page.locator("#statusTitle")).to_have_text("Адрес не сохранён")
            checks.append("remote backend URL refused")

            # Save/reload a local setting and show neutral disconnected state.
            page.locator("#backendUrl").fill("http://127.0.0.1:65530")
            page.locator("#saveSettings").click()
            expect(page.locator("#connectionLabel")).to_have_text("Сервер не подключён", timeout=10000)
            page.reload()
            expect(page.locator("#backendUrl")).to_have_value("http://127.0.0.1:65530")
            expect(page.locator("#send")).to_be_disabled()
            checks.append("persisted connection setting and disconnected send gate")

            state["mock"] = True
            page.locator(".preferences").evaluate("el => el.open = true")
            page.locator("#backendUrl").fill("http://127.0.0.1:8000")
            page.locator("#saveSettings").click()
            expect(page.locator("#connectionLabel")).to_contain_text("MOCK")
            page.locator("#voice").select_option("openai")
            expect(page.locator("#statusTitle")).to_have_text("Голос изменён")
            assert state["provider"] == "openai"
            page.locator("#voice").select_option("local-clone")
            expect(page.locator("#statusTitle")).to_have_text("Голос изменён")
            checks.append("provider selection uses existing status/provider contract")

            # Screenshots of the actual interactive panel, not a static mock-up.
            screenshots = ROOT / "logs" / "chrome-extension-browser"
            screenshots.mkdir(parents=True, exist_ok=True)
            page.locator(".preferences").evaluate("el => el.open = false")
            page.screenshot(path=str(screenshots / "panel.png"), full_page=True)
            page.locator(".preferences").evaluate("el => el.open = true")
            page.locator("#demo").click()
            expect(page.locator("#download")).to_be_visible()
            page.wait_for_timeout(700)
            page.locator(".preferences").evaluate("el => el.open = false")
            page.screenshot(path=str(screenshots / "demo-result.png"), full_page=True)
            page.set_viewport_size({"width": 300, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(screenshots / "panel-narrow.png"), full_page=True)
            checks.append("390px and 300px layouts without horizontal overflow")
            assert not failures, failures
            report = {"browser": browser.version, "base_commit": "78c932cfeda680429d6538bd991ccc42c13a9776",
                      "checks": checks, "page_errors": failures, "model_calls": 0, "paid_calls": 0,
                      "note": "Interactive panel served on localhost with a Chrome API test adapter and matching CSP. Native unpacked extension loading is blocked by this environment's browser administrator policy and remains a manual ASUS check. Fake microphone, deterministic localhost fixture; not Windows/model quality acceptance."}
            (screenshots / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        panel_server.shutdown()
        panel_server.server_close()


if __name__ == "__main__":
    run()
