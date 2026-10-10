import wave
import struct
import pytest
from transcribe.diarize import _read_wav


def _write_wav(path, n_samples=1600, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", 0) for _ in range(n_samples)))


def test_read_wav(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p)
    samples, rate = _read_wav(str(p))
    assert rate == 16000
    assert len(samples) == 1600


def test_read_wav_wrong_rate_raises(tmp_path):
    p = tmp_path / "b.wav"
    _write_wav(p, rate=8000)
    with pytest.raises(ValueError, match="16000"):
        _read_wav(str(p))
