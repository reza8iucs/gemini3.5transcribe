"""Rules that need no server: the English-echo filter, session config, origin check."""

import pytest

import app as studio

ENGLISH_HEARD = [
    "Can you send the updated invoice to the client before lunch? "
    "I will check the numbers again tonight and call you tomorrow morning."
]


@pytest.mark.parametrize(
    "output, own_input",
    [
        # Real translations that share common words with English spoken nearby.
        # An earlier filter dropped these and left gaps in the translation.
        (" to show you how the", [" vous montrer comment"]),
        (" doctor tomorrow morning.", [" Arzt vereinbaren"]),
        (" are you? I", [" wie geht es Ihnen? Ich"]),
        (" Hello everyone.", ["Bonjour à tous."]),
    ],
)
def test_real_translation_is_kept(output, own_input):
    assert not studio.is_echo(output, own_input, ENGLISH_HEARD, tagged_english=False)


@pytest.mark.parametrize(
    "output, own_input, transcript, tagged_english",
    [
        # English repeated back while the session heard English.
        (" So, for example, if I speak German, um,", [" So for example if I", " speak German um"], [], True),
        (" hints. recognize all again,", [" hints", " recognize all the", " again"], [], True),
        (" Hello", [" Hello"], [], True),
        # Same word sequence as the transcript, even without the English tag.
        (" call you tomorrow morning", [], ENGLISH_HEARD, False),
        # Nothing but punctuation.
        (" ...", [], [], False),
    ],
)
def test_repeated_english_is_dropped(output, own_input, transcript, tagged_english):
    assert studio.is_echo(output, own_input, transcript, tagged_english)


def test_english_tag_alone_does_not_drop_a_translation():
    # Language detection is unreliable when languages switch quickly.
    assert not studio.is_echo(" I would like to book a table", [" je voudrais réserver"], [], True)


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
