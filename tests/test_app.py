import numpy as np

from live_translator import AppConfig, AudioMath, LANGUAGES


def test_language_profiles_have_translation_and_voice_data():
    assert LANGUAGES
    assert all(profile.translate_code for profile in LANGUAGES.values())
    assert all(profile.voices for profile in LANGUAGES.values())


def test_to_mono_averages_channels():
    samples = np.array([1.0, 3.0, 5.0, 7.0], dtype=np.float32)

    result = AudioMath.to_mono(samples, channels=2)

    np.testing.assert_allclose(result, [2.0, 6.0])


def test_resample_returns_requested_length():
    samples = np.linspace(-1.0, 1.0, 480, dtype=np.float32)

    result = AudioMath.resample(samples, src_rate=48000, dst_rate=16000)

    assert len(result) == 160


def test_config_profile_falls_back_to_english():
    assert AppConfig().profile("unknown").label == LANGUAGES["en"].label


def test_srt_timestamps_are_relative_and_do_not_overlap():
    from live_translator.transcript import Transcript, srt_timestamp

    assert srt_timestamp(3725.5) == "01:02:05,500"

    transcript = Transcript()
    transcript.add(1000.0, 1003.2, "hello", "merhaba")
    transcript.add(1003.0, 1004.0, "bye", "hoşça kal")

    assert transcript.to_srt() == (
        "1\n00:00:00,000 --> 00:00:03,000\nmerhaba\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nhoşça kal\n"
    )
