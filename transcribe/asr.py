import logging
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")  # 国内镜像兜底
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet 通道弱网静默挂死，强制走普通下载

from faster_whisper import WhisperModel

from .models import ASR_PROFILES

_model_cache = {}


def _create_model(model_name: str, model_dir: str):
    try:
        return WhisperModel(model_name, device="auto", compute_type="int8",
                            download_root=model_dir)
    except Exception as e:
        # 探测到 N 卡但 CUDA/cuDNN 动态库缺失 → 回退纯 CPU
        logging.getLogger(__name__).warning("CUDA 初始化失败，回退 CPU：%s", e)
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
