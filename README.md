# HA Voice Add-ons

A small Home Assistant add-on repository for **speaker verification** and
**Speech-to-Text** over an OpenAI-compatible API (Groq, OpenAI, LocalAI, …).

**Repository:** https://github.com/kdinya/ha-voice-addons

| Add-on | Wyoming port | Purpose |
|---|---|---|
| **[Voice Match](voice-match/)** | `10350` | Verifies that it's really *you* talking, strips background noise / other speakers, then proxies the cleaned audio to an upstream Wyoming STT add-on. Fully self-contained. |
| **[Wyoming OpenAI STT](wyoming-openai-stt/)** | `10300` | Speech-to-Text (Ukrainian / Russian by default) via any OpenAI-compatible transcription API. |

## Installation

Tested with **Home Assistant OS**, Core `2026.8.x`, Supervisor `2026.07.x`, on
`amd64` and `aarch64`.

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add:
   ```
   https://github.com/kdinya/ha-voice-addons
   ```
3. Refresh the store, install the add-on(s) you need, and start them.
4. Add a **Wyoming Protocol** integration pointed at the relevant port.

### Typical pipeline

```
Home Assistant microphone
    → Voice Match (10350)            ← speaker verification
        → Wyoming OpenAI STT (10300) ← transcription (Groq / OpenAI / …)
            → Assist / automations
```

You can also use either add-on on its own — Voice Match works with any
Wyoming STT service as its upstream, and Wyoming OpenAI STT works as a
standalone Wyoming STT provider without Voice Match in front of it.

---

## Voice Match — quick overview

- Fully self-contained — no dependency on a third-party base image.
- **Hot-reload**: after enrolling a new voice, no add-on restart is needed.
- Runs on CPU only (`amd64` / `aarch64`) — no GPU required.
- Web UI (Ingress panel) for recording samples, checking their quality,
  enrollment, and managing voiceprints.
- First start takes 1–3 minutes while the ECAPA-TDNN model downloads into
  `/data`; subsequent starts are fast (cached).

**Setup:**
1. In Configuration, set **`upstream_uri`** ("Wyoming STT address"), e.g.
   `tcp://homeassistant:10300` — or use **Scan** in the web UI.
2. Open the **Voice Match** side-panel:
   - pick or create a speaker;
   - record from the microphone or upload files;
   - check sample quality;
   - **Enroll** → the voiceprint is active immediately.
3. Add a **Wyoming Protocol** integration on port **10350** and select
   Voice Match as the STT engine in your Assist pipeline.

| Option | Description | Default |
|---|---|---|
| `upstream_uri` | Where verified audio is forwarded | `tcp://homeassistant:10300` |
| `verify_threshold` | Voice similarity threshold (0–1); higher = stricter | `0.35` |
| `extraction_threshold` | Strips other voices/background before STT | `0.30` |
| `stt_languages` | Comma-separated languages advertised to HA | `uk,ru` |
| `require_speaker_match` | Reject audio from unenrolled speakers | `true` |
| `log_level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |

Full reference: [voice-match/DOCS.md](voice-match/DOCS.md).
Security notes: [SECURITY.md](SECURITY.md).

### Enrolling a voice

1. Pick an existing speaker or type a new name (lowercase, `a-z0-9_-`).
2. Record 3–5 samples (3–10 seconds of clean speech each).
3. **Check all samples** → remove any marked weak/bad.
4. **Enroll** → the voiceprint is created and **active immediately** (no
   restart required).

---

## Wyoming OpenAI STT — quick overview

- Speech-to-Text via any OpenAI-compatible transcription API (Groq, OpenAI,
  LocalAI, …).
- Ships tuned defaults for **Ukrainian / Russian** auto-detection, but you
  can point it at any model/language your provider supports.

| Option | Description | Example |
|---|---|---|
| `base_url` | OpenAI-compatible API endpoint | `https://api.groq.com/openai/v1` |
| `api_key` | Provider API key | `gsk_...` |
| `model` | Model name at the provider | `whisper-large-v3-turbo` |
| `languages` | Space-separated languages; first = preferred on ambiguity | `uk ru` |
| `language_mode` | `auto` (detect) or `fixed` (force first language) | `auto` |
| `log_level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |

Full reference: [wyoming-openai-stt/DOCS.md](wyoming-openai-stt/DOCS.md).

---

## Releases

Each add-on is versioned independently via its own `config.yaml`. Tagging a
commit on `main` triggers `.github/workflows/release.yml`, which builds a
GitHub Release with notes pulled from the matching `CHANGELOG.md` section.
CI (`.github/workflows/ci.yml`) runs on every push/PR: syntax checks, a
regression test for the `languages` code-injection fix, add-on smoke tests,
a check that `CHANGELOG.md` has an entry for the current `config.yaml`
version, and a Dockerfile lint + build for both add-ons.

## License

See [LICENSE](LICENSE).
