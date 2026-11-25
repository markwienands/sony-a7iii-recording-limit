#!/bin/sh
# Fetch the pinned Sony-PMCA-RE source, apply one small fix, install dependencies.
set -eu
cd "$(dirname "$0")"
REV=a82f5baaa8e9c3d9f28f94699e860fb2e48cc8e0
if [ ! -d Sony-PMCA-RE ]; then
  git clone https://github.com/ma1co/Sony-PMCA-RE.git
fi
git -C Sony-PMCA-RE checkout -q --detach "$REV"
if ! git -C Sony-PMCA-RE apply --reverse --check "$PWD"/patches/*.patch 2>/dev/null; then
  git -C Sony-PMCA-RE apply "$PWD"/patches/*.patch
fi
python3 -m venv venv
venv/bin/python -m pip install -q -r requirements.txt
venv/bin/python -I tests/test_offline.py
echo "Setup complete. Read README.md, then start with: ./run.sh check"
