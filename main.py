import os
import subprocess
import sys
import threading, queue, subprocess, os, sys
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import *
import tkinter as tk
# 全局变量，存储选择的文件夹路径
folder_path = ""
# 任务队列
job_q = queue.Queue()
# 结果队列
result_q = queue.Queue()

# 获取打包后的文件路径
def resource_path(rel):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))  
    return os.path.join(base_path, rel)

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

            btn_main.config(text="开始转换", command=lambda: start_convert(), style="Accent.TButton")           
        


def worker():
    while True:
        folder = job_q.get()          # 阻塞等待任务
        video_ext = (".mp4",".mkv",".avi",".mov",".flv",".wmv",".m4v",".ts")
        files = [f for f in os.listdir(folder) if f.lower().endswith(video_ext)]
        total = len(files)
        for i, file in enumerate(files, 1):
            in_path  = os.path.join(folder, file)
            out_path = os.path.join(folder, "mp3_output",
                                    f"{os.path.splitext(file)[0]}.mp3")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            try:
                subprocess.run(
                    [resource_path("ffmpeg.exe"), "-i", in_path,
                     "-q:a", "0", "-map", "a", out_path],
                    check=True, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            except subprocess.CalledProcessError:
                pass
            result_q.put(int((i + 1) / total * 100))
        result_q.put("done")                     # 通知完成

threading.Thread(target=worker, daemon=True).start()

def poll_progress():
    try:
        val = result_q.get_nowait()   # 非阻塞取消息
        if val == "done":
            messagebox.showinfo("完成", "全部转换完毕！")
            btn_main.config(state="normal", text="选择文件夹",
                            command=select_folder, style="TButton")
            progress["value"] = 0
            return
        progress["value"] = val
    except queue.Empty:
        pass
    root.after(100, poll_progress)   # 每 100 ms 回来检查一次

def start_convert():
    if not folder_path:
        return
    btn_main.config(state="disabled")
    progress["value"] = 0
    job_q.put(folder_path)     # 把任务丢给线程
    poll_progress()            # 开始轮询进度


# ----------------- GUI -----------------

root = TkinterDnD.Tk()
root.title("视频转MP3")
root.geometry("400x160")
root.resizable(False, False)

# 拖拽文件夹
root.drop_target_register(DND_FILES)
root.dnd_bind('<<Drop>>', lambda event: on_drop_event(event))

def on_drop_event(event):
    path = event.data

    # Windows 会把路径用 {} 包起来，或者多个路径用空格分隔
    if path.startswith('{') and path.endswith('}'):
        path = path[1:-1]
    else:
        # 可能拖了多个，只取第一个
        path = path.split()[0]
    
    # 去掉多余的引号或大括号
    path = path.strip('{}"\'').replace('\\', '/')

    if os.path.isdir(path):
        global folder_path
        folder_path = path

        video_ext = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts")
        total = sum(1 for f in os.listdir(folder_path) if f.lower().endswith(video_ext))
        label_path.config(text=f"{folder_path}  \n（共 {total} 个视频文件）", justify="center")
        btn_main.config(state="normal", text="开始转换", 
                        command=lambda: start_convert(), style="Accent.TButton")
    else:
        messagebox.showwarning("不是文件夹", "请拖拽一个包含视频的文件夹进来喵~")

btn_main = ttk.Button(
    root,
    text="选择文件夹",
    command=select_folder,
    width=20,          # 按钮文字区域宽度（字符）
    padding=(20, 8)    # 左右 20 px，上下 8 px
)
btn_main.pack(pady=15)

label_path = ttk.Label(root, text="丢一个文件夹进来也可以哦~", anchor="center")
label_path.pack(fill="x", padx=20, pady=5)

progress = ttk.Progressbar(root, length=360, mode="determinate")
progress.pack(pady=10)

# 关闭窗口时的确认提示
def on_closing():
    if messagebox.askyesno("退出程序", "\n如果正在转换，任务会中断哦~"):
        root.destroy() 
        # 结束所有线程 防止占用
        os._exit(0)

root.protocol("WM_DELETE_WINDOW", on_closing)

root.mainloop()