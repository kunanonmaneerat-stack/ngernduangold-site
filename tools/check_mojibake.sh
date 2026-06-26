#!/usr/bin/env bash
# Guard: fail if any repo text file contains U+FFFD (replacement char) — i.e. Thai
# corrupted by a non-UTF-8 write. Added 2026-06-27 after the 06-21 mojibake incident.
# Runs from anywhere (cd to repo root = this script's parent dir).
cd "$(dirname "$0")/.." || exit 2
hits=$(grep -rlI $'\357\277\275' . \
  --include='*.md' --include='*.txt' --include='*.json' --include='*.csv' \
  --include='*.py' --include='*.html' --include='*.js' --include='*.ps1' --include='*.cmd' \
  | grep -v '/.git/')
if [ -n "$hits" ]; then
  echo "MOJIBAKE FOUND:"
  echo "$hits"
  exit 1
fi
echo "mojibake check: clean"
