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
