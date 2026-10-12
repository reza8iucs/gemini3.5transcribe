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
- Live English translation of non-English speech in a side panel
  (`gemini-3.5-live-translate-preview`), silent while English is spoken
- Custom vocabulary, language hint, verbatim or smart mode (Setup)
- Search, copy, and export to TXT / MD / JSON
- Automatic reconnect at the 10-minute session limit

See `.env.example` for the model and port overrides.

## Tests

```bash
uv run --with-requirements requirements-dev.txt pytest
```

The tests replace the Gemini sessions with scripted fakes, so they need no API
key and use no quota. They also run on GitHub for every push.
