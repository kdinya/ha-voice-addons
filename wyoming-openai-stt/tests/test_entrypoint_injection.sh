#!/usr/bin/env bash
# Regression test for the languages code-injection fix in entrypoint.sh.
#
# Writes a malicious /data/options.json-style file where "languages"
# contains a Python string-literal breakout payload, then runs only the
# option-parsing portion of entrypoint.sh (everything up to, but not
# including, `exec python -m wyoming_openai`, which isn't installed here)
# and asserts that:
#   1. the payload's side effect (creating $CANARY) never happens, and
#   2. languages are still normalized to a safe "uk ru"-style value.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

CANARY="$WORKDIR/pwned"
OPTIONS_FILE="$WORKDIR/options.json"

# Payload: if the old code re-interpolated $LANGUAGES into a Python source
# string, this would close the triple-quoted string, run arbitrary code
# (touch the canary file), then re-open a string so the rest of the
# original source still parses.
python3 - "$OPTIONS_FILE" "$CANARY" <<'PY'
import json, sys
options_file, canary = sys.argv[1], sys.argv[2]
payload = "uk''';import pathlib;pathlib.Path(%r).write_text('pwned');x='''" % canary
json.dump({
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "test-key",
    "model": "whisper-large-v3-turbo",
    "languages": payload,
    "language_mode": "auto",
    "log_level": "INFO",
}, open(options_file, "w"))
PY

# Run only the option-parsing part of entrypoint.sh: everything before the
# final `exec python -m wyoming_openai` line.
PARSE_ONLY="$WORKDIR/parse_only.sh"
sed '/^exec python -m wyoming_openai$/d' "$ADDON_DIR/entrypoint.sh" > "$PARSE_ONLY"
chmod +x "$PARSE_ONLY"

OPTIONS_FILE_OVERRIDE="$OPTIONS_FILE" \
  bash -c "OPTIONS_FILE='$OPTIONS_FILE' bash '$PARSE_ONLY'" > "$WORKDIR/out.log" 2>&1 || {
    echo "FAIL: entrypoint parsing exited non-zero"
    cat "$WORKDIR/out.log"
    exit 1
  }

if [[ -f "$CANARY" ]]; then
  echo "FAIL: injection payload executed — canary file was created"
  exit 1
fi

if ! grep -q "languages = uk" "$WORKDIR/out.log"; then
  echo "FAIL: expected normalized languages starting with 'uk' in output"
  cat "$WORKDIR/out.log"
  exit 1
fi

echo "PASS: languages injection payload was not executed; output was normalized safely"
