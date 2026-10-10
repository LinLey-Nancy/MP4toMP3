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
