#!/usr/bin/env bash
# Guard: fail if any repo text file is CORRUPTED Thai. Two checks:
#   (1) contains U+FFFD (EF BF BD) replacement char, OR
#   (2) is invalid UTF-8 (e.g. a dangling/truncated multibyte that the EF-BF-BD grep
#       cannot see). Detection MUST use real UTF-8 validation, not only the grep.
# Added 2026-06-27; iconv validity pass added Round 2 (a lone 0xE0 must fail this).
# Runs from anywhere (cd to repo root = this script's parent dir).
cd "$(dirname "$0")/.." || exit 2

INCL=(--include='*.md' --include='*.txt' --include='*.json' --include='*.csv' \
      --include='*.py' --include='*.html' --include='*.js' --include='*.ps1' --include='*.cmd')

# (1) EF BF BD (U+FFFD) replacement char
fffd=$(grep -rlI $'\357\277\275' . "${INCL[@]}" | grep -v '/.git/')

# (2) real UTF-8 validity — catches dangling/truncated multibyte
inv=$(find . -path ./.git -prune -o \
        \( -name '*.md' -o -name '*.txt' -o -name '*.json' -o -name '*.csv' \
           -o -name '*.py' -o -name '*.html' -o -name '*.js' -o -name '*.ps1' -o -name '*.cmd' \) -print \
      | grep -v '/.git/' \
      | while read -r f; do iconv -f utf-8 -t utf-8 "$f" >/dev/null 2>&1 || echo "$f"; done)

rc=0
if [ -n "$fffd" ]; then echo "MOJIBAKE FOUND (U+FFFD):"; echo "$fffd"; rc=1; fi
if [ -n "$inv" ];  then echo "INVALID UTF-8 (dangling/truncated multibyte):"; echo "$inv"; rc=1; fi
[ "$rc" = 0 ] && echo "mojibake check: clean"
exit $rc
