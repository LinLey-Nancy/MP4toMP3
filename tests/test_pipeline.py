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


# --- 终审修复：txt 已存在且不旧于 mp3 时跳过转写，直接复用 ---


def test_transcribe_one_skips_up_to_date_txt(tmp_path):
    import os
    mp3_dir = _setup(tmp_path, n=1)
    mp3_path = mp3_dir / "会0.mp3"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    txt_path = out_dir / "会0.txt"
    txt_path.write_text("历史转写结果", encoding="utf-8")
    # 保证 txt 的 mtime 严格新于 mp3（FAT/NTFS 时间戳精度）
    os.utime(mp3_path, (1000000000, 1000000000))
    os.utime(txt_path, (1000000100, 1000000100))

    def fail_if_called(*a, **k):
        pytest.fail("asr_fn 不应被调用：txt 已是最新")

    result = pipeline.transcribe_one(
        str(mp3_path), str(out_dir), "models", "ffmpeg.exe",
        str(tmp_path / "temp"), asr_fn=fail_if_called, diar_fn=fail_if_called)
    assert result == str(txt_path)
    assert txt_path.read_text(encoding="utf-8") == "历史转写结果"  # 未被覆盖


def test_transcribe_one_retries_stale_txt(tmp_path):
    import os
    mp3_dir = _setup(tmp_path, n=1)
    mp3_path = mp3_dir / "会0.mp3"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    txt_path = out_dir / "会0.txt"
    txt_path.write_text("旧结果", encoding="utf-8")
    # txt 旧于 mp3（例如 mp3 被重新转换过）→ 应重新转写
    os.utime(txt_path, (1000000000, 1000000000))
    os.utime(mp3_path, (1000000100, 1000000100))

    result = pipeline.transcribe_one(
        str(mp3_path), str(out_dir), "models", "ffmpeg.exe",
        str(tmp_path / "temp"), asr_fn=_fake_asr, diar_fn=_fake_diar)
    assert result == str(txt_path)
    assert "说话人1" in txt_path.read_text(encoding="utf-8")  # 已重转覆盖
