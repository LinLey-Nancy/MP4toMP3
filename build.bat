@echo off
cd /d "%~dp0"
title 视频转MP3 - 一键构建

echo ==========================================
echo   视频转MP3  一键构建
echo ==========================================
echo.

REM ---- 0. 环境检查 ----
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

if not exist "main.py" (
    echo [错误] 当前目录缺少 main.py，请确认本脚本与 main.py 放在同一目录。
    pause
    exit /b 1
)

if not exist "ffmpeg.exe" (
    echo [错误] 当前目录缺少 ffmpeg.exe。
    echo        下载地址：https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo        解压后在 bin 目录里找到 ffmpeg.exe，放到本目录即可。
    pause
    exit /b 1
)

REM ---- 1. 依赖 ----
echo [1/3] 检查并安装依赖（pyinstaller / tkinterdnd2）...
python -m pip install --quiet --disable-pip-version-check pyinstaller tkinterdnd2
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络或 pip 配置后重试。
    pause
    exit /b 1
)

REM ---- 2. 清理旧构建 ----
echo [2/3] 清理旧构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"

REM ---- 3. 打包 ----
echo [3/3] 开始打包...
python -m PyInstaller --onefile --windowed --name "视频转MP3" --add-binary "ffmpeg.exe;." main.py
if errorlevel 1 (
    echo.
    echo [错误] 构建失败，请把上方日志截图反馈。
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   构建成功！产物：dist\视频转MP3.exe
echo ==========================================
explorer "dist"
pause
