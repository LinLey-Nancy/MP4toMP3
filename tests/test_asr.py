import pytest
from transcribe import asr


def test_create_model_falls_back_to_cpu(monkeypatch):
    calls = []

    class FakeWhisper:
        def __init__(self, name, device=None, compute_type=None, download_root=None):
            calls.append(device)
            if device == "auto":
                raise RuntimeError("cudnn64_9.dll not found")

    monkeypatch.setattr("transcribe.asr.WhisperModel", FakeWhisper)
    model = asr._create_model("small", "models")
    assert calls == ["auto", "cpu"]


def test_create_model_keeps_auto_when_ok(monkeypatch):
    class FakeWhisper:
        def __init__(self, name, device=None, compute_type=None, download_root=None):
            pass

    monkeypatch.setattr("transcribe.asr.WhisperModel", FakeWhisper)
    asr._create_model("small", "models")
