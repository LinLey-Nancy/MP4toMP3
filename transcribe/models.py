import hashlib
import json
import os
import urllib.request

ASR_PROFILES = {"small": "small", "turbo": "large-v3-turbo"}

DIAR_FILES = {
    "segmentation": "pyannote-segmentation-3-0.onnx",
    "embedding": "3dspeaker-eresnet.onnx",
}

# 主源 + 镜像兜底；落地文件名以 DIAR_FILES 为准，URL 仅作下载来源（URL 中的文件名可与落地名不同）
DIAR_URLS = {
    "segmentation": [
        "https://huggingface.co/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/model.onnx",
        "https://hf-mirror.com/csukuangfj/sherpa-onnx-pyannote-segmentation-3-0/resolve/main/model.onnx",
    ],
    "embedding": [
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
        "https://hf-mirror.com/csukuangfj/speaker-embedding-models/resolve/main/3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx",
    ],
}


class ModelDownloadError(Exception):
    pass


def diar_paths(model_dir: str) -> dict:
    return {k: os.path.join(model_dir, v) for k, v in DIAR_FILES.items()}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(model_dir: str) -> dict:
    p = os.path.join(model_dir, "manifest.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def diar_ready(model_dir: str) -> bool:
    manifest = _load_manifest(model_dir)
    for path in diar_paths(model_dir).values():
        if not os.path.exists(path):
            return False
        expected = manifest.get(os.path.basename(path))
        if expected and _sha256(path) != expected:
            return False
    return True


def _download_file(url: str, dest: str, progress_cb=None) -> None:
    """支持断点续传的单文件下载。"""
    tmp = dest + ".part"
    got = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={got}-"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(tmp, "ab") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress_cb:
                progress_cb(got)
    os.replace(tmp, dest)


def ensure_diar_models(model_dir: str, progress_cb=None) -> None:
    if diar_ready(model_dir):
        return
    os.makedirs(model_dir, exist_ok=True)
    try:
        for key, path in diar_paths(model_dir).items():
            if os.path.exists(path):
                continue
            last_err = None
            for url in DIAR_URLS[key]:
                try:
                    _download_file(url, path, progress_cb)
                    last_err = None
                    break
                except OSError as e:
                    last_err = e
            if last_err is not None:
                raise last_err
    except OSError as e:
        raise ModelDownloadError(f"模型下载失败：{e}。请检查网络后重试。") from e
