# Wyoming OpenAI STT

Speech-to-Text через **будь-який OpenAI-compatible API**:
OpenAI, Groq, LocalAI, Speaches тощо.

Працює як звичайний Wyoming STT для Home Assistant (порт **10300**).
Ідеально поєднується з аддоном **Voice Match**.

---

## Налаштування

| Поле | Опис |
|------|------|
| **Базовий URL API** | Адреса API (див. приклади нижче) |
| **API-ключ** | Ключ провайдера (для Groq — з console.groq.com) |
| **Модель** | Назва моделі (див. рекомендовані) |
| **Мови** | Через пробіл, наприклад `uk en` |
| **Рівень логування** | INFO за замовчуванням |

### Приклади base_url

| Провайдер | base_url |
|-----------|----------|
| **Groq** (рекомендовано) | `https://api.groq.com/openai/v1` |
| OpenAI | `https://api.openai.com/v1` |
| LocalAI / Speaches | `http://IP:порт/v1` |

### Рекомендовані моделі

**Groq**
| Модель | Коли обрати |
|--------|-------------|
| `whisper-large-v3-turbo` | **Найкращий баланс** швидкість/ціна/якість |
| `whisper-large-v3` | Максимальна точність (дорожче) |

**OpenAI**
| Модель | Коли обрати |
|--------|-------------|
| `whisper-1` | Класика, стабільна |
| `gpt-4o-mini-transcribe` | Сучасніша, часто точніша |
| `gpt-4o-transcribe` | Найвища якість OpenAI |

Ключ Groq: [console.groq.com](https://console.groq.com) → API Keys.

---

## Якщо розпізнає «не те»

1. Переконайтеся, що в pipeline вибрана мова **українська** (або потрібна вам).
2. У полі **Мови** аддона має бути `uk` (або `uk en`).
3. Спробуйте `whisper-large-v3` замість turbo — трохи точніше.
4. Говоріть чіткіше; менше фонового шуму.
5. Voice Match може «обрізати» початок фрази — трохи знизьте
   `extraction_threshold` у Voice Match (наприклад 0.30).

---

## Підключення

1. Start цього аддона.
2. Settings → Devices & Services → **Wyoming Protocol**
   - Host: IP Home Assistant або `homeassistant`
   - Port: **10300**
3. Або вкажіть у Voice Match: `upstream_uri = tcp://homeassistant:10300`

---

## Технічні деталі

- Базується на [roryeckel/wyoming_openai](https://github.com/roryeckel/wyoming_openai)
- Режим **лише STT** (TTS вимкнено)
- 404 на `/readyz` / `/health` у логах для Groq — нормально
