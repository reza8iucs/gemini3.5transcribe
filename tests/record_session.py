"""Records what both Gemini Live sessions say about an audio clip, for use as a test.

Plays a WAV file to the transcription and translation sessions at normal speed
and writes down every transcript and translation they send back, with timings.
tests/test_recordings.py replays the files in tests/recordings/ through the
translation filter, so a clip that once went wrong keeps being checked.

    uv run --with-requirements requirements-dev.txt tests/record_session.py clip.wav tests/recordings/name.json

The WAV must be 16-bit mono. On a Mac, any recording converts with:

    afconvert -f WAVE -d LEI16@16000 -c 1 recording.mp4 clip.wav

Needs GEMINI_API_KEY and uses the same models and settings as the app.
"""

import asyncio
import json
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as studio  # noqa: E402
from google.genai import types  # noqa: E402

CHUNK_SECONDS = 0.1
# Silence sent after the clip so the sessions finish what they were saying.
TAIL_SECONDS = 10


async def play(sessions, frames, rate, started_at):
    size = int(rate * CHUNK_SECONDS) * 2
    chunks = [frames[i : i + size] for i in range(0, len(frames), size)]
    chunks += [b"\x00" * size] * int(TAIL_SECONDS / CHUNK_SECONDS)
    for number, chunk in enumerate(chunks):
        await asyncio.sleep(max(0, started_at + number * CHUNK_SECONDS - time.monotonic()))
        for session in sessions:
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={rate}")
            )


async def listen(session, events, started_at, translating):
    while True:
        async for response in session.receive():
            content = response.server_content
            if not content:
                continue
            at = round(time.monotonic() - started_at, 2)
            heard, said = content.input_transcription, content.output_transcription
            if translating:
                if heard and (heard.text or heard.language_code):
                    events.append([at, "source", heard.text, heard.language_code])
                if said and said.text:
                    events.append([at, "output", said.text])
            elif heard and heard.text:
                events.append([at, "final", heard.text])
            elif content.interim_input_transcription and content.interim_input_transcription.text:
                events.append([at, "interim", content.interim_input_transcription.text])


async def record(frames, rate, languages):
    events = []
    config = studio.build_config({"languages": languages})
    connect = studio.client.aio.live.connect
    async with (
        connect(model=studio.MODEL, config=config) as transcribe,
        connect(model=studio.LIVE_TRANSLATE_MODEL, config=studio.LIVE_TRANSLATE_CONFIG) as translate,
    ):
        started_at = time.monotonic()
        listeners = [
            asyncio.create_task(listen(transcribe, events, started_at, translating=False)),
            asyncio.create_task(listen(translate, events, started_at, translating=True)),
        ]
        await play([transcribe, translate], frames, rate, started_at)
        for listener in listeners:
            listener.cancel()
    return events


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    if studio.client is None:
        sys.exit("GEMINI_API_KEY is not set.")
    with wave.open(sys.argv[1]) as clip:
        if clip.getsampwidth() != 2 or clip.getnchannels() != 1:
            sys.exit("The WAV must be 16-bit mono.")
        rate, frames = clip.getframerate(), clip.readframes(clip.getnframes())
    # The page's default language hints.
    events = asyncio.run(record(frames, rate, ["en-US", "en-CA", "fr-CA"]))
    lines = ",\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    Path(sys.argv[2]).write_text(f'{{"about": "", "expect": {{}}, "events": [\n{lines}\n]}}\n')
    print(f"{len(events)} events written to {sys.argv[2]}. Fill in 'about' and 'expect'.")


if __name__ == "__main__":
    main()
