import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv",
             ".m4v", ".ts", ".webm", ".mpeg", ".mpg", ".3gp")
OUTPUT_DIR = "mp3_output"

COLOR_IDLE = "#666666"
COLOR_BUSY = "#2b6cb0"
COLOR_OK = "#2e7d32"
COLOR_WARN = "#b0771a"
COLOR_ERROR = "#c0453e"

# ----------------- 全局状态 -----------------
selected = []         # 待转换视频的完整路径列表
out_dir = ""          # 输出目录
converting = False
cancel_requested = False
current_proc = None   # 正在运行的 ffmpeg 子进程，取消/退出时用来终止
current_out = None    # 正在输出的文件，取消/退出时清理半成品
job_token = 0         # 每次转换 +1，让旧的进度轮询自动失效

job_q = queue.Queue()
result_q = queue.Queue()

# GUI 控件，在 setup_gui() 中赋值
root = None
drop_area = None
label_path = None
label_status = None
label_pct = None
progress = None
btn_pick = None
btn_main = None
btn_cancel = None


def resource_path(rel):
    """兼容 PyInstaller 打包后的资源路径"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, rel)


def parse_drop_paths(data):
    """解析拖拽数据：带空格的路径被 {} 包住，其余按空白分隔。

    不用 tk.splitlist：Windows 反斜杠路径会被 Tcl 当转义符处理
    （\\x 是十六进制、\\v 是垂直制表符、\\2 是八进制），路径会被吃掉。
    """
    return [m.group(1) if m.group(1) is not None else m.group(2)
            for m in re.finditer(r"\{([^{}]*)\}|([^\s{}]+)", data or "")]


def collect_videos(paths):
    """把拖入/选择的路径（文件夹或视频文件，可混合多个）汇总成视频列表。"""
    videos, skipped = [], 0
    for p in paths:
        if os.path.isdir(p):
            try:
                videos.extend(os.path.join(p, f) for f in sorted(os.listdir(p))
                              if f.lower().endswith(VIDEO_EXT))
            except OSError:
                skipped += 1
        elif os.path.isfile(p) and p.lower().endswith(VIDEO_EXT):
            videos.append(p)
        else:
            skipped += 1
    return videos, skipped


def convert_one(in_path, out_path):
    """转换单个文件，返回是否成功。失败或被取消时清理半成品文件。"""
    global current_proc, current_out
    cmd = [resource_path("ffmpeg.exe"), "-y", "-i", in_path,
           "-vn", "-map", "0:a:0", "-q:a", "0", out_path]
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        return False
    current_proc, current_out = proc, out_path
    try:
        proc.wait()
    finally:
        current_proc = current_out = None
    ok = proc.returncode == 0 and not cancel_requested
    if not ok:
        try:
            os.remove(out_path)
        except OSError:
            pass
    return ok


def worker():
    while True:
        files, out_dir, token = job_q.get()
        try:
            total = len(files)
            ok_count, failed = 0, []
            if total:
                os.makedirs(out_dir, exist_ok=True)
            used = set()  # 不同来源的同名文件，输出名去重
            for i, in_path in enumerate(files, 1):
                if cancel_requested:
                    break
                name = os.path.basename(in_path)
                result_q.put(("status", token, i, total, name))
                stem = os.path.splitext(name)[0]
                out_name, n = stem + ".mp3", 2
                while out_name in used:
                    out_name = f"{stem}_{n}.mp3"
                    n += 1
                used.add(out_name)
                if convert_one(in_path, os.path.join(out_dir, out_name)):
                    ok_count += 1
                elif cancel_requested:
                    break
                else:
                    failed.append(name)
                result_q.put(("progress", token, int(i / total * 100)))
            if cancel_requested:
                result_q.put(("cancelled", token, ok_count, failed, total))
            else:
                result_q.put(("done", token, ok_count, failed, total))
        except Exception as exc:  # 线程不能死，任何异常都转成错误消息
            result_q.put(("error", token, str(exc)))


# ----------------- UI 行为 -----------------

def set_sources(paths):
    """接收一组路径（文件夹/视频文件，可混合），汇总出待转换列表。"""
    global selected, out_dir
    videos, skipped = collect_videos(paths)
    if not videos:
        label_status.config(text="没有找到视频文件哦", fg=COLOR_ERROR)
        btn_main.config(state="disabled")
        return
    selected = videos
    first = paths[0]
    base = first if os.path.isdir(first) else os.path.dirname(first)
    out_dir = os.path.join(base, OUTPUT_DIR)
    if len(paths) == 1 and os.path.isdir(first):
        label_path.config(text=f"{first}\n（共 {len(videos)} 个视频文件）")
    else:
        label_path.config(
            text=f"已选 {len(videos)} 个视频（来自 {len(paths)} 个位置）\n输出到：{out_dir}")
    note = f"已跳过 {skipped} 个非视频项，" if skipped else ""
    label_status.config(text=note + "准备就绪，点「开始转换」吧~", fg=COLOR_IDLE)
    btn_main.config(state="normal")


def select_folder():
    path = filedialog.askdirectory(title="请选择包含视频的文件夹")
    if path:
        set_sources([path])


def on_drop_event(event):
    if converting:
        label_status.config(text="正在转换中，稍后再拖哦~", fg=COLOR_WARN)
        return
    paths = parse_drop_paths(event.data)
    if not paths:
        messagebox.showwarning(
            "拖放失败",
            f"没有识别到拖入的内容~\n收到的原始数据：{event.data!r}")
        return
    set_sources(paths)


def start_convert():
    global converting, cancel_requested, job_token
    if converting or not selected:
        return
    converting = True
    cancel_requested = False
    job_token += 1
    set_progress(0)
    btn_pick.config(state="disabled")
    btn_main.config(state="disabled")
    btn_cancel.config(state="normal")
    label_status.config(text="准备转换…", fg=COLOR_BUSY)
    job_q.put((list(selected), out_dir, job_token))
    poll_progress(job_token)


def request_cancel():
    global cancel_requested
    if not converting:
        return
    cancel_requested = True
    btn_cancel.config(state="disabled")
    label_status.config(text="正在取消…", fg=COLOR_WARN)
    proc = current_proc
    if proc and proc.poll() is None:
        proc.terminate()


def set_progress(value):
    progress["value"] = value
    label_pct.config(text=f"{value}%")


def poll_progress(token):
    if token != job_token:  # 属于旧任务的轮询，直接终止
        return
    try:
        while True:
            msg = result_q.get_nowait()
            if msg[1] != token:
                continue
            kind = msg[0]
            if kind == "progress":
                set_progress(msg[2])
            elif kind == "status":
                _, _, i, total, name = msg
                label_status.config(text=f"正在转换 {i}/{total}：{name}",
                                    fg=COLOR_BUSY)
            elif kind == "done":
                _, _, ok, failed, total = msg
                finish_convert(ok, failed, total)
                return
            elif kind == "cancelled":
                _, _, ok, failed, total = msg
                finish_convert(ok, failed, total, cancelled=True)
                return
            elif kind == "error":
                finish_convert(0, [], 0, error=msg[2])
                return
    except queue.Empty:
        pass
    root.after(100, lambda: poll_progress(token))


def finish_convert(ok, failed, total, cancelled=False, error=None):
    global converting
    converting = False
    btn_pick.config(state="normal")
    btn_main.config(state="normal")
    btn_cancel.config(state="disabled")
    if error:
        label_status.config(text=f"出错了：{error}", fg=COLOR_ERROR)
        messagebox.showerror("转换出错", error)
    elif cancelled:
        label_status.config(text=f"已取消（完成 {ok}/{total} 个）", fg=COLOR_WARN)
        messagebox.showinfo("已取消", f"转换已取消~\n成功 {ok} 个，失败 {len(failed)} 个")
    elif total == 0:
        label_status.config(text="文件夹里没有视频哦", fg=COLOR_ERROR)
        messagebox.showinfo("没有视频", "这个文件夹里没有找到视频文件喵~")
    elif failed:
        label_status.config(text=f"完成：成功 {ok} 个，失败 {len(failed)} 个",
                            fg=COLOR_ERROR)
        names = "\n".join(failed[:10])
        if len(failed) > 10:
            names += f"\n…等 {len(failed)} 个"
        messagebox.showwarning("部分失败", f"成功 {ok} 个，失败 {len(failed)} 个：\n{names}")
    else:
        label_status.config(text=f"全部完成！共 {ok} 个视频已转换", fg=COLOR_OK)
        messagebox.showinfo("完成", "全部转换完毕！")


def on_closing():
    global cancel_requested
    if converting and not messagebox.askyesno(
            "退出程序", "正在转换中，退出会中断当前任务哦~\n\n确定退出吗？"):
        return
    cancel_requested = True
    proc = current_proc
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = current_out
    if out:
        try:
            os.remove(out)
        except OSError:
            pass
    root.destroy()
    os._exit(0)


# ----------------- GUI -----------------

def register_drop(widget):
    """递归注册拖放目标：tkdnd 按控件 HWND 投递，
    落在未注册的子控件上（标签/进度条/按钮）时事件不会触发。"""
    widget.drop_target_register(DND_FILES)
    widget.dnd_bind("<<Drop>>", on_drop_event)
    for child in widget.winfo_children():
        register_drop(child)


def setup_gui():
    global root, drop_area, label_path, label_status, label_pct, progress
    global btn_pick, btn_main, btn_cancel

    root = TkinterDnD.Tk()
    root.title("视频转MP3")
    root.geometry("480x340")
    root.resizable(False, False)

    style = ttk.Style(root)
    style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    drop_area = tk.Label(
        root, text="把文件夹或视频文件拖进来也可以哦~\n或点击下方「选择文件夹」",
        bg="#f5f7fa", fg="#8a94a6", relief="groove", bd=2,
        font=("Microsoft YaHei UI", 10), height=4)
    drop_area.pack(fill="x", padx=20, pady=(18, 6))

    label_path = tk.Label(root, text="还没有选择文件夹", fg="#333333",
                          font=("Microsoft YaHei UI", 9),
                          wraplength=440, justify="center")
    label_path.pack(fill="x", padx=20, pady=(4, 0))

    label_status = tk.Label(root, text="等待中…", fg=COLOR_IDLE,
                            font=("Microsoft YaHei UI", 9),
                            wraplength=440, justify="center")
    label_status.pack(fill="x", padx=20, pady=(6, 0))

    bar = tk.Frame(root)
    bar.pack(pady=(10, 4))
    progress = ttk.Progressbar(bar, length=380, mode="determinate")
    progress.pack(side="left")
    label_pct = tk.Label(bar, text="0%", width=5, fg="#555555",
                         font=("Microsoft YaHei UI", 9))
    label_pct.pack(side="left")

    btns = tk.Frame(root)
    btns.pack(pady=12)
    btn_pick = ttk.Button(btns, text="选择文件夹", command=select_folder, width=12)
    btn_pick.pack(side="left", padx=6)
    btn_main = ttk.Button(btns, text="开始转换", command=start_convert,
                          width=12, state="disabled", style="Accent.TButton")
    btn_main.pack(side="left", padx=6)
    btn_cancel = ttk.Button(btns, text="取消", command=request_cancel,
                            width=8, state="disabled")
    btn_cancel.pack(side="left", padx=6)

    register_drop(root)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    return root


def main():
    setup_gui()
    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
