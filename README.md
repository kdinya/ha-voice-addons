# HA Voice Add-ons

Репозиторій аддонів для Home Assistant: верифікація голосу та Speech-to-Text через OpenAI-compatible API (Groq, OpenAI тощо).

**Репозиторій:** https://github.com/kdinya/ha-voice-addons

| Аддон | Порт Wyoming | Призначення |
|-------|--------------|-------------|
| **Voice Match** | **10350** | Перевірка голосу, проксі на upstream STT (повністю автономний) |
| **Wyoming OpenAI STT** | **10300** | Розпізнавання мови (uk/ru) через Groq / OpenAI API |

## Встановлення в Home Assistant

Перевірено з **Home Assistant OS**, Core **2026.8.x**, Supervisor **2026.07.x**.

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
    → Voice Match (10350)          ← перевірка спікера
        → Wyoming OpenAI STT (10300)  ← транскрипція (Groq/OpenAI)
            → Assist / автоматизації
```

---

## Voice Match 2.0 — коротко

**Нове в 2.0.x:**
- Повністю автономний (не залежить від чужого образу)
- **Hot-reload** — після Enrollment рестарт більше НЕ потрібен
- М’якші пороги за замовчуванням (0.35 / 0.30)
- У 2.0.3+ прибрано кнопки Restart з UI
- У 2.0.4 виправлено перевірку запису з мікрофона (`/api/analyze_blob`)

**Перший старт:** 1–3 хвилини (завантаження моделі ECAPA-TDNN у `/data`). Далі — з кешу.

1. У Configuration вкажіть **upstream_uri** (`Адреса Wyoming STT`), напр. `tcp://homeassistant:10300`.
2. Відкрийте панель **Voice Match**:
   - спікер (список або нове ім’я латиницею);
   - запис з мікрофона або завантаження файлів;
   - перевірка якості зразків;
   - **Enrollment** → voiceprint активується одразу.
3. Wyoming Protocol → порт **10350** → у pipeline STT = Voice Match.

### Параметри Voice Match

| Параметр | Українською | За замовчуванням |
|----------|-------------|------------------|
| `upstream_uri` | Адреса Wyoming STT | `tcp://homeassistant:10300` |
| `verify_threshold` | Поріг верифікації голосу | `0.35` |
| `extraction_threshold` | Поріг виділення сегментів | `0.30` |
| `stt_languages` | Мови розпізнавання | `uk,ru` |
| `require_speaker_match` | Вимагати збіг голосу | `true` |
| `log_level` | Рівень логування | `INFO` |

Детальніше: [voice-match/DOCS.md](voice-match/DOCS.md).  
Безпека: [SECURITY.md](SECURITY.md).

---

## Enrollment (реєстрація голосу)

1. Обрати спікера або ввести нове ім’я (латиниця).
2. Записати 3–5 зразків (3–10 сек).
3. **Перевірити всі зразки** → видалити погані.
4. **Enrollment** → voiceprint створюється і **одразу активний** (рестарт не потрібен).

---

## Релізи

Після змін у `main`:

```bash
git tag 2.0.4
git push origin 2.0.4
```

GitHub Action створить Release з текстом із CHANGELOG.
