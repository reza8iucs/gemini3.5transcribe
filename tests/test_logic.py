"""Rules that need no server: the English filters, session config, origin check."""

import pytest

import app as studio

@pytest.mark.parametrize(
    "output, heard",
    [
        # Real translations that share common words with English.
        # An earlier filter dropped these and left gaps in the translation.
        (" to show you how the", [" vous montrer comment"]),
        (" doctor tomorrow morning.", [" Arzt vereinbaren"]),
        (" are you? I", [" wie geht es Ihnen? Ich"]),
        (" Hello everyone.", ["Bonjour à tous."]),
    ],
)
def test_real_translation_is_kept(output, heard):
    assert not studio.is_echo(output, heard, tagged_english=False)


@pytest.mark.parametrize(
    "output, heard, tagged_english",
    [
        # English repeated back while the session heard English.
        (" So, for example, if I speak German, um,", [" So for example if I", " speak German um"], True),
        (" hints. recognize all again,", [" hints", " recognize all the", " again"], True),
        (" Hello", [" Hello"], True),
        # Same word sequence as what was heard, even without the English tag.
        (" it's because they", [" it's because they"], False),
        # Nothing but punctuation.
        (" ...", [], False),
    ],
)
def test_repeated_english_is_dropped(output, heard, tagged_english):
    assert studio.is_echo(output, heard, tagged_english)


def test_english_tag_alone_does_not_drop_a_translation():
    # Language detection is unreliable when languages switch quickly.
    assert not studio.is_echo(" I would like to book a table", [" je voudrais réserver"], True)


# Which language the transcript says is being spoken


def spoken_after(*interims):
    spoken = studio.SpokenLanguage()
    for second, text in enumerate(interims):
        spoken.heard(second, interim=text)
    return spoken, len(interims)


@pytest.mark.parametrize(
    "interim",
    [
        "So the column CE, it's agreement on the current invoices",
        "Can you send the updated invoice to the client before lunch",
        # English after another language in the same segment.
        "la semaine d'avant, la semaine d'après. OK. So the column CE it's",
    ],
)
def test_translation_is_dropped_while_the_transcript_is_english(interim):
    spoken, now = spoken_after(interim)
    # Reworded, so it does not match what was said word for word.
    assert spoken.is_english(" So when we say", now)


@pytest.mark.parametrize(
    "interim",
    [
        "Ça dépend, il y en a qui le paient la semaine d'avant",
        "Guten Tag, wie geht es Ihnen? Ich möchte einen Termin",
        "Buenos días, quiero reservar una mesa para mañana",
        # Another language after English in the same segment.
        "Can you repeat that? Their agreement is. Dans quel cas c'est eux",
    ],
)
def test_translation_is_kept_while_the_transcript_is_another_language(interim):
    spoken, now = spoken_after(interim)
    assert not spoken.is_english(" It depends, some of them", now)


def test_english_stays_until_the_transcript_clearly_changes():
    # A stretch of English without everyday words, then a single unclear word.
    spoken, now = spoken_after("So if we had problems with them", "agreement under current current invoices", "OK.")
    assert spoken.is_english(" current invoices", now)
    spoken.heard(now, interim="OK, mais c'est pas des COD nécessairement")
    assert not spoken.is_english(" Okay, but it's not", now + 1)


def test_english_said_back_is_dropped_even_without_everyday_words():
    spoken, now = spoken_after("Bonjour à tous, voici le rapport", "Bonjour à tous. Chico franchise royalties invoice")
    assert spoken.is_english(" franchise royalties invoice", now)


def test_a_silent_transcript_has_no_say():
    spoken, now = spoken_after("So the column CE, it's agreement on the current invoices")
    # The transcription session missed the next speaker altogether.
    assert not spoken.is_english(" It depends, some of them", now + 10)
    # And the speaker after the silence is not assumed to be English.
    spoken.heard(now + 20, interim="Bonjour")
    assert not spoken.is_english(" Hello", now + 20)


def test_default_config_detects_language_and_returns_text():
    config = studio.build_config({})
    transcription = config.input_audio_transcription
    assert config.response_modalities == ["TEXT"]
    assert transcription.language_codes == []
    assert transcription.custom_vocabulary is None
    assert transcription.mode is None


def test_config_uses_setup_options():
    config = studio.build_config(
        {"vocabulary": [" Thorsten ", "", "thorwebdev"], "languages": [" fr-CA ", "", "en-US"], "mode": "SMART"}
    )
    transcription = config.input_audio_transcription
    assert transcription.custom_vocabulary == ["Thorsten", "thorwebdev"]
    assert transcription.language_codes == ["fr-CA", "en-US"]
    assert transcription.mode == "SMART"


def test_config_ignores_unknown_mode_and_caps_vocabulary():
    config = studio.build_config({"mode": "SHOUTING", "vocabulary": [f"term{i}" for i in range(1500)]})
    assert config.input_audio_transcription.mode is None
    assert len(config.input_audio_transcription.custom_vocabulary) == 1000


def test_live_translation_targets_english_and_stays_silent_for_english():
    translation = studio.LIVE_TRANSLATE_CONFIG.translation_config
    assert translation.target_language_code == "en"
    assert translation.echo_target_language is False
    assert studio.LIVE_TRANSLATE_CONFIG.output_audio_transcription is not None


@pytest.mark.parametrize(
    "headers, allowed",
    [
        ({"host": "127.0.0.1:8000"}, True),
        ({"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:8000"}, True),
        ({"host": "127.0.0.1:8000", "origin": "https://evil.example"}, False),
        ({"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:9999"}, False),
    ],
)
def test_same_origin(headers, allowed):
    assert studio.same_origin(headers) is allowed
