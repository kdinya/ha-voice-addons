# Wyoming OpenAI STT

Speech-to-Text via any **OpenAI-compatible API** (Groq, OpenAI, LocalAI,
etc.), exposed to Home Assistant as a **Wyoming Protocol** STT service.

Port **10300**. Pairs well with **Voice Match** as its upstream.

---

## Languages: Ukrainian and Russian by default

Out of the box:
- languages: **`uk ru`**
- mode: **`auto`** — the model auto-detects between Ukrainian and Russian
- if it's unsure, **Ukrainian** is preferred (it's first in the list)

English and other languages are not used by default; set `languages` to
change this.

| `language_mode` | Behavior |
|---|---|
| **`auto`** | Auto-detect between the configured languages (recommended) |
| **`fixed`** | Always use the first language in the list |

Your Assist pipeline language can stay set to Ukrainian even in `auto`
mode — the add-on decides between `uk`/`ru` on its own.

---

## Configuration options

| Option | Description | Example |
|---|---|---|
| **`base_url`** | OpenAI-compatible API endpoint | `https://api.groq.com/openai/v1` |
| **`api_key`** | Provider API key (for Groq, from console.groq.com, starts with `gsk_`) | `gsk_...` |
| **`model`** | Model name at the provider | `whisper-large-v3-turbo` |
| **`languages`** | Space-separated languages; the first is preferred when ambiguous | `uk ru` |
| **`language_mode`** | `auto` or `fixed` | `auto` |
| **`log_level`** | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |

Field labels in Configuration are shown above each input, translated
according to your Home Assistant UI language.

### Recommended models

**Groq**
- `whisper-large-v3-turbo` — fast, accurate enough for voice assistants
- `whisper-large-v3` — more accurate, more tokens/cost

**OpenAI**
- `whisper-1`
- `gpt-4o-mini-transcribe`
- `gpt-4o-transcribe`

---

## If transcripts are inaccurate

1. Keep `language_mode: auto` with `languages: uk ru`.
2. Try the `whisper-large-v3` model.
3. Prefer Ukrainian as the Assist pipeline language.
4. Reduce background noise; speak clearly.
5. If Voice Match is in front of this add-on, try lowering its
   `extraction_threshold` (≈ 0.30) if it's cutting off words.

---

## Connecting it

1. Start the add-on.
2. Add a **Wyoming Protocol** integration on port **10300**, or set
   `upstream_uri = tcp://homeassistant:10300` in Voice Match.

Transcription will not work without a valid **`api_key`** — check the
add-on logs if nothing comes through.
