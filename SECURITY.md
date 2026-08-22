# Security

## Voice data (Voice Match)

- Enrollment samples and voiceprints are stored **locally** on Home
  Assistant, in the add-on's `/data` directory (`enrollment/`,
  `voiceprints/`).
- They are **never** sent to any cloud service by Voice Match.
- The ECAPA-TDNN model is downloaded from Hugging Face (cached in
  `/data/hf_cache`) — that's just model weights, not your recordings.

## API keys (Wyoming OpenAI STT)

- `api_key` is stored in the add-on's Supervisor configuration and is only
  ever sent to the configured `base_url`.
- Voice Match never sees or forwards your STT API key — it only forwards
  audio, after voice verification.

## Network

- The Wyoming ports (10300 / 10350) listen on your Home Assistant network.
  Restrict access to your Supervisor/HA host per your own network policy
  (VPN, firewall).
- Do not expose these ports directly to the internet without additional
  protection.

## Recommendations

1. Don't commit API keys to git.
2. Keep the add-ons updated from the repository.
3. If you're handing off a device, delete voiceprints and samples via the
   web UI first, or reinstall the add-on with its data wiped.
