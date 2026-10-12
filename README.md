# Gemini Live Studio

Realtime speech transcription in the browser, using the Gemini Live API
(`gemini-3.5-transcribe-live`). The browser streams microphone audio to a small
Python server, which relays it to a Gemini Live session and sends interim and
final transcripts back.

## Run

```bash
cp .env.example .env   # then add your GEMINI_API_KEY
uv run app.py
```

Open http://127.0.0.1:8000 and press **Start Session**.

## Features

- Live interim text with finalized segments
- Custom vocabulary, language hint, verbatim or smart mode (Setup)
- Search, copy, and export to TXT / MD / JSON
- Automatic reconnect at the 10-minute session limit

Set `GEMINI_MODEL` or `PORT` in `.env` to override the defaults.
