# 视频转MP3

把一个文件夹内的视频批量转换为 MP3，输出到 `mp3_output/`（与视频同级，拖文件时输出到文件所在目录下）。

支持格式：`.mp4` `.mkv` `.avi` `.mov` `.flv` `.wmv` `.m4v` `.ts` `.webm` `.mpeg` `.mpg` `.3gp`

## 使用

- 把**文件夹或视频文件**拖进窗口任意位置（可一次拖多个，自动汇总），或点击「选择文件夹」
- 点击「开始转换」，过程中可随时「取消」
- 已存在的同名 MP3 会被直接覆盖；多音轨视频取第一条音轨
- 转换结束后会报告成功/失败数量及失败文件名

## 构建

双击 `build.bat` 即可一键构建，脚本会自动：

1. 检查 Python、`main.py`、`ffmpeg.exe` 是否就位
2. 安装依赖（`pyinstaller`、`tkinterdnd2`）
3. 清理旧构建文件并打包

产物为 `dist\视频转MP3.exe`（已内置 ffmpeg，无需额外安装）。

> 手动准备 ffmpeg：下载 https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip ，
> 解压后在 `bin` 目录里找到 `ffmpeg.exe` 放到本目录。

## 转写功能

勾选「转写文字（识别说话人）」后，MP3 转换完成会自动进入语音转写：

- 语音识别用 faster-whisper（默认 small 模型），说话人分离用 sherpa-onnx
- 输出到 `mp3_output\transcript_output\`，每个 MP3 对应一个同名 `.txt`，按说话人分段并带时间戳
- 「说话人数」可选「自动」或 2–5，说话人数固定时分离更准
- 首次转写需联网下载模型（说话人分离约 35MB，语音识别约 460MB），下载一次后离线可用
- 模型保存在程序同级 `models\` 目录（打包版为 exe 同级），临时 wav 放 `temp\`（启动时自动清空）

开发环境依赖：`pip install -r requirements-transcribe.txt`

命令行也可以直接转写已有的 MP3 目录：

```bash
.venv\Scripts\python -m transcribe <mp3目录> --profile small --speakers 2
```

## 双发行包（build-transcribe.bat）

双击 `build-transcribe.bat` 一键构建转写版发行包（onedir 模式，已内置 ffmpeg）：

1. PyInstaller 打包到 `dist\MP4toMP3\`
2. 先打出**迷你包** `dist\MP4toMP3-mini.zip`（不含模型）
3. 再用 `tools\build_manifest.py` 生成模型 sha256 清单、把 `models\` 拷入，打出**全量包** `dist\MP4toMP3-full.zip`

| 包 | 内容 | 适用场景 |
| --- | --- | --- |
| `MP4toMP3-mini.zip` | 仅程序本体 | 体积小；首次转写时联网下载模型，之后离线可用 |
| `MP4toMP3-full.zip` | 程序 + 全部模型（含 sha256 清单） | 解压即用，全程无需联网 |

两种包都是 CPU 基线版，在 N 卡机器上也能直接跑；CUDA 加速需另装 cuBLAS/cuDNN，属二期可选项。
