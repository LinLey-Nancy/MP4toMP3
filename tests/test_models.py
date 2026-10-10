import hashlib
import json
import pytest
from transcribe.models import (
    diar_ready, diar_paths, ensure_diar_models, ModelDownloadError, DIAR_FILES,
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
