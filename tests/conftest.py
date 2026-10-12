"""Shared test helpers: a stand-in for the Gemini client, so no key or network is needed."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as studio  # noqa: E402


def message(interim=None, final=None, output=None, source=None, language=None, go_away=None):
    "A Live API server message carrying the given transcription texts"

    def transcription(text, language_code=None):
        if text is None and language_code is None:
            return None
        return SimpleNamespace(text=text, language_code=language_code)

    return SimpleNamespace(
        go_away=go_away,
        server_content=SimpleNamespace(
            interim_input_transcription=transcription(interim),
            # The transcription session's final and the translation session's
            # source transcript arrive in the same field.
            input_transcription=transcription(final if final is not None else source, language),
            output_transcription=transcription(output),
        ),
    )


class FakeSession:
    """Replays a script of messages; an exception in the script is raised in its place."""

    def __init__(self, script=()):
        self.script = list(script)
        self.sent = []

    async def send_realtime_input(self, **kwargs):
        self.sent.append(kwargs)

    async def receive(self):
        while self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            yield item
            await asyncio.sleep(0)
        # Script finished: stay connected and silent, like a quiet room.
        await asyncio.Event().wait()

    @property
    def audio(self):
        return [call["audio"] for call in self.sent if "audio" in call]


class FakeClient:
    def __init__(self, transcribe=None, translate=None, generate=None):
        self.transcribe = transcribe or FakeSession()
        # A session, or an exception to raise when connecting.
        self.translate = translate if translate is not None else FakeSession()
        self.generate = generate
        self.generate_calls = []
        self.aio = SimpleNamespace(
            live=SimpleNamespace(connect=self._connect),
            models=SimpleNamespace(generate_content=self._generate_content),
        )

    def _connect(self, model, config):
        session = self.transcribe if model == studio.MODEL else self.translate
        self.connected = getattr(self, "connected", []) + [(model, config)]

        class Connection:
            async def __aenter__(self):
                if isinstance(session, Exception):
                    raise session
                return session

            async def __aexit__(self, *exc):
                return False

        return Connection()

    async def _generate_content(self, **kwargs):
        self.generate_calls.append(kwargs)
        if isinstance(self.generate, Exception):
            raise self.generate
        return SimpleNamespace(parsed=self.generate)


@pytest.fixture
def install(monkeypatch):
    "Swap the app's Gemini client for a fake one and shorten the stop delay"
    monkeypatch.setattr(studio, "FLUSH_TIMEOUT", 0.3)

    def _install(**kwargs):
        fake = FakeClient(**kwargs)
        monkeypatch.setattr(studio, "client", fake)
        return fake

    return _install
