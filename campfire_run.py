"""篝火启动脚本调用：设置 Tesseract 路径和语言数据目录，然后启动上游自带的网页界面（misc/_webservice.py）。"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
env = os.environ
env["TESSDATA_PREFIX"] = str(ROOT / "tessdata")
for d in (r"C:\Program Files\Tesseract-OCR", r"C:\Program Files (x86)\Tesseract-OCR"):
    if Path(d).exists():
        env["PATH"] = d + os.pathsep + env["PATH"]
os.chdir(ROOT)
# 上游 misc/webservice.py 只是转调 streamlit；Windows 上它用 execvp 会让启动窗口提前结束，所以直接调用。
sys.exit(
    subprocess.call(
        [
            sys.executable, "-m", "streamlit", "run", str(ROOT / "misc" / "_webservice.py"),
            "--server.address", "127.0.0.1",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
    )
)
