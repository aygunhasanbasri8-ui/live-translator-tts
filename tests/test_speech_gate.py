import numpy as np

from live_translator.capture import SpeechSegmenter
from live_translator.config import AppConfig

RATE = 48000
BLOCK = 1024


def _speech(seconds, rnd):
    t = np.arange(int(RATE * seconds)) / RATE
    f0 = 140 + 30 * rnd.random()
    voiced = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    syllables = 0.55 + 0.45 * np.sin(2 * np.pi * 4.5 * t) ** 2   # ~4-5 hece/sn
    return (0.06 * voiced * syllables).astype(np.float32)


def _music(seconds):
    t = np.arange(int(RATE * seconds)) / RATE
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 277.2, 329.6, 440.0))
    return (0.012 * chord).astype(np.float32)


def _scene(sentences=6, with_music=True, seed=3):
    rnd = np.random.default_rng(seed)
    parts = [np.zeros(RATE // 2, np.float32)]
    for _ in range(sentences):
        parts.append(_speech(2.0 + rnd.random(), rnd))
        parts.append(np.zeros(int(RATE * 0.8), np.float32))
    audio = np.concatenate(parts)
    if with_music:
        audio = audio + _music(audio.size / RATE)
    return audio


def _segments(audio, gate_mode):
    cfg = AppConfig(streaming_enabled=False, gate_mode=gate_mode)
    finals = []
    segmenter = SpeechSegmenter(cfg, RATE, lambda chunks, duration, final, uid, ago: finals.append(duration))
    now = 0.0
    for start in range(0, audio.size - BLOCK, BLOCK):
        block = audio[start:start + BLOCK]
        segmenter.feed(block, float(np.sqrt(np.mean(block ** 2))), now)
        now += BLOCK / RATE
    segmenter.finish()
    return finals, cfg.max_segment_sec


def test_fixed_threshold_merges_sentences_under_music():
    finals, _ = _segments(_scene(), "rms")
    # Müzik eşiğin üstünde: cümle aralarını göremiyor, 6 cümle birkaç uzun parçaya karışıyor
    assert len(finals) < 6


def test_adaptive_gate_finds_sentence_breaks_under_music():
    finals, limit = _segments(_scene(), "auto")
    assert len(finals) == 6
    assert all(d < limit - 0.05 for d in finals)


def test_adaptive_gate_behaves_like_fixed_threshold_on_clean_speech():
    for seed in (1, 2, 3):
        clean = _scene(with_music=False, seed=seed)
        auto, fixed = _segments(clean, "auto")[0], _segments(clean, "rms")[0]
        assert len(auto) == len(fixed) == 6
        assert all(abs(a - f) < 0.15 for a, f in zip(auto, fixed, strict=True))
