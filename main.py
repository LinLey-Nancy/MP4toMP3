import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
import os
import subprocess
import sys
# 全局变量，存储选择的文件夹路径
folder_path = ""

# 获取打包后的文件路径
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))  
    return os.path.join(base_path, relative_path)

def select_folder():
    global folder_path
    folder_path = filedialog.askdirectory(title="请选择包含视频的文件夹")
    if folder_path:
        label_path.config(text=folder_path)
        btn_main.config(state="normal")     
        progress["value"] = 0    
        
        if folder_path:
            # 统计视频数量并更新标签
            video_ext = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts")
            total = sum(1 for f in os.listdir(folder_path) if f.lower().endswith(video_ext))
            label_path.config(text=f"{folder_path}  \n（共 {total} 个视频文件）", justify="center")

            btn_main.config(text="开始转换", command=lambda: convert_folder(folder_path), style="Accent.TButton")           
        


# 转换函数
def convert_folder(input_folder):
    # 未选择警告
    if not input_folder:
        messagebox.showwarning("请先选择一个文件夹")
        return
    btn_main.config(state="disabled")
    progress["value"] = 0

    # 获取ffmpeg路径 创建输出文件夹
    ffmpeg_path = resource_path("ffmpeg.exe")
    out_folder = os.path.join(input_folder, "转换后的MP3文件")
    os.makedirs(out_folder, exist_ok=True)
    video_ext = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts")
    
    # 统计转换成功的文件数
    count = 0
    
    # 目录下没有视频文件警告
    files = [f for f in os.listdir(input_folder) if f.lower().endswith(video_ext)]
    total = len(files)
    if not total:
        messagebox.showinfo("提示", "目录下没有视频文件")
        btn_main.config(state="normal")
        return

    # 转换主程序
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

    messagebox.showinfo("完成", f"共转换 {count} 个文件\n已保存到 {folder_path}/mp3_output 文件夹")



# ----------------- GUI -----------------
root = tk.Tk()
root.title("视频转MP3")
root.geometry("400x160")
root.resizable(False, False)


btn_main = ttk.Button(
    root,
    text="选择文件夹",
    command=select_folder,
    width=20,          # 按钮文字区域宽度（字符）
    padding=(20, 8)    # 左右 20 px，上下 8 px
)
btn_main.pack(pady=15)

label_path = ttk.Label(root, text="还没选从哪里开始转换呢", anchor="center")
label_path.pack(fill="x", padx=20, pady=5)

progress = ttk.Progressbar(root, length=350, mode="determinate")
progress.pack(pady=10)

root.mainloop()