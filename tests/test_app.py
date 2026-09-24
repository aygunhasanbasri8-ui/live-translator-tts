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
