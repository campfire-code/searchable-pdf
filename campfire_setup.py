"""篝火启动脚本调用（只在第一次安装时运行）：检查 Tesseract，并准备中文识别数据。

Tesseract 的 tessdata 目录里没有中文时，把 eng / osd / chi_sim / chi_tra 放进项目自己的
tessdata 目录（同时复制系统 tessdata 里的 configs，OCRmyPDF 要用），启动时由 campfire_run.py
指给 Tesseract。
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESSDATA = ROOT / "tessdata"
LANGS = ["eng", "osd", "chi_sim", "chi_tra"]
BASE = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/"
MIRRORS = ["https://ghfast.top/" + BASE, BASE]  # 国内直连 GitHub 可能很慢，先试镜像
WIN_DIRS = [r"C:\Program Files\Tesseract-OCR", r"C:\Program Files (x86)\Tesseract-OCR"]


def find_tesseract():
    exe = shutil.which("tesseract")
    if exe:
        return Path(exe)
    for d in WIN_DIRS:
        p = Path(d) / "tesseract.exe"
        if p.exists():
            return p
    return None


def system_tessdata(exe):
    out = subprocess.run([str(exe), "--list-langs"], capture_output=True, text=True, errors="replace")
    for line in (out.stdout + out.stderr).splitlines():
        if line.startswith("List of available languages in"):
            return Path(line.split('"')[1])
    return None


def download(lang):
    dest = TESSDATA / f"{lang}.traineddata"
    if dest.exists() and dest.stat().st_size > 100000:
        return
    for prefix in MIRRORS:
        try:
            print(f"下载语言数据 {lang} ...")
            with urllib.request.urlopen(prefix + f"{lang}.traineddata", timeout=60) as r:
                data = r.read()
            if len(data) > 100000:
                dest.write_bytes(data)
                return
        except Exception as e:  # noqa: BLE001
            print(f"  失败（{e}），换下一个地址")
    sys.exit(f"语言数据 {lang} 下载失败，请检查网络后重新双击启动脚本。")


def main():
    exe = find_tesseract()
    if exe is None:
        sys.exit(
            "没有找到 Tesseract。请先安装：\n"
            "  Windows：winget install UB-Mannheim.TesseractOCR（或到 https://github.com/UB-Mannheim/tesseract/wiki 下载安装包）\n"
            "  Mac：brew install tesseract\n"
            "装好后重新双击启动脚本。"
        )
    print(f"找到 Tesseract：{exe}")
    TESSDATA.mkdir(exist_ok=True)
    sysdir = system_tessdata(exe)
    if sysdir is None or not (sysdir / "configs").exists():
        sys.exit("读不到 Tesseract 自带的 tessdata/configs 目录，请确认 Tesseract 安装完整。")
    for name in ("configs", "tessconfigs"):
        if (sysdir / name).exists():
            shutil.copytree(sysdir / name, TESSDATA / name, dirs_exist_ok=True)
    for lang in LANGS:
        download(lang)
    print("准备完成。")


if __name__ == "__main__":
    main()
