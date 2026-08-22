#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE="${OPTIONS_FILE:-/data/options.json}"
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT

# All parsing/normalization happens inside a single Python process.
# The options file is read as JSON data (never interpolated into Python
# source code), which avoids the code-injection risk of building a
# Python literal out of a user-controlled string.
python3 - "$OPTIONS_FILE" "$ENV_FILE" <<'PY'
import json
import os
import sys

options_file, env_file = sys.argv[1], sys.argv[2]

defaults = {
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "",
    "model": "whisper-large-v3-turbo",
    "languages": "uk ru",
    "language_mode": "auto",
    "log_level": "INFO",
}

opts = {}
if os.path.isfile(options_file):
    with open(options_file, encoding="utf-8") as f:
        opts = json.load(f)

base_url = opts.get("base_url", defaults["base_url"])
api_key = opts.get("api_key", defaults["api_key"])
model = opts.get("model", defaults["model"])
lang_mode = opts.get("language_mode", defaults["language_mode"])
log_level = opts.get("log_level", defaults["log_level"])
raw_languages = opts.get("languages", defaults["languages"])

# Normalize languages: keep only uk/ru, dedupe, ensure uk is first.
allowed = []
for token in str(raw_languages).replace(",", " ").split():
    token = token.strip().lower()
    if token in ("uk", "ru") and token not in allowed:
        allowed.append(token)
if "uk" in allowed and allowed[0] != "uk":
    allowed.remove("uk")
    allowed.insert(0, "uk")
if "uk" not in allowed:
    allowed.insert(0, "uk")
if not allowed:
    allowed = ["uk", "ru"]
norm_languages = " ".join(allowed)


def sh_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


with open(env_file, "w", encoding="utf-8") as f:
    for key, value in (
        ("BASE_URL", base_url),
        ("API_KEY", api_key),
        ("MODEL", model),
        ("LANG_MODE", lang_mode),
        ("LOG_LEVEL", log_level),
        ("NORM_LANGS", norm_languages),
    ):
        f.write(f"{key}={sh_quote(value)}\n")
PY

# shellcheck disable=SC1090
source "$ENV_FILE"
rm -f "$ENV_FILE"

export WYOMING_URI="tcp://0.0.0.0:10300"
export WYOMING_LOG_LEVEL="$LOG_LEVEL"
export WYOMING_LANGUAGES="$NORM_LANGS"

export STT_OPENAI_URL="$BASE_URL"
export STT_OPENAI_KEY="$API_KEY"
export STT_MODELS="$MODEL"
export TTS_MODELS=""
export TTS_OPENAI_URL=""
export TTS_OPENAI_KEY=""

# language_mode=auto → do not force a single language via prompt;
# model auto-detects between advertised languages. Default preference = uk.
if [[ "$LANG_MODE" == "auto" ]]; then
  # Empty temperature / no fixed language hint — Whisper auto-detects
  # Prefer Ukrainian when ambiguous via mild prompt
  export STT_PROMPT="Prefer Ukrainian if the language is unclear between Ukrainian and Russian."
  echo "[wyoming-openai-stt] Language mode: auto (uk/ru, default preference uk)"
else
  # fixed → first language (uk)
  FIRST_LANG=$(echo "$NORM_LANGS" | awk '{print $1}')
  export STT_PROMPT=""
  echo "[wyoming-openai-stt] Language mode: fixed ($FIRST_LANG)"
fi

if [[ -z "$API_KEY" ]]; then
  echo "[wyoming-openai-stt] WARNING: API key is empty — set api_key in Configuration"
fi

echo "[wyoming-openai-stt] Starting STT-only proxy"
echo "[wyoming-openai-stt]   base_url  = $BASE_URL"
echo "[wyoming-openai-stt]   model     = $MODEL"
echo "[wyoming-openai-stt]   languages = $NORM_LANGS"
echo "[wyoming-openai-stt]   mode      = $LANG_MODE"

exec python -m wyoming_openai
