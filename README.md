# HA Voice Add-ons

Репозиторій аддонів для голосового асистента Home Assistant.

| Аддон | Призначення | Порт |
|-------|-------------|------|
| **Voice Match** | Верифікація голосу + очищення фону | 10350 |
| **Wyoming OpenAI STT** | STT через Groq / OpenAI / будь-який OpenAI-compatible API | 10300 |

Разом: спочатку OpenAI STT, потім Voice Match вказує на нього — приймається лише ваш голос.

---

## Встановлення

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Додайте URL цього репозиторію:
   ```
   https://github.com/YOUR_USERNAME/ha-voice-addons
   ```
3. Оновіть список аддонів.

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FYOUR_USERNAME%2Fha-voice-addons)

---

## Рекомендований шлях (Groq + Voice Match)

### 1. Wyoming OpenAI STT

- **base_url**: `https://api.groq.com/openai/v1`
- **api_key**: з [console.groq.com](https://console.groq.com)
- **model**: `whisper-large-v3-turbo`
- **languages**: `uk en`
- Start

### 2. Voice Match

- **upstream_uri**: `tcp://homeassistant:10300`  
  (або кнопка «Сканувати Wyoming STT» у веб-UI)
- **stt_languages**: `uk` або `uk,en`
- Start → бічне меню **Voice Match** → enrollment (3–5 записів) → Restart

### 3. Home Assistant

- Wyoming Protocol → host = HA, port **10350**
- Voice Assistant pipeline → Speech-to-Text → **Voice Match**

---

## Якщо текст розпізнається з помилками

Це налаштування **STT**, не Voice Match:

1. Мова pipeline = українська
2. Модель Groq: `whisper-large-v3` (точніше) або turbo
3. Менше шуму, чіткіша вимова
4. У Voice Match трохи знизьте **Поріг виділення голосу з фону** (0.28–0.32), якщо обрізає слова

Пороги Voice Match (`verify_threshold`) впливають лише на те, **чий** голос приймається, а не на якість тексту.

---

## Що нового в 1.3 / 1.1

- Кнопка сканування Wyoming STT у UI Voice Match
- Зрозуміліші підписи полів українською
- Документація з рекомендованими моделями та порогами
- Підказки щодо якості розпізнавання

---

## Credits

- Voice Match — на основі [jxlarrea/wyoming-voice-match](https://github.com/jxlarrea/wyoming-voice-match)
- OpenAI STT — [roryeckel/wyoming_openai](https://github.com/roryeckel/wyoming_openai)
