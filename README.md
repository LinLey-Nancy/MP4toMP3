实现将一个文件夹内的mp4文件批量转换为mp3

ffmpeg构建压缩包下载
https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

在其bin目录下找到ffmpeg.exe与main.py放在一起
（上面也有）

使用 pyinstaller --onefile --windowed --add-binary "ffmpeg.exe;." main.py 进行构建
