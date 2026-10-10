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


def diarize_mp3(mp3_path: str, model_dir: str, ffmpeg_path: str, temp_dir: str,
                num_speakers: int | None = None):
    wav_path = extract_wav(ffmpeg_path, mp3_path, temp_dir)
    return diarize_audio(wav_path, model_dir, num_speakers)
