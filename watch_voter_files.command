#!/bin/zsh
cd "$(dirname "$0")" || exit 1
mkdir -p inbox
exec .venv/bin/python scripts/local_update.py --inbox inbox --watch --push
