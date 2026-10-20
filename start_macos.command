#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
python3 scripts/launch.py
if [ $? -ne 0 ]; then
  read "?Startup failed. Press Enter to close this window."
fi
