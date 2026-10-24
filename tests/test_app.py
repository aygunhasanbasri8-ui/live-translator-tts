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


def test_google_continuous_response_joins_all_final_phrases():
    from live_translator.speech import parse_google_stt

    body = (
        '{"result":[]}\n'
        '{"result":[{"alternative":[{"transcript":"first part","confidence":0.9}],"final":true}],"result_index":0}\n'
        '{"result":[{"alternative":[{"transcript":" second part"}],"final":true}],"result_index":1}\n'
    )

    assert parse_google_stt(body) == "first part second part"
    assert parse_google_stt('{"result":[]}\n') == ""


def test_long_speech_is_split_at_the_quietest_point_not_mid_word():
    from live_translator.capture import SpeechSegmenter

    rate = 16000
    speech = np.full(rate * 7, 0.2, dtype=np.float32)
    gap_at = int(rate * 5.2)
    speech[gap_at:gap_at + int(rate * 0.1)] = 0.0   # sessizlik sayılmayacak kadar kısa bir duraklama
    finals = []
    segmenter = SpeechSegmenter(AppConfig(streaming_enabled=False), rate,
                                lambda chunks, duration, is_final, uid, ago: finals.append(duration))

    for start in range(0, speech.size, 1024):
        block = speech[start:start + 1024]
        segmenter.feed(block, 0.2, start / rate)

    assert len(finals) == 1
    assert 5.2 <= finals[0] <= 5.3
