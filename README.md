# Gemini Live Studio

Realtime speech transcription in the browser, with live English translation of
anything spoken in another language. Built on the Gemini Live API.

You speak; the transcript appears as you talk and settles into finished
segments when you pause. If someone speaks French, Persian, German or another
language, an English translation streams into a side panel at the same time.

## How it works

```
Browser (microphone, UI)  ──audio──▶  Python server  ──audio──▶  Gemini Live
                          ◀──text───                 ◀──text───
```

- The **browser** captures the microphone and sends raw 16 kHz audio to the
  server over a WebSocket.
- The **server** (`app.py`) relays that audio to two Gemini Live sessions at
  once: `gemini-3.5-transcribe-live` for the transcript and
  `gemini-3.5-live-translate-preview` for the English translation.
- Your API keys stay on the server. The browser never sees them.

## Requirements

- [uv](https://docs.astral.sh/uv/) (it installs Python and the dependencies for you)
- A [Gemini API key](https://aistudio.google.com/apikey)
- A current desktop browser and a microphone
- Optional: a Supabase project holding a glossary table (see
  [Glossary from Supabase](#glossary-from-supabase))

## Quick start

```bash
git clone https://github.com/reza8iucs/gemini3.5transcribe.git
cd gemini3.5transcribe
cp .env.example .env   # then add your GEMINI_API_KEY
uv run app.py
```

Open http://127.0.0.1:8000, press **Start Session** and allow microphone
access. Press **Stop Session** when you are done. Stop the server with Ctrl+C.

## Using the app

| Part of the screen | What it does |
|---|---|
| Transcription Stream | The live transcript. The green-edged block is the interim text, still changing as you speak; cards marked **Final** are finished segments. |
| English Translation | Appears on the right when a language other than English is spoken. Stays hidden while everything is English. |
| Vocab chip / Setup | Opens Setup: custom vocabulary, language hints, transcription mode and microphone. Changes apply to the next session. |
| Slider in the header | Microphone input gain. |
| Microphone button | Mutes and unmutes without ending the session. |
| Search | Filters both panels and highlights matches. |
| Copy / Clear | Copies or clears the whole transcript. Each card also has its own copy button. |
| Export | Downloads the transcript and translations as TXT, Markdown or JSON. |

## Features

### Live transcription

- Interim text within a fraction of a second, replaced by a final transcript
  for each segment when the speaker pauses.
- **Verbatim** mode keeps exactly what was said. **Smart** mode removes filler
  words and tidies formatting.
- Sessions are limited to 10 minutes by the API. The app reconnects on its own
  and keeps the microphone running, so long recordings carry on.

### Live English translation

- Translates from the audio as the person speaks, not after they finish.
- Only non-English speech is translated. When English and another language are
  spoken at the same time, the panel follows the non-English speaker and goes
  quiet when they stop.
- Translation stops on its own when the speaker goes back to English. The
  translation model sometimes carries on through English, so the server checks
  each piece against the transcript and drops it while English is being spoken.
- Each translation card is labelled with the detected language, for example
  "French → English".
- If the translation session cannot start, transcription carries on without it.

### Custom vocabulary

Names, brands and jargon that speech recognition tends to get wrong can be
listed in **Setup → Custom vocabulary**. The list is sent to the transcription
model to bias it toward those terms.

Vocabulary terms are also **highlighted in amber** wherever they appear: in
the live interim text, in finished segments and in the translation panel.
Matching ignores capitals and only matches whole words.

### Glossary from Supabase

Instead of typing the vocabulary by hand, the app can load it from a glossary
table in Supabase.

- The glossary is fetched **once a day**, the first time the page is opened
  that day, and becomes the default vocabulary. It is not fetched again on
  later page loads or session starts that day. "Once a day" is tracked per
  browser.
- Each row contributes its term and all of its aliases (for example
  "QuickBooks" and "QB").
- Terms you add by hand in Setup are kept, listed after the glossary terms.
- If the glossary cannot be reached, the app keeps the vocabulary it already
  has and tries again at the next session start.

The table needs these columns:

| Column | Type | Used for |
|---|---|---|
| `term` | text | The main spelling of the term. |
| `aliases` | text[] | Other spellings or abbreviations. May be empty. |
| `scope` | text[] | Which glossary the row belongs to. Only rows whose scope contains `GLOSSARY_SCOPE` are loaded. |

To turn it on, add `SUPABASE_URL` and `SUPABASE_KEY` to `.env`. The key must
be allowed to read the table. If row-level security only lets signed-in users
read it, that means the project's secret key, which can read and write
everything in the project. Keep it in `.env` only.

Without those two settings the app works normally and the vocabulary is
whatever you enter in Setup.

### Language hints

**Setup → Language hints** lists the languages you expect to hear, as BCP-47
codes. They are sent to the transcription model to bias recognition toward
those languages.

- Default: `en-US`, `en-CA`, `fr-CA`.
- Add codes with the box and **Add** button; remove one by clicking its chip.
- Hints are a nudge, not a filter. Other languages are still transcribed.
- With no hints, the language is detected automatically.
- Hints apply to the transcript only. The translation panel detects languages
  on its own.

## Configuration

All settings live in `.env` next to `app.py`. Only `GEMINI_API_KEY` is required.

| Setting | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Your Gemini API key. |
| `GEMINI_MODEL` | `models/gemini-3.5-transcribe-live` | Transcription model. |
| `GEMINI_LIVE_TRANSLATE_MODEL` | `models/gemini-3.5-live-translate-preview` | Live translation model. |
| `GEMINI_TRANSLATE_MODEL` | `models/gemini-3.5-flash-lite` | Text model used for translation only if the live translation session is unavailable. |
| `SUPABASE_URL` | none | Address of the Supabase project holding the glossary. |
| `SUPABASE_KEY` | none | Key allowed to read the glossary table. |
| `GLOSSARY_TABLE` | `pv_glossary` | Glossary table name. |
| `GLOSSARY_SCOPE` | `Chico` | Which rows of the glossary to load. |
| `HOST` | `127.0.0.1` | Address the server listens on. |
| `PORT` | `8000` | Port the server listens on. |

Vocabulary, language hints, mode and microphone are chosen in Setup and
remembered by the browser.

## Privacy and security

- **Audio leaves your machine.** Everything the microphone picks up during a
  session is sent to Google's Gemini API for transcription and translation.
  Tell the people you are recording.
- **Transcripts are not stored.** They exist only in the open browser tab and
  are gone when you reload or clear, unless you export them.
- **Keys stay local.** `.env` is ignored by git, and the keys are used only by
  the server.
- **Local use only.** The server listens on `127.0.0.1` and refuses requests
  from other websites, so another page cannot use your keys. It has no login,
  so do not expose it to a network or the internet as it is.

## Limitations

- **Quotas.** A free-tier Gemini key has per-minute and daily limits. Long or
  frequent sessions can run into them.
- **No speaker labels.** The Live API does not identify who is speaking.
- **Translation cards and transcript cards are separate.** The translation
  runs a moment behind the transcript, so cards on the right follow the
  translation's own pauses and do not line up one-to-one with the left.
- **Mixed languages are hard.** With several languages in the room the models
  can mislabel a language or miss part of an overlapping sentence.
- **Preview models.** The translation model is a preview and may change or be
  withdrawn. If a model name stops working, set the matching `GEMINI_*`
  setting to the current one.

## Troubleshooting

| Problem | Fix |
|---|---|
| `address already in use` when starting | Another copy of the app is still running. Press Ctrl+C in its terminal, or set a different `PORT`. |
| "GEMINI_API_KEY is not set" | Add the key to `.env` and restart the server. |
| A model is "not found" | Your key does not have that model. Set `GEMINI_MODEL` or `GEMINI_LIVE_TRANSLATE_MODEL` to one it does. |
| "Could not open the microphone" | Allow microphone access for the page in the browser, and check the device chosen in Setup. |
| Vocabulary is empty with Supabase configured | Check `SUPABASE_URL` and `SUPABASE_KEY`, that the key may read the table, and that rows exist for `GLOSSARY_SCOPE`. Restart the server after editing `.env`. |
| A change to `.env` or `app.py` has no effect | Restart the server. Changes to the page only need a reload. |

## Project layout

| Path | Contents |
|---|---|
| `app.py` | The server: audio relay, translation filter, glossary and translation endpoints. |
| `static/index.html` | The whole page: layout, styling and browser logic. |
| `tests/` | The test suite, with recorded sessions in `tests/recordings/`. |
| `.env.example` | Template for `.env`. |
| `requirements-dev.txt` | Dependencies for running the tests. |

## Tests

```bash
uv run --with-requirements requirements-dev.txt pytest
```

The tests replace the Gemini sessions with scripted fakes and recordings of
real sessions, so they need no API key and use no quota. They also run on
GitHub for every push.

### What is covered

**Logic rules** (`tests/test_logic.py`) — small rules checked on their own:

| Area | What the tests check |
|---|---|
| English-echo filter | A real translation is kept even when it shares common words ("to", "you", "tomorrow") with English spoken nearby. |
| English-echo filter | English that the translation model repeats back is dropped, including the phrases from a real mixed-language session. |
| English-echo filter | The model's "this was English" tag is not enough on its own to drop a translation, because that tag is unreliable when languages switch quickly. |
| Spoken language | While the transcript reads as English, translation is dropped even when the model rewords what was said; French, German and Spanish transcripts let it through, including right after English in the same sentence. |
| Spoken language | English stays in force through a stretch with few everyday words, and ends when the transcript clearly changes language. |
| Spoken language | A transcript that has gone silent has no say, and the next speaker is not assumed to be English. |
| Session setup | With no options, language is detected automatically and text is returned. |
| Session setup | Vocabulary, language hints and Smart mode from Setup are applied; blank terms are removed, unknown modes ignored, vocabulary capped at 1,000 terms. |
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
| Live translation | English that the model reports as French and rewords is dropped when the transcript shows English. |
| Live translation | Translation resumes when a non-English speaker follows an English one. |
| Live translation | If the translation session fails, transcription carries on. |
| Glossary vocabulary | Each term and its aliases are returned once; a missing configuration or unreachable glossary is reported; other sites are refused. |
| Text translation fallback | The transcript is sent to the model, empty text skips the model, long text is capped, quota errors are passed on, and other sites or a missing key are refused. |

**Recorded sessions** (`tests/test_recordings.py`) — real sessions replayed through the translation filter:

Each file in `tests/recordings/` holds everything the two Gemini sessions sent
back for a real clip, with timings, and marks where English and where another
language was spoken. The five recordings there are of the same one-minute
meeting clip (English, French, English); the model behaved differently each
time, which is why there are several.

| Area | What the tests check |
|---|---|
| English stretches | Nothing is shown as a translation while English is spoken, whether the model stays quiet, repeats the English, tags it as French, or hears it as French and rewords it. |
| Other languages | Every piece of the French translation is shown, with no gaps. |

To turn another clip into a test, record it and then fill in `about` and
`expect` in the file it writes (this one does need the API key):

```bash
afconvert -f WAVE -d LEI16@16000 -c 1 recording.mp4 clip.wav
uv run --with-requirements requirements-dev.txt tests/record_session.py clip.wav tests/recordings/name.json
```

### What is not covered

- The page itself: how cards are grouped, search, copy and export, vocabulary
  highlighting, the language-hint editor, and the once-a-day timing of the
  glossary fetch.
- The real Gemini models and a real microphone. The fakes replay scripted
  messages, so a change in how the models behave will not be caught here.
