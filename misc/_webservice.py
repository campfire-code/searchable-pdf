# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: AGPL-3.0-or-later

"""This is a simple web service/HTTP wrapper for OCRmyPDF.

This may be more convenient than the command line tool for some Docker users.
Note that OCRmyPDF uses Ghostscript, which is licensed under AGPLv3+. While
OCRmyPDF is under GPLv3, this file is distributed under the Affero GPLv3+ license,
to emphasize that SaaS deployments should make sure they comply with
Ghostscript's license as well as OCRmyPDF's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pikepdf
import streamlit as st

from ocrmypdf._defaults import DEFAULT_ROTATE_PAGES_THRESHOLD


def get_host_url_with_port(port: int) -> str:
    """Get the host URL for the web service. Hacky."""
    host_url = st.context.headers["host"]
    try:
        host, _streamlit_port = host_url.split(":", maxsplit=1)
    except ValueError:
        host = host_url
    return f"//{host}:{port}"  # Use the same protocol


# 篝火版：界面文字全部汉化。选项的取值（传给 ocrmypdf 的参数）保持原样，只把显示文字换成中文。
MODE_LABELS = {
    "normal": "常规（页面已有文字时会报错）",
    "skip-text": "跳过已有文字的页面",
    "force-ocr": "强制识别（已有文字也重新识别）",
    "redo-ocr": "重新识别（替换旧的文字层）",
}
LANGUAGE_LABELS = {
    "chi_sim+eng": "简体中文 + 英文",
    "eng": "英文",
    "chi_tra+eng": "繁体中文 + 英文",
    "chi_sim": "仅简体中文",
}
OUTPUT_TYPE_LABELS = {
    "pdfa": "PDF/A（归档格式，默认）",
    "pdf": "普通 PDF",
    "pdfa-1": "PDF/A-1",
    "pdfa-2": "PDF/A-2",
    "pdfa-3": "PDF/A-3",
    "none": "不生成文件",
}
RENDERER_LABELS = {
    "auto": "自动选择",
    "hocr": "逐词定位渲染",
    "hocrdebug": "逐词定位渲染（显示文字框，调试用）",
    "sandwich": "三明治渲染（图像加不可见文字层）",
}
OPTIMIZE_LABELS = {
    "0": "0（不优化）",
    "1": "1（无损优化）",
    "2": "2（有损优化，受下方质量设置影响）",
    "3": "3（最大程度压缩）",
}
COMPRESSION_LABELS = {"auto": "自动", "jpeg": "JPEG", "lossless": "无损"}
VERBOSE_LABELS = {-1: "安静", 0: "默认", 1: "调试", 2: "详细调试"}

st.title("扫描 PDF 可搜索化")
st.caption(
    "上传扫描版 PDF，识别文字后得到可以搜索、复制的 PDF。文件只在本机处理，不会上传到任何服务器。"
)

uploaded = st.file_uploader("上传要识别的 PDF", type=["pdf"], key="file")

# 篝火版：Streamlit 上传框自带的英文提示（按钮、拖放说明）没有中文开关，用样式把它们替换成中文。
# 只在还没选文件时注入：选好文件后上传框里只剩图标按钮，样式会把它们弄乱。
if uploaded is None:
    st.markdown(
        """
<style>
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
    content: "选择文件"; font-size: 1rem;
}
[data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 0 !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span::after {
    content: "把 PDF 文件拖到这里，每个文件不超过 200 MB"; font-size: 0.875rem;
}
[data-testid="stFileUploaderDropzoneInstructions"] small { display: none; }
</style>
""",
        unsafe_allow_html=True,
    )

mode = st.selectbox(
    "识别模式",
    options=["normal", "skip-text", "force-ocr", "redo-ocr"],
    format_func=MODE_LABELS.get,
)

pages = st.text_input(
    "页码范围", value="", help="只处理指定的页，页码用英文逗号分隔，例如 1,3,5-8；留空表示全部页"
)

with st.expander("输入选项"):
    invalidate_digital_signatures = st.checkbox("使数字签名失效", value=False)
    # 篝火版：语言选项改为启动脚本下载好的 chi_sim / chi_tra / eng
    language = st.selectbox(
        "识别语言",
        options=["chi_sim+eng", "eng", "chi_tra+eng", "chi_sim"],
        format_func=LANGUAGE_LABELS.get,
    )

    image_dpi = st.slider(
        "图片分辨率（DPI）",
        value=300,
        key="image_dpi",
        min_value=1,
        max_value=5000,
        step=50,
    )
with st.expander("预处理"):
    skip_big = st.checkbox("跳过过大的页面", value=False, key="skip_big")
    oversample = st.slider(
        "最低分辨率（DPI，低于此值会放大）", min_value=0, max_value=5000, value=0, step=50
    )
    rotate_pages = st.checkbox("自动旋转页面", value=False, key="rotate")
    deskew = st.checkbox("自动纠正倾斜", value=False, key="deskew")
    clean = st.checkbox("识别前清理页面", value=False, key="clean")
    clean_final = st.checkbox("把清理结果写入最终文件", value=False, key="clean_final")
    remove_vectors = st.checkbox("去除矢量图形", value=False, key="remove_vectors")


with st.expander("输出选项"):
    output_type = st.selectbox(
        "输出格式",
        options=["pdfa", "pdf", "pdfa-1", "pdfa-2", "pdfa-3", "none"],
        format_func=OUTPUT_TYPE_LABELS.get,
    )

    pdf_renderer = st.selectbox(
        "文字层渲染方式",
        options=["auto", "hocr", "hocrdebug", "sandwich"],
        format_func=RENDERER_LABELS.get,
    )

    optimize = st.selectbox(
        "文件体积优化", options=["0", "1", "2", "3"], format_func=OPTIMIZE_LABELS.get
    )

    st.selectbox(
        "PDF/A 压缩方式",
        options=["auto", "jpeg", "lossless"],
        format_func=COMPRESSION_LABELS.get,
    )

with st.expander("文档信息"):
    title = author = keywords = subject = None
    if uploaded:
        with pikepdf.open(uploaded) as pdf, pdf.open_metadata() as meta:
            st.code(str(meta), language="xml")
            title = st.text_input("标题", value=meta.get('dc:title', ''))
            author = st.text_input("作者", value=meta.get('dc:creator', ''))
            keywords = st.text_input("关键词", value=meta.get('dc:subject', ''))
            subject = st.text_input("主题", value=meta.get('dc:description', ''))
    else:
        st.caption("上传 PDF 后，这里会显示并允许修改文档信息。")


with st.expander("识别后的压缩"):
    jpeg_quality = st.slider(
        "JPEG 质量", min_value=0, max_value=100, value=75, key="jpeg_quality"
    )
    png_quality = st.slider(
        "PNG 质量", min_value=0, max_value=100, value=75, key="png_quality"
    )
    jbig2_threshold = st.number_input(
        "黑白图压缩阈值", value=0.85, key="jbig2_threshold"
    )

with st.expander("高级选项"):
    jobs = st.slider(
        "并行线程数",
        min_value=1,
        max_value=os.cpu_count(),
        value=os.cpu_count(),
        key="threads",
    )
    max_image_mpixels = st.number_input(
        "图片大小上限（百万像素）",
        value=250.0,
        min_value=0.0,
        help="超过这个大小的图片会被拒绝处理，单位是百万像素",
    )
    rotate_pages_threshold = st.number_input(
        "自动旋转的置信度阈值",
        value=DEFAULT_ROTATE_PAGES_THRESHOLD,
        min_value=0.0,
        max_value=1000.0,
        help="识别出的页面方向置信度达到这个值才会自动旋转",
    )
    fast_web_view = st.number_input(
        "网页快速浏览阈值（MB）",
        value=1.0,
        min_value=0.0,
        help="大于这个体积的文件会做线性化处理，方便边下载边浏览，单位是 MB",
    )
    continue_on_soft_render_error = st.checkbox(
        "页面渲染出现轻微错误时继续处理", value=True
    )
    verbose = st.selectbox(
        "日志详细程度",
        options=[-1, 0, 1, 2],
        index=1,
        format_func=VERBOSE_LABELS.get,
    )

if uploaded:
    args = []
    if mode and mode != 'normal':
        args.append(f"--{mode}")
    if language:
        args.append(f"--language={language}")
    if not uploaded.name.lower().endswith(".pdf") and image_dpi:
        args.append(f"--image-dpi={image_dpi}")
    if skip_big:
        args.append("--skip-big")
    if oversample:
        args.append(f"--oversample={oversample}")
    if rotate_pages:
        args.append("--rotate-pages")
    if deskew:
        args.append("--deskew")
    if clean:
        args.append("--clean")
    if clean_final:
        args.append("--clean-final")
    if remove_vectors:
        args.append("--remove-vectors")
    if output_type:
        args.append(f"--output-type={output_type}")
    if pdf_renderer:
        args.append(f"--pdf-renderer={pdf_renderer}")
    if optimize:
        args.append(f"--optimize={optimize}")
    if title:
        args.append(f"--title={title}")
    if author:
        args.append(f"--author={author}")
    if keywords:
        args.append(f"--keywords={keywords}")
    if subject:
        args.append(f"--subject={subject}")
    if pages:
        args.append(f"--pages={pages}")
    if max_image_mpixels:
        args.append(f"--max-image-mpixels={max_image_mpixels}")
    if rotate_pages_threshold:
        args.append(f"--rotate-pages-threshold={rotate_pages_threshold}")
    if fast_web_view:
        args.append(f"--fast-web-view={fast_web_view}")
    if continue_on_soft_render_error:
        args.append("--continue-on-soft-render-error")
    if verbose:
        args.append(f"--verbose={verbose}")
    if optimize > '0' and jpeg_quality:
        args.append(f"--jpeg-quality={jpeg_quality}")
    if optimize > '0' and png_quality:
        args.append(f"--png-quality={png_quality}")
    if jbig2_threshold:
        args.append(f"--jbig2-threshold={jbig2_threshold}")
    if jobs:
        args.append(f"--jobs={jobs}")
    # 篝火版：Windows 上不能让子进程打开仍被占用的 NamedTemporaryFile，改用临时目录
    with TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / f"input_{Path(uploaded.name).name}"
        input_file.write_bytes(uploaded.getvalue())
        args.append(str(input_file))
        if True:
            output_file = Path(tmpdir) / "output.pdf"
            args.append(str(output_file))

            # 篝火版：去掉上游的 disabled 逻辑。新版 streamlit 下点击的同一轮里按钮
            # 已被禁用，点击不会触发任何处理。
            if st.button("开始识别", key='run_button'):
                st.session_state['running'] = True
                args = [sys.executable, '-u', '-m', "ocrmypdf"] + args

                proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                with st.container(border=True):
                    while proc.poll() is None:
                        line = proc.stderr.readline()
                        if line:
                            st.html(
                                "<code>"
                                + line.decode("utf-8", errors="replace").strip()
                                + "</code>"
                            )

                if proc.returncode != 0:
                    st.error(f"识别失败，退出码 {proc.returncode}。请查看上方的日志。")
                    st.session_state['running'] = False
                    st.stop()

                if not output_file.exists() or output_file.stat().st_size == 0:
                    st.error("没有生成输出文件，请查看上方的日志。")
                    st.stop()

                st.download_button(
                    label="下载识别后的 PDF",
                    data=output_file.read_bytes(),
                    file_name=uploaded.name,
                    mime="application/pdf",
                )
                st.session_state['running'] = False
