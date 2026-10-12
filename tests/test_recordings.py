"""Real sessions replayed through the translation filter.

Each file in tests/recordings/ holds what the two Gemini Live sessions sent
back for a real audio clip (see tests/record_session.py), and the stretches of
the clip where English or another language was spoken.
"""

import collections
import json
from pathlib import Path

import pytest

import app as studio

RECORDINGS = sorted((Path(__file__).parent / "recordings").glob("*.json"))


def translations(events):
    "Replays a recording as the server sees it; returns (time, text, shown) per translation chunk"
    spoken = studio.SpokenLanguage()
    heard = collections.deque(maxlen=6)
    language = None
    chunks = []
    for at, kind, text, *rest in events:
        if kind == "interim":
            spoken.heard(at, interim=text)
        elif kind == "final":
            spoken.heard(at, final=text)
        elif kind == "source":
            language = rest[0] or language
            if text:
                heard.append(text)
        else:
            english = spoken.is_english(text, at) or studio.is_echo(
                text, heard, (language or "").lower().startswith("en")
            )
            chunks.append((at, text, not english))
    return chunks


def within(chunks, spans):
    return [chunk for chunk in chunks if any(start <= chunk[0] <= end for start, end in spans)]


def test_there_are_recordings():
    assert RECORDINGS


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda path: path.stem)
def test_nothing_is_translated_while_english_is_spoken(path):
    recording = json.loads(path.read_text())
    chunks = within(translations(recording["events"]), recording["expect"]["english"])
    assert [text for _, text, shown in chunks if shown] == []


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda path: path.stem)
def test_other_languages_are_translated_without_gaps(path):
    recording = json.loads(path.read_text())
    chunks = within(translations(recording["events"]), recording["expect"]["other"])
    assert len(chunks) > 10
    assert [text for _, text, shown in chunks if not shown] == []
