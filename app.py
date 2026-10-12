# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai",
#     "fastapi",
#     "uvicorn[standard]",
#     "python-dotenv",
# ]
# ///
"""
Gemini Live Studio - realtime speech transcription over the Gemini Live API.

Adapted from the Live API quickstart:
https://github.com/google-gemini/cookbook/blob/main/quickstarts/Get_started_LiveAPI.py

The browser captures the microphone and streams raw 16-bit PCM to this server
over a WebSocket; the server relays it to a Gemini Live session and sends the
interim / final transcriptions back.

## Setup

    export GEMINI_API_KEY=...   (or put it in a .env file next to this script)
    uv run app.py

Then open http://127.0.0.1:8000
"""

import os
import asyncio
import json
import traceback
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

SEND_SAMPLE_RATE = 16000

MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.5-transcribe-live")

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# Live transcription sessions are capped at 10 minutes; closures after this
# many seconds are treated as the cap and the browser is told to reconnect.
SESSION_RENEW_AFTER = 540
# How long to wait for the last final transcript after the user hits stop.
FLUSH_TIMEOUT = 2.5

API_KEY = os.environ.get("GEMINI_API_KEY")

client = (
    genai.Client(
        http_options={"api_version": "v1beta"},
        api_key=API_KEY,
    )
    if API_KEY
    else None
)


def build_config(options):
    vocabulary = [v.strip() for v in options.get("vocabulary", []) if v.strip()]
    language = (options.get("language") or "").strip()
    mode = "SMART" if options.get("mode") == "SMART" else None

    return types.LiveConnectConfig(
        response_modalities=[
            "TEXT",
        ],
        input_audio_transcription=types.AudioTranscriptionConfig(
            # An empty list means automatic language detection
            language_codes=[language] if language else [],
            custom_vocabulary=vocabulary[:1000] or None,
            mode=mode,
        ),
    )


class AudioLoop:
    def __init__(self, ws, options):
        self.ws = ws
        self.config = build_config(options)
        self.sample_rate = int(options.get("sampleRate") or SEND_SAMPLE_RATE)

        self.out_queue = None

        self.session = None

        self.client_gone = False
        self.stopping = False
        self.going_away = False
        self.final_after_stop = False
        self.last_message_at = 0.0

    async def notify(self, kind, **payload):
        try:
            await self.ws.send_json({"type": kind, **payload})
        except Exception:
            self.client_gone = True

    async def listen_audio(self):
        "Reads pcm chunks (and the stop message) from the browser"
        while True:
            msg = await self.ws.receive()
            if msg["type"] == "websocket.disconnect":
                self.client_gone = True
                return
            if data := msg.get("bytes"):
                await self.out_queue.put(data)
            elif text := msg.get("text"):
                if json.loads(text).get("type") == "stop":
                    self.stopping = True
                    await self.out_queue.put(None)
                    return

    async def send_realtime(self):
        mime_type = f"audio/pcm;rate={self.sample_rate}"
        while True:
            data = await self.out_queue.get()
            if data is None:
                # Finalizes the current turn right away instead of waiting
                # for the server-side silence timeout.
                await self.session.send_realtime_input(audio_stream_end=True)
                continue
            await self.session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=mime_type)
            )

    async def receive_transcripts(self):
        "Background task to read from the Gemini websocket and forward transcripts"
        loop = asyncio.get_running_loop()
        while True:
            turn = self.session.receive()
            async for response in turn:
                self.last_message_at = loop.time()
                if response.go_away is not None:
                    self.going_away = True

                server_content = response.server_content
                if not server_content:
                    continue

                # Speculative partial hypothesis, replaced as the speaker talks
                interim = server_content.interim_input_transcription
                if interim and interim.text:
                    await self.notify("interim", text=interim.text)

                # Authoritative transcript of a finished speech segment
                final = server_content.input_transcription
                if final and final.text:
                    if self.stopping:
                        self.final_after_stop = True
                    await self.notify("final", text=final.text)

    async def wait_for_flush(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + FLUSH_TIMEOUT
        while loop.time() < deadline:
            await asyncio.sleep(0.1)
            if self.final_after_stop and loop.time() - self.last_message_at > 0.5:
                break

    async def run(self):
        if client is None:
            await self.notify(
                "error",
                message="GEMINI_API_KEY is not set. Add it to .env and restart the server.",
            )
            return

        loop = asyncio.get_running_loop()
        started_at = loop.time()
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=self.config) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.out_queue = asyncio.Queue(maxsize=5)

                await self.notify("ready", model=MODEL)

                listen_audio_task = tg.create_task(self.listen_audio())
                background = [
                    tg.create_task(self.send_realtime()),
                    tg.create_task(self.receive_transcripts()),
                ]

                await listen_audio_task
                if not self.client_gone:
                    await self.wait_for_flush()
                for task in background:
                    task.cancel()

        except* Exception as EG:
            if self.client_gone or self.stopping:
                pass
            elif self.going_away or loop.time() - started_at > SESSION_RENEW_AFTER:
                await self.notify("renew")
            else:
                traceback.print_exception(EG)
                error = EG.exceptions[0]
                while isinstance(error, BaseExceptionGroup):
                    error = error.exceptions[0]
                await self.notify("error", message=str(error) or type(error).__name__)


app = FastAPI()


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/config")
async def get_config():
    return {"model": MODEL.removeprefix("models/"), "hasKey": client is not None}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # The session spends the server's API key, so only this app's own page may open it.
    origin = ws.headers.get("origin")
    if origin and urlparse(origin).netloc != ws.headers.get("host"):
        await ws.close(code=1008)
        return

    await ws.accept()
    try:
        options = await ws.receive_json()
    except Exception:
        return

    await AudioLoop(ws, options).run()
    try:
        await ws.close()
    except Exception:
        pass


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
