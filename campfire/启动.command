#!/bin/bash
# 篝火：双击启动（macOS）。第一次运行会自动下载 Python 和依赖。
cd "$(dirname "$0")" || exit 1
# ===== 篝火填写：每个工具不同 =====
TOOL_NAME="扫描 PDF 可搜索化"
PY_VERSION="3.12"
INSTALL_CMD="uv pip install ocrmypdf==17.13.0 streamlit==1.66.1 && python campfire_setup.py"
RUN_CMD="python campfire_run.py"
OPEN_URL="http://127.0.0.1:8501"
# ===================================
echo; echo "  $TOOL_NAME · 篝火出品"; echo "  第一次运行会自动下载 Python 和依赖，需要几分钟，请保持联网。"; echo
fail() { echo; echo "启动失败：请截图这个窗口，到 GitHub 仓库的 Issues 反馈。"; read -r -p "按回车关闭"; exit 1; }
if ! command -v uv >/dev/null 2>&1; then
  echo "正在安装 uv（Python 环境管理工具）..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ ! -f .venv/campfire-ready ]; then
  read -r -p "使用国内镜像加速下载依赖吗？直接回车表示使用 [Y/n]：" m
  [ "$m" = "n" ] || [ "$m" = "N" ] || export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
  uv venv --python "$PY_VERSION" .venv || fail
  source .venv/bin/activate
  eval "$INSTALL_CMD" || fail
  touch .venv/campfire-ready
else
  source .venv/bin/activate
fi
[ -n "$OPEN_URL" ] && (sleep 6; open "$OPEN_URL") &
echo "正在启动，关闭这个窗口即可退出。"
eval "$RUN_CMD"
