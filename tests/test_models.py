import hashlib
import http.client
import json
import os
import pytest
import transcribe.models as models
from transcribe.models import (
    diar_ready, diar_paths, ensure_diar_models, ModelDownloadError, DIAR_FILES,
    DIAR_URLS,
)


def _write_fake_models(tmp_path, manifest=True):
    for name in DIAR_FILES.values():
        data = ("fake-" + name).encode()
        (tmp_path / name).write_bytes(data)
    if manifest:
        m = {
            name: hashlib.sha256(("fake-" + name).encode()).hexdigest()
            for name in DIAR_FILES.values()
        }
        (tmp_path / "manifest.json").write_text(json.dumps(m))


def test_diar_ready_false_when_missing(tmp_path):
    assert diar_ready(str(tmp_path)) is False


def test_diar_ready_true_when_all_present(tmp_path):
    _write_fake_models(tmp_path)
    assert diar_ready(str(tmp_path)) is True


def test_diar_ready_false_on_sha_mismatch(tmp_path):
    _write_fake_models(tmp_path)
    (tmp_path / DIAR_FILES["embedding"]).write_bytes(b"corrupted")
    assert diar_ready(str(tmp_path)) is False


# --- 终审修复：损坏的 manifest.json 不得抛异常，按无清单处理（仅查存在性） ---


def test_diar_ready_tolerates_corrupted_manifest(tmp_path):
    _write_fake_models(tmp_path)
    (tmp_path / "manifest.json").write_bytes(b"\xff\xfe garbage-not-json {{{")
    assert diar_ready(str(tmp_path)) is True  # 模型文件在，无清单可校验即视为就绪


def test_diar_ready_missing_models_with_corrupted_manifest(tmp_path):
    (tmp_path / "manifest.json").write_bytes(b"\xff\xfe garbage-not-json {{{")
    assert diar_ready(str(tmp_path)) is False  # 模型文件不存在，仍不就绪


def test_diar_paths(tmp_path):
    p = diar_paths(str(tmp_path))
    assert p["segmentation"].endswith(DIAR_FILES["segmentation"])
    assert p["embedding"].endswith(DIAR_FILES["embedding"])


def test_ensure_raises_when_download_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "transcribe.models._download_file",
        lambda *a, **k: (_ for _ in ()).throw(OSError("network down")),
    )
    with pytest.raises(ModelDownloadError, match="模型下载失败"):
        ensure_diar_models(str(tmp_path))


# --- Finding 1 回归：IncompleteRead（非 OSError）必须被包成 ModelDownloadError ---


def test_ensure_wraps_incomplete_read(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise http.client.IncompleteRead(b"partial")
    monkeypatch.setattr("transcribe.models._download_file", boom)
    with pytest.raises(ModelDownloadError, match="模型下载失败"):
        ensure_diar_models(str(tmp_path))


# --- Finding 2a 回归：sha 不符的已存在文件应删除后重下，而不是跳过 ---


def test_ensure_redownloads_corrupted_file(tmp_path, monkeypatch):
    _write_fake_models(tmp_path)
    (tmp_path / DIAR_FILES["embedding"]).write_bytes(b"corrupted")
    calls = []

    def fake_download(url, dest, progress_cb=None):
        calls.append(url)
        name = os.path.basename(dest)
        with open(dest, "wb") as f:
            f.write(("fake-" + name).encode())
    monkeypatch.setattr("transcribe.models._download_file", fake_download)

    ensure_diar_models(str(tmp_path))
    assert diar_ready(str(tmp_path)) is True
    assert calls == [DIAR_URLS["embedding"][0]]  # 只重下损坏的那个文件


# --- Finding 2b 回归：下载后 sha 不符应换下一个 URL 重试 ---


def test_ensure_retries_next_url_on_bad_sha(tmp_path, monkeypatch):
    m = {
        name: hashlib.sha256(("fake-" + name).encode()).hexdigest()
        for name in DIAR_FILES.values()
    }
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    attempts = {}

    def fake_download(url, dest, progress_cb=None):
        name = os.path.basename(dest)
        attempts[name] = attempts.get(name, 0) + 1
        # 每个文件的第一个 URL 都给坏内容，第二个 URL 给正确内容
        data = b"garbage" if attempts[name] == 1 else ("fake-" + name).encode()
        with open(dest, "wb") as f:
            f.write(data)
    monkeypatch.setattr("transcribe.models._download_file", fake_download)

    ensure_diar_models(str(tmp_path))
    assert diar_ready(str(tmp_path)) is True
    assert sorted(attempts.values()) == [2, 2]  # 每个文件都走了兜底 URL


# --- Finding 2b 回归：Content-Length 与实际字节数不符判失败，截断文件不落地 ---


class _FakeResp:
    def __init__(self, status, payload, content_length):
        self.status = status
        self.headers = {"Content-Length": str(content_length)}
        self._payload = payload
        self._sent = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        if self._sent:
            return b""  # 连接提前关闭：CPython 静默返回空
        self._sent = True
        return self._payload


def test_download_file_size_mismatch_raises(tmp_path, monkeypatch):
    # 承诺 10 字节实际 0 字节
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeResp(200, b"", 10),
    )
    dest = str(tmp_path / "x.onnx")
    with pytest.raises(http.client.HTTPException):
        models._download_file("http://example.com/x", dest)
    assert not os.path.exists(dest)  # 截断文件不应被当作完成落地


# --- Finding 2 防御回归：续传时服务器忽略 Range（未回 206）应截断重写 ---


def test_download_file_range_ignored_rewrites(tmp_path, monkeypatch):
    dest = str(tmp_path / "x.onnx")
    with open(dest + ".part", "wb") as f:
        f.write(b"stale-bytes")
    payload = b"fresh-full-content"
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeResp(200, payload, len(payload)),  # 非 206
    )
    models._download_file("http://example.com/x", dest)
    with open(dest, "rb") as f:
        assert f.read() == payload  # 不是 stale 残片与新内容的拼接
