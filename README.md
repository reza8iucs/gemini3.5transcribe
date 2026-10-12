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
- Custom vocabulary defaults to a Supabase glossary, fetched once a day when the page opens
  (needs `SUPABASE_URL` and `SUPABASE_KEY` in `.env`)
- Search, copy, and export to TXT / MD / JSON
- Automatic reconnect at the 10-minute session limit

See `.env.example` for the model and port overrides.

## Tests

```bash
uv run --with-requirements requirements-dev.txt pytest
```

The tests replace the Gemini sessions with scripted fakes, so they need no API
key and use no quota. They also run on GitHub for every push.

### What is covered

**Logic rules** (`tests/test_logic.py`) — small rules checked on their own:

| Area | What the tests check |
|---|---|
| English-echo filter | A real translation is kept even when it shares common words ("to", "you", "tomorrow") with English spoken nearby. |
| English-echo filter | English that the translation model repeats back is dropped, including the phrases from a real mixed-language session. |
| English-echo filter | The model's "this was English" tag is not enough on its own to drop a translation, because that tag is unreliable when languages switch quickly. |
| Session setup | With no options, language is detected automatically and text is returned. |
| Session setup | Vocabulary, language and Smart mode from Setup are applied; blank terms are removed, unknown modes ignored, vocabulary capped at 1,000 terms. |
| Translation setup | The live translation targets English and is configured to stay silent for English speech. |
| Origin check | Requests from the app's own page are allowed; other sites and other ports are refused. |

**Server behaviour** (`tests/test_server.py`) — the app run end to end against the fakes:

| Area | What the tests check |
|---|---|
| Pages | The page is served, and the config endpoint reports the model and whether a key is set. |
| Transcription | Interim and final transcripts reach the page in the order they were produced. |
| Transcription | Microphone audio is passed to both the transcription and translation sessions, at the sample rate the page reports. |
| Transcription | Stopping ends the audio stream so the last transcript is flushed. |
| Transcription | Setup options reach the transcription session. |
| Errors | A missing API key and a failed session are each reported to the page. |
| Session limit | When the 10-minute session limit is reached, the page is told to reconnect instead of being shown an error. |
| Security | Another website cannot open a session and spend the API key. |
| Live translation | Non-English speech is translated and labelled with its language. |
| Live translation | English speech produces no translation, both when the model stays silent and when it repeats the English back. |
| Live translation | Translation resumes when a non-English speaker follows an English one. |
| Live translation | If the translation session fails, transcription carries on. |
| Glossary vocabulary | Each term and its aliases are returned once; a missing configuration or unreachable glossary is reported; other sites are refused. |
| Text translation fallback | The transcript is sent to the model, empty text skips the model, long text is capped, quota errors are passed on, and other sites or a missing key are refused. |

### What is not covered

- The page itself: how cards are grouped, search, copy and export, and the
  once-a-day timing of the glossary fetch.
- The real Gemini models and a real microphone. The fakes replay scripted
  messages, so a change in how the models behave will not be caught here.
