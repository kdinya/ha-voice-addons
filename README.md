# HA Voice Add-ons

Репозиторій: https://github.com/kdinya/ha-voice-addons

| Аддон | Призначення | Порт |
|-------|-------------|------|
| **Voice Match** | Верифікація голосу, запис у UI, enrollment | 10350 |
| **Wyoming OpenAI STT** | STT через Groq / OpenAI (uk + ru) | 10300 |

## Встановлення

Settings → Add-ons → Add-on Store → ⋮ → Repositories → додайте:

```
https://github.com/kdinya/ha-voice-addons
```

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkdinya%2Fha-voice-addons)

## Швидкий старт

1. **Wyoming OpenAI STT** — base_url Groq, api_key, model `whisper-large-v3-turbo`, мови `uk ru`, режим `auto`
2. **Voice Match** — upstream `tcp://homeassistant:10300`
3. Бічне меню Voice Match → запис / файли → перевірка → enrollment → **Restart**
4. Wyoming Protocol порт **10350** → pipeline STT = Voice Match

## Будь-який голос без перевірки

Configuration → **Вимагати збіг голосу** → вимкнути.

## Інші STT у HA

Якщо всі команди йдуть через Voice Match → цей Groq STT, інші STT-аддони / інтеграції можна видалити, щоб не плутались у pipeline.
