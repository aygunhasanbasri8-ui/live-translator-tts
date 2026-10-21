import numpy as np


class AudioMath:
    @staticmethod
    def to_mono(samples: np.ndarray, channels: int) -> np.ndarray:
        if channels <= 1:
            return samples
        usable = (len(samples) // channels) * channels
        if usable == 0:
            return samples[:0]
        return samples[:usable].reshape(-1, channels).mean(axis=1)

    @staticmethod
    def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate == dst_rate or samples.size == 0:
            return samples
        if src_rate > dst_rate:
            # aliasing'e karşı kaba ama yeterli bir kutu filtresi
            factor = int(src_rate // dst_rate)
            if factor > 1:
                kernel = np.ones(factor, dtype=np.float32) / factor
                samples = np.convolve(samples, kernel, mode="same").astype(np.float32)
        new_len = int(round(samples.size * dst_rate / src_rate))
        if new_len <= 1:
            return samples[:0]
        src_idx = np.linspace(0.0, samples.size - 1.0, new_len, dtype=np.float64)
        return np.interp(src_idx, np.arange(samples.size, dtype=np.float64), samples).astype(np.float32)

    @staticmethod
    def rms(samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))

    @staticmethod
    def float_to_pcm16(samples: np.ndarray) -> bytes:
        clipped = np.clip(samples, -1.0, 1.0)
        return (clipped * 32767.0).astype("<i2").tobytes()
