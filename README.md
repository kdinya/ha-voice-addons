# HA Voice Add-ons

Репозиторій аддонів для Home Assistant: верифікація голосу та Speech-to-Text через OpenAI-compatible API (Groq, OpenAI тощо).

**Репозиторій:** https://github.com/kdinya/ha-voice-addons

| Аддон | Порт Wyoming | Призначення |
|-------|--------------|-------------|
| **Voice Match** | **10350** | Перевірка голосу, очищення фону, проксі на upstream STT |
| **Wyoming OpenAI STT** | **10300** | Розпізнавання мови (uk/ru) через Groq / OpenAI API |

## Встановлення в Home Assistant

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Додайте:
   ```
   https://github.com/kdinya/ha-voice-addons
   ```
3. Оновіть список, встановіть потрібні аддони, запустіть їх.
4. Додайте інтеграцію **Wyoming Protocol** на відповідні порти.

### Типова схема

```
Мікрофон HA
    → Voice Match (10350)          ← перевірка спікера + очищення
        → Wyoming OpenAI STT (10300)  ← транскрипція (Groq/OpenAI)
            → Assist / автоматизації
```

Можна використовувати лише **Wyoming OpenAI STT** без Voice Match, або Voice Match з будь-яким іншим Wyoming STT.

---

## Voice Match — коротко

1. У Configuration вкажіть **upstream_uri** (`Адреса Wyoming STT`), напр. `tcp://homeassistant:10300`.
2. Відкрийте панель **Voice Match**:
   - спікер (список або нове ім’я латиницею);
   - запис з мікрофона або завантаження файлів (конвертація в WAV 16 kHz mono);
   - перевірка якості зразків;
   - **Enrollment** → voiceprint;
   - **Restart** аддона.
3. Wyoming Protocol → порт **10350** → у pipeline STT = Voice Match.

### Параметри Voice Match

| Параметр | Українською | За замовчуванням |
|----------|-------------|------------------|
| `upstream_uri` | Адреса Wyoming STT | `tcp://homeassistant:10300` |
| `verify_threshold` | Поріг верифікації голосу | `0.40` |
| `extraction_threshold` | Поріг виділення сегментів | `0.35` |
| `max_verify_seconds` | Макс. тривалість першої перевірки | `5.0` |
| `verify_window_seconds` | Розмір ковзного вікна | `3.0` |
| `verify_step_seconds` | Крок ковзного вікна | `1.5` |
| `stt_languages` | Мови розпізнавання | `uk,ru` |
| `tag_speaker` | Додавати ім’я мовця до тексту | `false` |
| `require_speaker_match` | Вимагати збіг голосу | `true` |
| `save_rejected` | Зберігати відхилені записи | `false` |
| `log_level` | Рівень логування | `INFO` |

Детальніше: [voice-match/DOCS.md](voice-match/DOCS.md).

---

## Wyoming OpenAI STT — коротко

Speech-to-Text через **OpenAI-compatible API** (Groq, OpenAI, LocalAI…).

- Порт **10300**
- Мови за замовчуванням: **uk ru**, режим **auto** (автовизначення між українською та російською)
- Рекомендована модель на Groq: `whisper-large-v3-turbo`

| Параметр | Українською | Приклад |
|----------|-------------|---------|
| `base_url` | Базовий URL API | `https://api.groq.com/openai/v1` |
| `api_key` | API-ключ | `gsk_...` |
| `model` | Модель | `whisper-large-v3-turbo` |
| `languages` | Мови | `uk ru` |
| `language_mode` | Режим мови | `auto` або `fixed` |
| `log_level` | Рівень логування | `INFO` |

Детальніше: [wyoming-openai-stt/DOCS.md](wyoming-openai-stt/DOCS.md).

---

## Enrollment (реєстрація голосу)

1. Обрати спікера зі списку або ввести нове ім’я (латиниця).
2. Запис з мікрофона (зберігається як WAV) або файли з диска.
3. **Перевірити всі зразки** → видалити погані (залишити 3–5 OK).
4. **Enrollment** → створюється voiceprint.
5. **Restart** аддона (кнопка в UI або на сторінці аддона в Supervisor).

Без Restart новий voiceprint не застосується.

---

## Релізи (для розробника)

1. Підняти `version` у `*/config.yaml`
2. Оновити `*/CHANGELOG.md` секцією `## x.y.z`
3. Push у `main`
4. Тег:

```bash
git tag 1.5.1
git push origin 1.5.1
```

GitHub Action створить Release з текстом із CHANGELOG.
