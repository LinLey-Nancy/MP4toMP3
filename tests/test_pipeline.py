import pytest
from transcribe import pipeline


def _fake_asr(path, model_dir, profile="small"):
    return [
        {"start": 2.0, "end": 5.0, "text": "我们先过一下进度。"},
        {"start": 15.0, "end": 20.0, "text": "联调基本完成了。"},
    ]


def _fake_diar(path, model_dir, ffmpeg_path, temp_dir, num_speakers=None):
    return [
        {"start": 0.0, "end": 10.0, "speaker": 0},
        {"start": 10.0, "end": 25.0, "speaker": 1},
    ]


def _setup(tmp_path, n=2):
    mp3_dir = tmp_path / "mp3_output"
    mp3_dir.mkdir()
    for i in range(n):
        (mp3_dir / f"会{i}.mp3").write_bytes(b"fake")
    return mp3_dir


def test_transcribe_folder_writes_txt(tmp_path):
    mp3_dir = _setup(tmp_path)
    out_dir = str(tmp_path / "transcript_output")
    results = pipeline.transcribe_folder(
        str(mp3_dir), out_dir, "models", "ffmpeg.exe", str(tmp_path / "temp"),
        asr_fn=_fake_asr, diar_fn=_fake_diar,
    )
    assert len(results) == 2
    text = open(results[0], encoding="utf-8").read()
    assert "说话人1: 我们先过一下进度。" in text
    assert "说话人2: 联调基本完成了。" in text


def test_transcribe_folder_skips_failed_file(tmp_path):
    mp3_dir = _setup(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("损坏的文件")

    results = pipeline.transcribe_folder(
        str(mp3_dir), str(tmp_path / "out"), "models", "ffmpeg.exe",
        str(tmp_path / "temp"), asr_fn=boom, diar_fn=_fake_diar,
    )
    assert results == []  # 全部失败但不抛异常


def test_progress_callback(tmp_path):
    mp3_dir = _setup(tmp_path, n=2)
    calls = []
    pipeline.transcribe_folder(
        str(mp3_dir), str(tmp_path / "out"), "models", "ffmpeg.exe",
        str(tmp_path / "temp"), asr_fn=_fake_asr, diar_fn=_fake_diar,
        progress_cb=lambda i, total, name: calls.append((i, total, name)),
    )
    assert [c[:2] for c in calls] == [(1, 2), (2, 2)]
