# HA Voice Add-ons

Home Assistant add-on repository with two complementary voice tools:

| Add-on | Purpose | Port |
|--------|---------|------|
| **Voice Match** | Speaker verification + noise stripping proxy | 10350 |
| **Wyoming OpenAI STT** | OpenAI / Groq / any OpenAI-compatible STT | 10300 |

They work great together: install OpenAI STT → point Voice Match at it → only your voice is accepted.

---

## Installation (one time)

1. Open **Settings → Add-ons → Add-on Store**
2. Click the **⋮** (three dots) → **Repositories**
3. Paste the URL of this repository:
   ```
   https://github.com/kdinya/ha-voice-addons
   ```
4. Click **Add**

Or use the button (after you publish the repo):

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkdinya%2Fha-voice-addons)

---

## Recommended setup (simplest path)

### 1. Install Wyoming OpenAI STT

1. In Add-on Store find **Wyoming OpenAI STT** → Install
2. Configuration:
   - **base_url**: `https://api.groq.com/openai/v1` (or OpenAI)
   - **api_key**: your key
   - **model**: `whisper-large-v3` (Groq) or `whisper-1` (OpenAI)
   - **languages**: `uk en`
3. Start the add-on

### 2. Install Voice Match

1. Find **Voice Match** → Install
2. Configuration:
   - **upstream_uri**: `tcp://homeassistant:10300` (points to the STT above)
   - **stt_languages**: `uk` or `uk,en`
3. Start

### 3. Enroll your voice

1. Open the side panel **Voice Match**
2. Enter a name (latin letters)
3. Upload 3–5 short recordings of your voice
4. Click **Start enrollment**
5. Restart the Voice Match add-on

### 4. Connect to Home Assistant

1. **Settings → Devices & Services → Add Integration → Wyoming Protocol**
   - Host = IP of your HA (or `homeassistant`)
   - Port = **10350** (Voice Match)
2. **Settings → Voice Assistants** → your pipeline → Speech-to-Text → **Voice Match**

Done. Only your voice will be accepted; background TV / other people are filtered.

---

## Using only one of the add-ons

- **Only OpenAI STT** — install it, add Wyoming Protocol on port 10300, select it in the pipeline.
- **Only Voice Match** — you still need *any* Wyoming STT (official Faster Whisper, another container, etc.) and set its address in `upstream_uri`.

---

## Ports summary

| Service | Port | What to put in Wyoming Protocol |
|---------|------|---------------------------------|
| Wyoming OpenAI STT | 10300 | Direct STT |
| Voice Match | 10350 | Verified STT (recommended) |

---

## Credits

- Voice Match is based on [jxlarrea/wyoming-voice-match](https://github.com/jxlarrea/wyoming-voice-match)
- Wyoming OpenAI STT uses [roryeckel/wyoming_openai](https://github.com/roryeckel/wyoming_openai)
