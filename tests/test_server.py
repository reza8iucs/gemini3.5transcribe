"""The server end to end, with the Gemini sessions replaced by scripted fakes."""

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from starlette.websockets import WebSocketDisconnect

import app as studio
from conftest import FakeSession, message

http = TestClient(studio.app)


def run_session(options=None, audio=(b"\x01\x00" * 1600,), stop=True, headers=None):
    "Opens the app's socket like the page does and returns every message it sends back"
    received = []
    with http.websocket_connect("/ws", headers=headers or {}) as ws:
        ws.send_json({"type": "start", "sampleRate": 16000, **(options or {})})
        for chunk in audio:
            ws.send_bytes(chunk)
        if stop:
            ws.send_json({"type": "stop"})
        try:
            while True:
                received.append(ws.receive_json())
        except WebSocketDisconnect:
            pass
    return received


def of_type(messages, kind):
    return [m for m in messages if m["type"] == kind]


# Pages and config


def test_page_is_served():
    response = http.get("/")
    assert response.status_code == 200
    assert "Gemini Live Studio" in response.text


def test_config_reports_model_and_key(install, monkeypatch):
    install()
    assert http.get("/api/config").json() == {
        "model": studio.MODEL.removeprefix("models/"),
        "hasKey": True,
    }
    monkeypatch.setattr(studio, "client", None)
    assert http.get("/api/config").json()["hasKey"] is False


# Transcription


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.setattr(studio, "client", None)
    messages = run_session(stop=False)
    assert [m["type"] for m in messages] == ["error"]
    assert "GEMINI_API_KEY" in messages[0]["message"]


def test_interim_and_final_transcripts_are_forwarded_in_order(install):
    install(
        transcribe=FakeSession(
            [
                message(interim="Hello"),
                message(interim="Hello, this is"),
                message(final="Hello, this is a test."),
            ]
        )
    )
    messages = run_session()
    assert messages[0] == {"type": "ready", "model": studio.MODEL}
    transcripts = [m for m in messages if m["type"] in ("interim", "final")]
    assert transcripts == [
        {"type": "interim", "text": "Hello"},
        {"type": "interim", "text": "Hello, this is"},
        {"type": "final", "text": "Hello, this is a test."},
    ]


def test_audio_reaches_both_sessions_with_the_page_sample_rate(install):
    fake = install()
    chunks = [b"\x01\x00" * 2400, b"\x02\x00" * 2400]
    run_session(options={"sampleRate": 48000}, audio=chunks)
    for session in (fake.transcribe, fake.translate):
        assert [blob.data for blob in session.audio] == chunks
        assert {blob.mime_type for blob in session.audio} == {"audio/pcm;rate=48000"}


def test_stop_ends_the_audio_stream_to_flush_the_last_transcript(install):
    fake = install()
    run_session()
    assert fake.transcribe.sent[-1] == {"audio_stream_end": True}


def test_setup_options_are_passed_to_the_session(install):
    fake = install()
    run_session(options={"vocabulary": ["thorwebdev"], "languages": ["en-US", "fr-CA"], "mode": "SMART"})
    model, config = next(c for c in fake.connected if c[0] == studio.MODEL)
    assert config.input_audio_transcription.custom_vocabulary == ["thorwebdev"]
    assert config.input_audio_transcription.language_codes == ["en-US", "fr-CA"]
    assert config.input_audio_transcription.mode == "SMART"


def test_session_failure_is_reported(install):
    install(transcribe=FakeSession([RuntimeError("model is not found")]))
    messages = run_session(stop=False)
    assert of_type(messages, "error") == [{"type": "error", "message": "model is not found"}]
    assert not of_type(messages, "renew")


def test_session_time_limit_asks_the_page_to_reconnect(install):
    install(
        transcribe=FakeSession(
            [message(final="Before the limit."), message(go_away=object()), RuntimeError("closed")]
        )
    )
    messages = run_session(stop=False)
    assert of_type(messages, "renew")
    assert not of_type(messages, "error")
    assert of_type(messages, "final") == [{"type": "final", "text": "Before the limit."}]


def test_other_sites_cannot_open_a_session(install):
    install()
    with pytest.raises(WebSocketDisconnect) as closed:
        run_session(headers={"origin": "https://evil.example"})
    assert closed.value.code == 1008


# Live translation


def test_non_english_speech_is_translated_with_its_language(install):
    install(
        translate=FakeSession(
            [
                message(source="Bonjour à tous.", language="fr", output="Hello everyone."),
                message(source=" Samedi, je", language="fr"),
                message(output=" On Saturday, I'm going"),
            ]
        )
    )
    messages = run_session()
    assert {"type": "translator", "active": True} in messages
    assert of_type(messages, "translation") == [
        {"type": "translation", "text": "Hello everyone.", "language": "fr"},
        {"type": "translation", "text": " On Saturday, I'm going", "language": "fr"},
    ]


def test_english_speech_produces_no_translation(install):
    install(
        translate=FakeSession(
            [
                # The usual case: the model stays silent for English.
                message(source=" And now I am speaking", language="en"),
                message(output=None, language="en"),
                # The case from a mixed-language room: it repeats the English back.
                message(source=" So for example if I speak German", language="en"),
                message(output=" So, for example, if I speak German,"),
            ]
        )
    )
    assert of_type(run_session(), "translation") == []


def test_translation_resumes_after_english(install):
    install(
        translate=FakeSession(
            [
                message(source=" I will call you tomorrow", language="en"),
                message(output=" I will call you tomorrow"),
                message(source=" Guten Tag, wie geht es Ihnen?", language="de"),
                message(output=" Good day, how are you?"),
            ]
        )
    )
    assert of_type(run_session(), "translation") == [
        {"type": "translation", "text": " Good day, how are you?", "language": "de"}
    ]


def test_translation_failure_does_not_stop_transcription(install):
    install(
        transcribe=FakeSession([message(final="Still transcribing.")]),
        translate=RuntimeError("translate model unavailable"),
    )
    messages = run_session()
    assert {"type": "translator", "active": False} in messages
    assert of_type(messages, "final") == [{"type": "final", "text": "Still transcribing."}]
    assert not of_type(messages, "error")


# Text translation fallback


def test_translate_endpoint_wraps_the_transcript(install):
    result = studio.Translation(is_english=False, language="French", translation="Hello everyone.")
    fake = install(generate=result)
    response = http.post("/api/translate", json={"text": "  Bonjour à tous.  "})
    assert response.json() == result.model_dump()
    assert fake.generate_calls[0]["contents"] == "<transcript>Bonjour à tous.</transcript>"
    assert fake.generate_calls[0]["model"] == studio.TRANSLATE_MODEL


def test_translate_endpoint_skips_the_model_for_empty_text(install):
    fake = install()
    response = http.post("/api/translate", json={"text": "   "})
    assert response.json() == {"is_english": True, "language": "", "translation": ""}
    assert fake.generate_calls == []


def test_translate_endpoint_caps_long_text(install):
    fake = install(generate=studio.Translation(is_english=True, language="English", translation=""))
    http.post("/api/translate", json={"text": "a" * 20000})
    assert len(fake.generate_calls[0]["contents"]) == 8000 + len("<transcript></transcript>")


def test_translate_endpoint_passes_on_quota_errors(install):
    quota = genai_errors.APIError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
    install(generate=quota)
    assert http.post("/api/translate", json={"text": "Bonjour"}).status_code == 429


def test_translate_endpoint_rejects_other_sites_and_missing_key(install, monkeypatch):
    install()
    blocked = http.post("/api/translate", json={"text": "Bonjour"}, headers={"origin": "https://evil.example"})
    assert blocked.status_code == 403
    monkeypatch.setattr(studio, "client", None)
    assert http.post("/api/translate", json={"text": "Bonjour"}).status_code == 503


# Glossary vocabulary


def test_glossary_returns_terms_and_aliases_once_each(monkeypatch):
    async def rows():
        return [
            {"term": "QuickBooks", "aliases": ["QuickBooks", "QB"]},
            {"term": "DEXT", "aliases": ["DEXT", "Dext", " "]},
            {"term": "Chico", "aliases": None},
        ]

    monkeypatch.setattr(studio, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(studio, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(studio, "fetch_glossary_rows", rows)
    assert http.get("/api/glossary").json() == {
        "scope": studio.GLOSSARY_SCOPE,
        "terms": ["QuickBooks", "QB", "DEXT", "Chico"],
    }


def test_glossary_reports_when_it_is_not_configured_or_unreachable(monkeypatch):
    monkeypatch.setattr(studio, "SUPABASE_KEY", None)
    assert http.get("/api/glossary").status_code == 503

    async def unreachable():
        raise studio.httpx.ConnectError("no route")

    monkeypatch.setattr(studio, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(studio, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(studio, "fetch_glossary_rows", unreachable)
    assert http.get("/api/glossary").status_code == 502


def test_glossary_rejects_other_sites(monkeypatch):
    monkeypatch.setattr(studio, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(studio, "SUPABASE_KEY", "test-key")
    assert http.get("/api/glossary", headers={"origin": "https://evil.example"}).status_code == 403
