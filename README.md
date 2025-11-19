实现将一个文件夹内的视频文件批量转换为mp3

支持".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts"格式

双击 build.bat 进行构建

~~ffmpeg构建压缩包下载
https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip/~~

~~在其bin目录下找到ffmpeg.exe与main.py放在一起~~

~~使用 pyinstaller --onefile --windowed --add-binary "ffmpeg.exe;." main.py 进行构建~~

支持文件夹拖拽了捏
