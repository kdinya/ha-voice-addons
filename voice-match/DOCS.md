# Voice Match

Speaker-verified ASR proxy for Home Assistant. Verifies that audio contains
*your* voice before allowing a command through, and strips TV/background
noise before forwarding the cleaned audio to your real Wyoming STT service.

Works with **any** Wyoming STT (Faster Whisper, OpenAI / Groq via wyoming-openai-stt, Vosk, etc.).

## Quick start

1. Install a Wyoming STT first (recommended: **Wyoming OpenAI STT** from this same repository, or official **Wyoming Faster Whisper**).
2. **Configuration** — set `upstream_uri` to the address of your STT (default `tcp://homeassistant:10300`) and languages (`stt_languages`: `uk` or `uk,en`).
3. **Start** the add-on.
4. Open the side panel **Voice Match** (Ingress) → upload 3–5 short recordings of your voice → click **Start enrollment**.
5. **Restart** the add-on so it loads the new voiceprint.
6. Settings → Devices & Services → **Wyoming Protocol** → host = Home Assistant IP (or `homeassistant`), port **10350**.
7. Settings → Voice Assistants → your pipeline → Speech-to-Text → **Voice Match**.

## Options

- **upstream_uri** — address of your real Wyoming STT service.
- **verify_threshold** (0.40) — voice similarity threshold. Higher = stricter.
- **extraction_threshold** (0.35) — threshold for extracting your voice from background.
- **stt_languages** — languages advertised to Home Assistant (comma-separated, e.g. `uk,en`).
- **require_speaker_match** — require voice match (disable for diagnostics).
- **tag_speaker** — prepend `[name]` to the transcript.
- **save_rejected** — keep rejected audio samples.
- **log_level** — logging level.

## Example upstream_uri values

| STT | upstream_uri |
|-----|--------------|
| Official Wyoming Faster Whisper | `tcp://homeassistant:10300` |
| Wyoming OpenAI STT (this repo) | `tcp://homeassistant:10300` |
| Other container on same host | `tcp://container_name:port` or `tcp://IP:port` |

## Enrollment via web UI

In the HA side panel open **Voice Match**. Then:

1. Enter speaker name (latin letters, `a-z0-9_-`).
2. Drag & drop or select audio files (.wav / .flac / .ogg / .mp3).
3. Click **Start enrollment**.
4. After success **restart the add-on**.

Recommended recordings: 16 kHz mono, 3–10 seconds, different tone/distance/volume, no strong background noise.

## Threshold tuning

- Foreign voice still passes → raise `verify_threshold` (0.45–0.55).
- Your own voice is often rejected → lower to 0.30–0.35.
