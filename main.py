import tkinter as tk
from tkinter import filedialog, messagebox
import os
import subprocess
import sys

def resource_path(relative_path):
    """获取打包后的资源路径"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def convert_folder(input_folder):
    ffmpeg_path = resource_path("ffmpeg.exe")
    out_folder = os.path.join(input_folder, "mp3_output")
    os.makedirs(out_folder, exist_ok=True)

    video_ext = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts")
    count = 0

    for file in os.listdir(input_folder):
        if file.lower().endswith(video_ext):
            in_path  = os.path.join(input_folder, file)
            out_path = os.path.join(out_folder, f"{os.path.splitext(file)[0]}.mp3")
            try:
                subprocess.run(
                    [ffmpeg_path, "-i", in_path, "-q:a", "0", "-map", "a", out_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                count += 1
            except subprocess.CalledProcessError:
                continue   # 跳过有问题的文件

    messagebox.showinfo("完成", f"共转换 {count} 个文件\n已保存到 mp3_output 文件夹")

def select_folder():
    folder = filedialog.askdirectory(title="请选择包含视频的文件夹")
    if folder:
        convert_folder(folder)

# ----------------- GUI -----------------
root = tk.Tk()
root.title("视频转MP3 便携版")
root.geometry("300x100")
btn = tk.Button(root, text="选择文件夹→批量转MP3", command=select_folder)
btn.pack(expand=True)
root.mainloop()