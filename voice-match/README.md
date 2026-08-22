# Voice Match

Speaker verification for Home Assistant. Checks that it's really *you*
talking, strips out background noise and other people's voices, then
forwards the cleaned audio to a Wyoming STT add-on (for example
**Wyoming OpenAI STT**).

```
Microphone → Voice Match (port 10350) → Wyoming STT (e.g. 10300) → Home Assistant
```

- Fully self-contained — no dependency on a third-party base image.
- **Hot-reload**: after enrolling a new voice, no add-on restart is needed.
- Runs on CPU only (amd64 / aarch64) — no GPU required.
- Web UI (Ingress panel) for recording samples, checking their quality,
  enrollment, and managing voiceprints.

See [DOCS.md](DOCS.md) for full setup and configuration instructions, and
[../SECURITY.md](../SECURITY.md) for what data is stored and where.
