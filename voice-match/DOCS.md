# Voice Match

Speaker verification for Home Assistant: confirms that it's really *you*
talking, strips out background noise and other people's voices, then
forwards the cleaned audio to a Wyoming STT add-on (for example
**Wyoming OpenAI STT**).

The add-on sits in front of your STT engine as a proxy:

```
Microphone → Voice Match (port 10350) → Wyoming STT (e.g. port 10300) → Home Assistant
```

**First start:** downloading the ECAPA-TDNN model from Hugging Face can take
**1–3 minutes** depending on your network. It's cached in `/data/hf_cache`
and `/data/models`, so later starts are fast.

Compatibility: Home Assistant OS, Core `2026.8.x`, Supervisor `2026.07.x`
(`amd64` / `aarch64`).

## Quick start

1. Install and start **Wyoming OpenAI STT** (or any other Wyoming STT
   add-on).
2. In Voice Match's Configuration, set **`upstream_uri`** ("Wyoming STT
   address"): `tcp://homeassistant:10300` — or click **Scan** in the web UI
   and copy the URI it finds.
3. Open the **Voice Match** side panel (Ingress):
   - pick an existing speaker or type a new lowercase name;
   - record 3–5 samples from the microphone, **or** upload files;
   - click **Check all samples** and remove anything marked bad/weak;
   - **Enroll** → the voiceprint appears and is **active immediately**
     (hot-reload, no restart needed).
4. In Home Assistant: **Settings → Devices & services → Add integration →
   Wyoming Protocol**, host `homeassistant` (or its IP), port **10350**.
5. In your Assist pipeline, select **Voice Match** as the STT engine.

## Recording and enrollment in the web UI

1. **Speaker** — pick an existing one or type a new name (`a-z`, `0-9`, `_`,
   `-`, up to 32 characters).
2. **Record from microphone**: Record → speak for 3–10 s → Stop → Check →
   Save as WAV.
3. Or **Files from disk** — any common audio format is accepted; the server
   converts it to WAV 16 kHz mono.
4. The **Samples** section (section 5) always shows the samples of the
   *currently selected* speaker only. Nothing is shown, and **Check all
   samples** is disabled, until a speaker is selected.
5. **Check all samples** — scores each sample already listed (duration,
   sample rate, loudness, clipping) and color-codes it green/yellow/red *in
   place* — it does not add a second list. Each sample row has its own
   **Delete** button.
6. Keep **3–5** samples with an OK status.
7. **Enroll** — creates a voiceprint (a file under `/data/voiceprints/`).
   It's **active immediately** — no add-on restart required.

No voiceprint is created without Enrollment. After enrolling or deleting a
voiceprint, the change is picked up automatically (hot-reload).

If you record samples and close the tab without enrolling, the browser may
ask you to confirm (so you don't lose unsaved work).

## Any-voice mode (pure proxy)

Turn off **`require_speaker_match`** ("Require speaker match") in
Configuration. The add-on then stops rejecting unrecognized voices and
behaves as a plain proxy that still applies segment extraction depending on
the configured thresholds.

## Configuration options

| Option | Description | Default |
|---|---|---|
| **`upstream_uri`** | Where cleaned audio is sent. Format `tcp://host:port` | `tcp://homeassistant:10300` |
| **`verify_threshold`** | Voice similarity (0–1). Higher = stricter | `0.35` |
| **`extraction_threshold`** | Strips TV/other voices before STT | `0.30` |
| **`max_verify_seconds`** | Seconds of audio used for the first verification pass | `5.0` |
| **`verify_window_seconds`** | Sliding-window size for fallback verification (sec) | `3.0` |
| **`verify_step_seconds`** | Sliding-window step (sec) | `1.5` |
| **`stt_languages`** | Comma-separated languages, e.g. `uk,ru` | `uk,ru` |
| **`tag_speaker`** | Prepend `[name]` to the transcript | `false` |
| **`require_speaker_match`** | `true` — audio from unenrolled speakers is rejected | `true` |
| **`save_rejected`** | Keep audio that failed verification, for diagnostics | `false` |
| **`log_level`** | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |

Translated labels for these options in the Home Assistant UI (Ukrainian,
Russian, English) come from `translations/*.yaml`.

### Recommended thresholds

| Situation | `verify_threshold` | `extraction_threshold` |
|---|---|---|
| Default | 0.35 | 0.30 |
| Rejects you too often | 0.28–0.32 | 0.25–0.28 |
| Accepts other voices | 0.45–0.55 | 0.35–0.40 |
| Cuts off your words | — | lower to 0.25–0.28 |

Thresholds only affect **who** is accepted and how aggressively background
is stripped. Transcription quality depends on the upstream STT (model,
languages).

## Port and integration

- **`10350/tcp`** — Wyoming Protocol (add the integration in HA).
- Ingress UI — the **Voice Match** side panel (recording, enrollment, scan).

## Troubleshooting

| Problem | Try this |
|---|---|
| Other voices are accepted | Raise `verify_threshold`, re-record samples |
| Your own voice is rejected | Lower `verify_threshold`, add more OK samples, re-enroll |
| Words get cut off | Lower `extraction_threshold` |
| Nothing changes after Enrollment | Wait 1–2 s (hot-reload); check the logs |
| Long first start | Expected: the model downloads once (1–3 min) |
| No upstream found | Use **Scan** in the UI, or try `tcp://homeassistant:10300` |

## Data

- Samples: `/data/enrollment/<speaker>/`
- Voiceprints: `/data/voiceprints/<speaker>.npy`
- Model cache: `/data/models` and `/data/hf_cache`

See also [SECURITY.md](../SECURITY.md).
