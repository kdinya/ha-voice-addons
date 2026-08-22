# Wyoming OpenAI STT

Speech-to-Text for Home Assistant via any **OpenAI-compatible API** (Groq,
OpenAI, LocalAI, …), exposed as a **Wyoming Protocol** STT service on port
**10300**.

```
Wyoming Protocol integration (or Voice Match) → Wyoming OpenAI STT (port 10300) → your API provider
```

- Tuned defaults for **Ukrainian / Russian** auto-detection, with a mild
  preference for Ukrainian when the model is unsure — but any
  model/language your provider supports can be configured.
- Options are parsed once from `/data/options.json` as JSON data (never
  interpolated into shell/Python source), so a crafted option value can't
  be used to inject code into the container.
- Pairs directly with **Voice Match** as its upstream, or works standalone
  as a Wyoming STT provider.

See [DOCS.md](DOCS.md) for full configuration and troubleshooting, and
[../SECURITY.md](../SECURITY.md) for what data is stored and where.
