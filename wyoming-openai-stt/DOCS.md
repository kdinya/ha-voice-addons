# Wyoming OpenAI STT

Wyoming Speech-to-Text server that talks to any **OpenAI-compatible** API.

Works with:
- Official OpenAI (`whisper-1`, `gpt-4o-transcribe`, …)
- Groq
- LocalAI / Speaches / any self-hosted OpenAI-compatible endpoint

## Configuration

| Option | Description | Example |
|--------|-------------|---------|
| **base_url** | API base URL | `https://api.openai.com/v1` or `https://api.groq.com/openai/v1` |
| **api_key** | API key (password field) | `sk-...` or Groq key |
| **model** | Model name | `whisper-1`, `whisper-large-v3`, `gpt-4o-transcribe` |
| **languages** | Languages to advertise (space-separated) | `uk en` |
| **log_level** | Logging level | `INFO` |

## Recommended settings

**OpenAI**
- base_url: `https://api.openai.com/v1`
- model: `whisper-1` or `gpt-4o-mini-transcribe`

**Groq**
- base_url: `https://api.groq.com/openai/v1`
- model: `whisper-large-v3` (or current Groq Whisper model)

## After start

1. Settings → Devices & Services → Add Integration → **Wyoming Protocol**
2. Host: IP of Home Assistant (or `homeassistant`), Port: **10300**
3. In Voice Assistant pipeline choose this STT engine.

You can also point **Voice Match** (from the same repository) at this add-on by setting its `upstream_uri` to `tcp://homeassistant:10300`.

## Notes

- This add-on runs in **STT-only** mode (TTS is disabled).
- The underlying project is [roryeckel/wyoming_openai](https://github.com/roryeckel/wyoming_openai).
