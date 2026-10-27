#!/bin/zsh
# 双击启动绝区零一条龙（macOS） 已在运行时不重复启动
cd "$(dirname "$0")/../.." || exit 1
if pgrep -f 'zzz_od/gui/app.py' >/dev/null; then
  echo '一条龙已经在运行'
  exit 0
fi
mkdir -p .log
PYTHONPATH=src nohup uv run python src/zzz_od/gui/app.py > .log/gui_launch.log 2>&1 < /dev/null &
echo '已启动 日志见 .log/gui_launch.log'
