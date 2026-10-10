import logging
import os

from .align import assign_speakers, merge_adjacent, format_transcript
from .asr import transcribe_audio
from .diarize import diarize_mp3

logger = logging.getLogger(__name__)


def transcribe_one(mp3_path, out_dir, model_dir, ffmpeg_path, temp_dir,
                   profile="small", num_speakers=None,
                   asr_fn=None, diar_fn=None):
    asr_fn = asr_fn or transcribe_audio
    diar_fn = diar_fn or diarize_mp3
    try:
        # 统一约定：diar_fn 直接收 mp3 路径，内部自己抽 wav
        diar = diar_fn(mp3_path, model_dir, ffmpeg_path, temp_dir, num_speakers)
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
