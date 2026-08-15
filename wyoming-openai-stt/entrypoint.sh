#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE="/data/options.json"

if [[ -f "$OPTIONS_FILE" ]]; then
  BASE_URL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('base_url', 'https://api.groq.com/openai/v1'))")
  API_KEY=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('api_key', ''))")
  MODEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('model', 'whisper-large-v3-turbo'))")
  LANGUAGES=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('languages', 'uk ru'))")
  LANG_MODE=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('language_mode', 'auto'))")
  LOG_LEVEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('log_level', 'INFO'))")
else
  BASE_URL="https://api.groq.com/openai/v1"
  API_KEY=""
  MODEL="whisper-large-v3-turbo"
  LANGUAGES="uk ru"
  LANG_MODE="auto"
  LOG_LEVEL="INFO"
fi

# Normalize languages: ensure uk is first (default)
# Keep only uk and ru if user passed extras
NORM_LANGS=$(python3 -c "
langs = '''$LANGUAGES'''.replace(',', ' ').split()
allowed = []
for x in langs:
    x = x.strip().lower()
    if x in ('uk', 'ru') and x not in allowed:
        allowed.append(x)
if 'uk' not in allowed:
    allowed.insert(0, 'uk')
elif allowed[0] != 'uk' and 'uk' in allowed:
    allowed.remove('uk')
    allowed.insert(0, 'uk')
if not allowed:
    allowed = ['uk', 'ru']
print(' '.join(allowed))
")

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
