# 语音转写与说话人分离 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有「视频批量转 MP3」工具上增加本地语音转文字 + 说话人区分能力（会议记录场景）。

**Architecture:** 新增独立 `transcribe/` 包：ffmpeg 抽取 16k 单声道临时 wav → sherpa-onnx 说话人分离 → faster-whisper 转写 → 按时间重叠对齐合并 → 输出带说话人标签的 txt。与 MP3 转换解耦，未勾选转写时行为与现状完全一致。

**Tech Stack:** Python 3.12（项目 venv，**不用**系统默认的 3.14 alpha）、faster-whisper 1.2.1、sherpa-onnx 1.13.8、pytest、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-10-10-transcribe-design.md`

## Global Constraints

- 纯本地运行，不依赖任何云端推理服务
- 便携、轻量：程序运行时 + 依赖约 300MB；模型外置 `models/` 目录，不进 exe
- 纯 CPU 与 N 卡都能跑：ASR 用 `device="auto", compute_type="int8"` 自动适配
- 转写主要面向中文：`transcribe(..., language="zh")`
- 模型分发两种包：迷你包（首启下载）+ 全量包（内置 `models/`）
- 输出： `[HH:MM:SS] 说话人N: 文字` 的 txt，写入 `transcript_output/`
- 隔离约定：实现只新增 `transcribe/`、`models/`、`tests/`、`tools/` 等新文件；`main.py` 的集成改动放最后（Task 8），等并行会话提交后再做，撞车以对方为准、本方 rebase

## Review Focus

1. **系统 Python 是 3.14 alpha**——faster-whisper / sherpa-onnx 在 3.14 上没有预编译 wheel，装了必炸。所有任务一律用 `py -3.12` 创建的 `.venv`。Task 1 的验证步骤钉死这一点。
2. **无人声 / 极短音频**：sherpa-onnx 分离遇到全静音会报错或返回空。预期行为：正常输出 txt，全部标「说话人1」或仅输出转写文字。Task 5、Task 6 各有对应测试/步骤。
3. **CUDA 机器缺 cuDNN/cuBLAS 动态库**：`device="auto"` 探测到 N 卡但库不全时 ctranslate2 会抛异常。预期行为：捕获异常回退 CPU 继续跑，并在日志说明。Task 4 钉死。
4. **模型下载中断 / 校验失败**：预期行为：断点续传、sha256 不符自动重下，失败给明确中文提示而不是崩溃。Task 3 钉死。
5. **ffmpeg 抽取临时 wav 失败**（损坏视频、无音轨）：预期行为：记日志、跳过该文件、不阻塞队列。Task 6 钉死。

---

### Task 1: 环境准备与项目骨架

**Files:**
- Create: `requirements-transcribe.txt`
- Create: `transcribe/__init__.py`（空文件）
- Create: `tests/__init__.py`（空文件）
- Modify: `.gitignore`（无则新建）

**Interfaces:**
- Produces: `.venv/`（Python 3.12 虚拟环境，后续所有任务共用）；`transcribe` 包名

- [ ] **Step 1: 创建依赖清单**

`requirements-transcribe.txt`:

```text
faster-whisper==1.2.1
sherpa-onnx==1.13.8
pytest==8.3.4
pyinstaller==6.11.1
```

- [ ] **Step 2: 创建 Python 3.12 虚拟环境并安装**

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-transcribe.txt
```

- [ ] **Step 3: 验证关键依赖在 3.12 下可导入**

```bash
.venv/Scripts/python -c "import faster_whisper, sherpa_onnx, ctranslate2; print(faster_whisper.__version__, sherpa_onnx.__version__)"
```

预期：打印版本号，无 ImportError。若 sherpa-onnx 在 3.12 无 wheel，回退到 `py -3.11`（uv 已装 3.11.15）重建 venv 并把本行结论记入 README。

- [ ] **Step 4: 建包骨架与 .gitignore**

```bash
mkdir -p transcribe tests tools
```

`transcribe/__init__.py`、`tests/__init__.py` 为空文件。`.gitignore` 追加：

```text
.venv/
models/
temp/
mp3_output/
transcript_output/
dist/
build/
__pycache__/
*.spec
```

- [ ] **Step 5: 验证 pytest 可运行**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

预期：no tests ran，退出码 5（无测试是正常）。

- [ ] **Step 6: Commit**

```bash
git add requirements-transcribe.txt transcribe/__init__.py tests/__init__.py .gitignore
git commit -m "chore: 转写功能环境与包骨架"
```

---

### Task 2: align.py —— 转写段与说话人的对齐合并（纯逻辑，TDD）

**Files:**
- Create: `transcribe/align.py`
- Test: `tests/test_align.py`

**Interfaces:**
- Consumes: 无（纯函数）
- Produces（Task 6 依赖，签名一字不动）:
  - `assign_speakers(asr_segments: list[dict], diar_segments: list[dict]) -> list[dict]`
    - asr: `[{"start": float, "end": float, "text": str}]`
    - diar: `[{"start": float, "end": float, "speaker": int}]`
    - 返回 asr 段 + `"speaker": int`
  - `merge_adjacent(segments: list[dict]) -> list[dict]`（相邻同说话人合并，文本以空格拼接）
  - `format_transcript(segments: list[dict]) -> str`（`[HH:MM:SS] 说话人N: 文本`，逐行）
  - `format_ts(seconds: float) -> str`（`HH:MM:SS`，秒以下截断）

- [ ] **Step 1: 写失败测试**

`tests/test_align.py`:

```python
from transcribe.align import (
    assign_speakers, merge_adjacent, format_transcript, format_ts,
)


def test_format_ts():
    assert format_ts(0) == "00:00:00"
    assert format_ts(65.9) == "00:01:05"
    assert format_ts(3661.2) == "01:01:01"


def test_assign_speakers_picks_max_overlap():
    asr = [{"start": 0.0, "end": 10.0, "text": "你好"}]
    diar = [
        {"start": 0.0, "end": 3.0, "speaker": 0},
        {"start": 3.0, "end": 10.0, "speaker": 1},
    ]
    result = assign_speakers(asr, diar)
    assert result[0]["speaker"] == 1  # 7 秒重叠 > 3 秒


def test_assign_speakers_no_diarization_defaults_to_zero():
    asr = [{"start": 0.0, "end": 5.0, "text": "喂"}]
    assert assign_speakers(asr, [])[0]["speaker"] == 0


def test_assign_speakers_gap_defaults_to_zero():
    asr = [{"start": 0.0, "end": 2.0, "text": "嗯"}]
    diar = [{"start": 5.0, "end": 9.0, "speaker": 3}]
    assert assign_speakers(asr, diar)[0]["speaker"] == 0


def test_merge_adjacent_same_speaker():
    segs = [
        {"start": 0.0, "end": 2.0, "text": "先过一下", "speaker": 1},
        {"start": 2.0, "end": 5.0, "text": "上周进度", "speaker": 1},
        {"start": 5.0, "end": 8.0, "text": "好的", "speaker": 2},
    ]
    merged = merge_adjacent(segs)
    assert len(merged) == 2
    assert merged[0]["end"] == 5.0
    assert merged[0]["text"] == "先过一下 上周进度"


def test_format_transcript():
    segs = [
        {"start": 2.0, "end": 5.0, "text": "我们先过一下进度。", "speaker": 0},
        {"start": 15.0, "end": 20.0, "text": "联调基本完成了。", "speaker": 1},
    ]
    text = format_transcript(segs)
    assert text == (
        "[00:00:02] 说话人1: 我们先过一下进度。\n"
        "[00:01:15] 说话人2: 联调基本完成了。\n"
    )
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python -m pytest tests/test_align.py -v
```

预期：ImportError（模块不存在）。

- [ ] **Step 3: 实现 align.py**

`transcribe/align.py`:

```python
def format_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(asr_segments, diar_segments):
    for seg in asr_segments:
        best_speaker, best_overlap = 0, 0.0
        for d in diar_segments:
            ov = _overlap(seg["start"], seg["end"], d["start"], d["end"])
            if ov > best_overlap:
                best_speaker, best_overlap = d["speaker"], ov
        seg["speaker"] = best_speaker
    return asr_segments


def merge_adjacent(segments):
    merged = []
    for seg in segments:
        if merged and merged[-1]["speaker"] == seg["speaker"]:
            merged[-1]["end"] = seg["end"]
            merged[-1]["text"] += " " + seg["text"]
        else:
            merged.append(dict(seg))
    return merged


def format_transcript(segments):
    return "".join(
        f"[{format_ts(s['start'])}] 说话人{s['speaker'] + 1}: {s['text'].strip()}\n"
        for s in segments
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python -m pytest tests/test_align.py -v
```

预期：5 passed。

- [ ] **Step 5: Commit**

```bash
git add transcribe/align.py tests/test_align.py
git commit -m "feat: 转写段与说话人对齐合并逻辑"
```

---

### Task 3: models.py —— 模型清单、检测、下载、校验

**Files:**
- Create: `transcribe/models.py`
- Create: `tools/build_manifest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces（Task 4/5/6/8 依赖）:
  - `ASR_PROFILES = {"small": "small", "turbo": "large-v3-turbo"}`（faster-whisper 模型名）
  - `DIAR_FILES = {"segmentation": "pyannote-segmentation-3-0.onnx", "embedding": "3dspeaker-eresnet.onnx"}`（文件名常量）
  - `diar_ready(model_dir: str) -> bool`
  - `diar_paths(model_dir: str) -> dict`（`{"segmentation": 绝对路径, "embedding": 绝对路径}`）
  - `ensure_diar_models(model_dir: str, progress_cb=None) -> None`（缺失则下载，失败抛 `ModelDownloadError`（自定义异常，带中文 message））
  - `ModelDownloadError(Exception)`

下载源：分离模型走 GitHub release / ModelScope 双 URL 兜底；ASR 模型由 faster-whisper 自带的 huggingface_hub 下载（设 `HF_ENDPOINT=https://hf-mirror.com` 镜像兜底，见 Task 4）。分离模型 sha256 清单由 `tools/build_manifest.py` 在**发版时**生成 `models/manifest.json`；运行期校验：文件存在且（有 manifest 时）sha256 相符。

- [ ] **Step 1: 写失败测试**

`tests/test_models.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python -m pytest tests/test_models.py -v
```

预期：ImportError。

- [ ] **Step 3: 实现 models.py 与 build_manifest.py**

`transcribe/models.py`:

```python
import hashlib
import json
import os
import urllib.request

ASR_PROFILES = {"small": "small", "turbo": "large-v3-turbo"}

DIAR_FILES = {
    "segmentation": "pyannote-segmentation-3-0.onnx",
    "embedding": "3dspeaker-eresnet.onnx",
}

# 主源 + 镜像兜底；文件名即落地文件名
DIAR_URLS = {
    "segmentation": [
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/pyannote-segmentation-3-0.onnx",
        "https://modelscope.cn/models/csukuangfj/sherpa-onnx-models/resolve/master/pyannote-segmentation-3-0.onnx",
    ],
    "embedding": [
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eresnet_sv_en_voxceleb_16k.onnx",
        "https://modelscope.cn/models/csukuangfj/sherpa-onnx-models/resolve/master/3dspeaker_speech_eresnet_sv_en_voxceleb_16k.onnx",
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
```

注意：上面 URL 在 Task 3 Step 4 必须用 `curl -I` 实际验证 200/302，失效就到 sherpa-onnx release 页找当前文件名替换，文件名改动要同步 `DIAR_FILES`。

`tools/build_manifest.py`（发版时跑，为 `models/` 内所有 onnx 生成 sha256 清单）:

```python
import hashlib
import json
import os
import sys

def main(model_dir):
    manifest = {}
    for name in os.listdir(model_dir):
        if not name.endswith(".onnx"):
            continue
        h = hashlib.sha256()
        with open(os.path.join(model_dir, name), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        manifest[name] = h.hexdigest()
    out = os.path.join(model_dir, "manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"written {out} ({len(manifest)} files)")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "models")
```

- [ ] **Step 4: 验证下载 URL 可用 + 跑测试**

```bash
curl -sI -o /dev/null -w "%{http_code}\n" "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/pyannote-segmentation-3-0.onnx"
curl -sI -o /dev/null -w "%{http_code}\n" "https://modelscope.cn/models/csukuangfj/sherpa-onnx-models/resolve/master/pyannote-segmentation-3-0.onnx"
.venv/Scripts/python -m pytest tests/test_models.py -v
```

预期：URL 返回 200 或 302；5 passed。

- [ ] **Step 5: Commit**

```bash
git add transcribe/models.py tools/build_manifest.py tests/test_models.py
git commit -m "feat: 模型检测、断点续传下载与 sha256 校验"
```

---

### Task 4: asr.py —— faster-whisper 封装（设备自动适配 + CUDA 回退）

**Files:**
- Create: `transcribe/asr.py`
- Test: `tests/test_asr.py`（只测纯逻辑部分：设备回退决策）

**Interfaces:**
- Consumes: `transcribe.models.ASR_PROFILES`
- Produces（Task 6 依赖）:
  - `transcribe_audio(audio_path: str, model_dir: str, profile: str = "small") -> list[dict]`
    - 返回 `[{"start": float, "end": float, "text": str}]`，按 start 升序
  - 内部 `_create_model(model_name, model_dir)`：先 `device="auto"`，ct2 因 CUDA 库缺失抛异常时回退 `device="cpu"`，两级都用 `compute_type="int8"`

- [ ] **Step 1: 写失败测试**

`tests/test_asr.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python -m pytest tests/test_asr.py -v
```

预期：ImportError / AttributeError。

- [ ] **Step 3: 实现 asr.py**

`transcribe/asr.py`:

```python
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")  # 国内镜像兜底

from faster_whisper import WhisperModel

from .models import ASR_PROFILES

_model_cache = {}


def _create_model(model_name: str, model_dir: str):
    try:
        return WhisperModel(model_name, device="auto", compute_type="int8",
                            download_root=model_dir)
    except Exception:
        # 探测到 N 卡但 CUDA/cuDNN 动态库缺失 → 回退纯 CPU
        return WhisperModel(model_name, device="cpu", compute_type="int8",
                            download_root=model_dir)


def transcribe_audio(audio_path: str, model_dir: str, profile: str = "small"):
    name = ASR_PROFILES[profile]
    if name not in _model_cache:
        _model_cache[name] = _create_model(name, model_dir)
    model = _model_cache[name]
    segments, _info = model.transcribe(
        audio_path, language="zh", vad_filter=True, beam_size=5,
    )
    return sorted(
        ({"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments),
        key=lambda s: s["start"],
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python -m pytest tests/test_asr.py -v
```

预期：2 passed。

- [ ] **Step 5: Commit**

```bash
git add transcribe/asr.py tests/test_asr.py
git commit -m "feat: faster-whisper 封装（设备自动适配 + CUDA 回退）"
```

---

### Task 5: diarize.py —— sherpa-onnx 说话人分离封装

**Files:**
- Create: `transcribe/diarize.py`
- Test: `tests/test_diarize.py`（只测 wav 读取与空结果处理；模型推理走人工冒烟）

**Interfaces:**
- Consumes: `transcribe.models.diar_paths`（Task 3）；`resource_path("ffmpeg.exe")` 由调用方传入路径字符串，diarize 不依赖 main.py
- Produces（Task 6 依赖）:
  - `extract_wav(ffmpeg_path: str, audio_path: str, temp_dir: str) -> str`（16k 单声道 wav 路径；ffmpeg 失败抛 `subprocess.CalledProcessError`）
  - `diarize_audio(wav_path: str, model_dir: str, num_speakers: int | None = None) -> list[dict]`
    - 返回 `[{"start": float, "end": float, "speaker": int}]`；**空结果或推理异常返回 `[]`**（无人声场景，Review Focus #2）

- [ ] **Step 1: 写失败测试**

`tests/test_diarize.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python -m pytest tests/test_diarize.py -v
```

预期：ImportError。

- [ ] **Step 3: 实现 diarize.py**

`transcribe/diarize.py`:

```python
import os
import subprocess
import wave

import numpy as np
import sherpa_onnx

from .models import diar_paths


def extract_wav(ffmpeg_path: str, audio_path: str, temp_dir: str) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    out = os.path.join(temp_dir, os.path.splitext(os.path.basename(audio_path))[0] + ".wav")
    subprocess.run(
        [ffmpeg_path, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1",
         "-f", "wav", out],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return out


def _read_wav(path: str):
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        if rate != 16000:
            raise ValueError(f"wav 采样率必须是 16000，实际 {rate}")
        n = w.getnframes()
        pcm = w.readframes(n)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, rate


def _create_diarizer(model_dir: str, num_speakers: int | None):
    paths = diar_paths(model_dir)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=paths["segmentation"]),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=paths["embedding"]),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers if num_speakers else -1),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    return sherpa_onnx.OfflineSpeakerDiarization(config)


def diarize_audio(wav_path: str, model_dir: str, num_speakers: int | None = None):
    try:
        samples, _rate = _read_wav(wav_path)
        sd = _create_diarizer(model_dir, num_speakers)
        result = sd.process(samples)
        return sorted(
            ({"start": s.start, "end": s.end, "speaker": s.speaker} for s in result),
            key=lambda s: s["start"],
        )
    except Exception:
        # 无人声 / 音频过短 / 推理失败：返回空，由对齐层兜底为说话人1
        return []
```

注：`OfflineSpeakerDiarization` 的配置字段名以 sherpa-onnx 1.13.8 实际为准；实现时先跑 `python -c "import sherpa_onnx; help(sherpa_onnx.OfflineSpeakerDiarizationConfig)"` 核对，字段名不同就按实际改。

- [ ] **Step 4: 跑测试确认通过 + API 核对**

```bash
.venv/Scripts/python -m pytest tests/test_diarize.py -v
.venv/Scripts/python -c "import sherpa_onnx; print(hasattr(sherpa_onnx, 'OfflineSpeakerDiarization'))"
```

预期：2 passed；True。

- [ ] **Step 5: Commit**

```bash
git add transcribe/diarize.py tests/test_diarize.py
git commit -m "feat: sherpa-onnx 说话人分离封装"
```

---

### Task 6: pipeline.py —— 单文件与整目录编排

**Files:**
- Create: `transcribe/pipeline.py`
- Test: `tests/test_pipeline.py`（asr/diarize 用 fake 注入，不碰真模型）

**Interfaces:**
- Consumes: `transcribe_audio`（Task 4）、`extract_wav` / `diarize_audio`（Task 5）、`assign_speakers` / `merge_adjacent` / `format_transcript`（Task 2）
- Produces（Task 7/8 依赖）:
  - `transcribe_one(mp3_path: str, out_dir: str, model_dir: str, ffmpeg_path: str, temp_dir: str, profile: str = "small", num_speakers: int | None = None) -> str | None`（成功返回 txt 路径，失败返回 None 并记日志）
  - `transcribe_folder(mp3_dir: str, out_dir: str, model_dir: str, ffmpeg_path: str, temp_dir: str, profile: str = "small", num_speakers: int | None = None, progress_cb=None) -> list[str]`（progress_cb(i, total, filename)；单文件失败跳过不阻塞，Review Focus #5）
  - 两函数接受可选依赖注入参数 `asr_fn=None, diar_fn=None`（默认用真实现）

- [ ] **Step 1: 写失败测试**

`tests/test_pipeline.py`:

```python
import pytest
from transcribe import pipeline


def _fake_asr(path, model_dir, profile="small"):
    return [
        {"start": 2.0, "end": 5.0, "text": "我们先过一下进度。"},
        {"start": 15.0, "end": 20.0, "text": "联调基本完成了。"},
    ]


def _fake_diar(wav_path, model_dir, num_speakers=None):
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/Scripts/python -m pytest tests/test_pipeline.py -v
```

预期：ImportError。

- [ ] **Step 3: 实现 pipeline.py**

`transcribe/pipeline.py`:

```python
import logging
import os

from .align import assign_speakers, merge_adjacent, format_transcript
from .asr import transcribe_audio
from .diarize import extract_wav, diarize_audio

logger = logging.getLogger(__name__)


def transcribe_one(mp3_path, out_dir, model_dir, ffmpeg_path, temp_dir,
                   profile="small", num_speakers=None,
                   asr_fn=None, diar_fn=None):
    asr_fn = asr_fn or transcribe_audio
    diar_fn = diar_fn or diarize_audio
    try:
        diar = diar_fn(extract_wav(ffmpeg_path, mp3_path, temp_dir),
                       model_dir, num_speakers) if diar_fn is diarize_audio else \
               diar_fn(mp3_path, model_dir, num_speakers)
        asr = asr_fn(mp3_path, model_dir, profile)
        labeled = merge_adjacent(assign_speakers(asr, diar))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(
            out_dir, os.path.splitext(os.path.basename(mp3_path))[0] + ".txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(format_transcript(labeled))
        return out_path
    except Exception:
        logger.exception("转写失败: %s", mp3_path)
        return None


def transcribe_folder(mp3_dir, out_dir, model_dir, ffmpeg_path, temp_dir,
                      profile="small", num_speakers=None, progress_cb=None,
                      asr_fn=None, diar_fn=None):
    files = sorted(f for f in os.listdir(mp3_dir) if f.lower().endswith(".mp3"))
    total = len(files)
    results = []
    for i, name in enumerate(files, 1):
        if progress_cb:
            progress_cb(i, total, name)
        r = transcribe_one(os.path.join(mp3_dir, name), out_dir, model_dir,
                           ffmpeg_path, temp_dir, profile, num_speakers,
                           asr_fn=asr_fn, diar_fn=diar_fn)
        if r:
            results.append(r)
    return results
```

注意：上面 `transcribe_one` 里对 `extract_wav` 的调用方式（真实 diar_fn 需要先抽 wav，fake 不需要）在实现时要理顺——建议统一约定 **diar_fn 直接收 mp3 路径、内部自己抽 wav**，即把 `extract_wav` 调用移进 `diarize_audio` 的薄封装 `diarize_mp3(mp3_path, model_dir, ffmpeg_path, temp_dir, num_speakers=None)`，fake 按同签名注入。实现时以此为准并同步修正本文件与测试。

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/Scripts/python -m pytest tests/test_pipeline.py -v
```

预期：3 passed。

- [ ] **Step 5: Commit**

```bash
git add transcribe/pipeline.py tests/test_pipeline.py
git commit -m "feat: 转写流水线编排"
```

---

### Task 7: 命令行入口（不碰 main.py 也能端到端验证）

**Files:**
- Create: `transcribe/__main__.py`

**Interfaces:**
- Consumes: `transcribe_folder`（Task 6）、`ensure_diar_models` / `diar_ready`（Task 3）
- Produces: `python -m transcribe <mp3目录> [--profile small|turbo] [--speakers N]` 命令行入口

- [ ] **Step 1: 实现 __main__.py**

`transcribe/__main__.py`:

```python
import argparse
import logging
import os
import sys

from .models import diar_ready, ensure_diar_models, ModelDownloadError
from .pipeline import transcribe_folder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def resource_path(rel):
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def main():
    ap = argparse.ArgumentParser(description="MP3 批量转写（带说话人区分）")
    ap.add_argument("mp3_dir")
    ap.add_argument("--profile", choices=["small", "turbo"], default="small")
    ap.add_argument("--speakers", type=int, default=None)
    args = ap.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_dir = os.path.join(base, "models")
    if not diar_ready(model_dir):
        try:
            print("首次运行需要下载说话人分离模型（约 35MB）...")
            ensure_diar_models(model_dir, progress_cb=lambda n: print(f"\r已下载 {n >> 20} MB", end=""))
            print()
        except ModelDownloadError as e:
            print(e, file=sys.stderr)
            sys.exit(1)

    out_dir = os.path.join(args.mp3_dir, "transcript_output")
    results = transcribe_folder(
        args.mp3_dir, out_dir, model_dir,
        resource_path("ffmpeg.exe"), os.path.join(base, "temp"),
        profile=args.profile, num_speakers=args.speakers,
        progress_cb=lambda i, t, n: print(f"[{i}/{t}] {n}"),
    )
    print(f"完成 {len(results)} 个，输出目录: {out_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 人工冒烟——真模型跑通一个短音频**

准备一段 30 秒中文单人讲话 mp3 放到 `demo/`：

```bash
.venv/Scripts/python -m transcribe demo --profile small
```

预期：下载分离模型 + whisper-small（首次约 300MB），`demo/transcript_output/` 生成 txt，内容可读、标「说话人1」。此步是 Review Focus #2/#3/#4 的真机验证，结果记录在 commit message。

- [ ] **Step 3: Commit**

```bash
git add transcribe/__main__.py
git commit -m "feat: 转写命令行入口"
```

---

### Task 8: main.py UI 集成（**等并行会话提交后再做**）

**前置条件（开工前必查）:** `git status` 确认 `main.py` 无未提交改动；`git log -1 --format=%ci -- main.py` 确认并行会话的最新提交已落。不满足就停下等对方。

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `transcribe.pipeline.transcribe_folder`（Task 6）、`transcribe.models.diar_ready / ensure_diar_models / ModelDownloadError`（Task 3）
- Produces: 主窗口新增「转写文字（识别说话人）」勾选框（默认关）+「说话人数」下拉（自动/2/3/4/5）

- [ ] **Step 1: 读当时的 main.py 全文**

并行会话可能已大改，以读到的最新内容为准重新定位插入点，**禁止**按旧行号改。

- [ ] **Step 2: 加控件与转写钩子**

在现有「开始转换」流程上挂钩子：转换队列跑完（`result_q` 收到 `"done"`）且勾选框选中时，若 `diar_ready` 为否则弹窗询问是否下载（是 → `ensure_diar_models` 后台线程 + 进度提示；否 → 只保留 MP3），然后对 `mp3_output/` 调 `transcribe_folder`，进度复用现有 Progressbar，完成弹窗显示输出目录。说话人数下拉「自动」传 `None`，数字传 `int`。

转写必须放独立线程（沿用现有 worker + queue 模式），UI 线程不阻塞；`temp/` 在程序启动时清空。

- [ ] **Step 3: 手工验证**

```bash
.venv/Scripts/python main.py
```

选一个含 2 个短视频的文件夹：不勾选 → 只出 MP3（回归现有行为）；勾选 → MP3 + txt，说话人标签正确。

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: 主界面集成转写选项与说话人数设置"
```

---

### Task 9: 打包（迷你包 + 全量包）

**Files:**
- Create: `build-transcribe.bat`（**不动** 现有 `build.bat`，避免与并行会话冲突）
- Modify: `README.md`（追加转写功能说明与两种包的区别）

- [ ] **Step 1: 写 build-transcribe.bat**

要点（实现时展开为完整 bat）：

```bat
chcp 65001 >nul
:: onedir 模式；ffmpeg.exe 与 models/ 外置
.venv\Scripts\pyinstaller --onedir --windowed --name MP4toMP3 ^
  --add-binary "ffmpeg.exe;." main.py
:: 迷你包：dist\MP4toMP3 直接 zip（不含 models）
:: 全量包：把 models\ 拷进 dist\MP4toMP3 后再 zip
:: 全量包打包前先跑 tools/build_manifest.py models 生成 sha256 清单
```

GPU 说明：默认打 CPU 基线包（两种包都能在 N 卡机器跑）；CUDA 加速需另装 cuBLAS/cuDNN，属二期可选项，本次不出 GPU 专包。

- [ ] **Step 2: 打包并在干净目录验证**

- 全量包：解压到无 Python 的机器/目录，双击运行，转写一个中文视频 → txt 正确
- 迷你包：断网虚拟机（或拔网线）双击 → 弹模型下载提示；恢复网络下载完成后再次断网运行 → 全流程可用（Review Focus #4 闭环）

- [ ] **Step 3: 更新 README 并 Commit**

```bash
git add build-transcribe.bat README.md
git commit -m "build: 转写版双发行包构建脚本与文档"
```

---

### Task 10: 端到端验收

**Files:** 无（纯验证）

- [ ] **Step 1: 三段测试音频人工核对**：单人讲话、双人对话、4 人会议（各 1~3 分钟），核对说话人切换点与中文错字率
- [ ] **Step 2: 纯 CPU 机器全流程**；有 N 卡的机器确认日志显示 cuda 或回退提示
- [ ] **Step 3: 结果汇总写进 commit / 用户汇报**：各音频说话人区分对错、错字感受、各机型耗时
