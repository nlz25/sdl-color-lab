#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
python3 scripts/launch.py
if [ $? -ne 0 ]; then
  read "?启动失败，按回车关闭窗口。"
fi
