#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE="/data/options.json"

if [[ -f "$OPTIONS_FILE" ]]; then
  # Extract values with python (always present in the image)
  BASE_URL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('base_url', 'https://api.openai.com/v1'))")
  API_KEY=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('api_key', ''))")
  MODEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('model', 'whisper-1'))")
  LANGUAGES=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('languages', 'uk en'))")
  LOG_LEVEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('log_level', 'INFO'))")
else
  BASE_URL="https://api.openai.com/v1"
  API_KEY=""
  MODEL="whisper-1"
  LANGUAGES="uk en"
  LOG_LEVEL="INFO"
fi

export WYOMING_URI="tcp://0.0.0.0:10300"
export WYOMING_LOG_LEVEL="$LOG_LEVEL"
export WYOMING_LANGUAGES="$LANGUAGES"

# STT only — leave TTS models empty so the process skips TTS client
export STT_OPENAI_URL="$BASE_URL"
export STT_OPENAI_KEY="$API_KEY"
export STT_MODELS="$MODEL"
# Empty TTS → STT-only mode (supported since wyoming_openai 0.4.4+)
export TTS_MODELS=""
export TTS_OPENAI_URL=""
export TTS_OPENAI_KEY=""

echo "[wyoming-openai-stt] Starting STT-only proxy"
echo "[wyoming-openai-stt]   base_url = $BASE_URL"
echo "[wyoming-openai-stt]   model    = $MODEL"
echo "[wyoming-openai-stt]   languages= $LANGUAGES"

exec python -m wyoming_openai
