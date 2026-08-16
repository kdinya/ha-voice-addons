# Changelog

## 2.0.11
- **Fix: рекомендація порогу тиші** — одна формула в UI і в flash: `макс + 40` (межі 50–400). Прибрано розбіжність, коли flash показував 46/53, а текст — 80

## 2.0.10
- **Fix: калібрування тиші** — кращі повідомлення про помилку мікрофона, resume AudioContext, підказка відкрити Ingress у новій вкладці (iframe блокує getUserMedia)
- **Переклади** — додано повні uk / en / ru для всіх параметрів silence_* (threshold, timeout, min_speech_duration + enabled-перемикачі)
- Підказка в UI секції «0. Калібрування тиші» про відкриття в новій вкладці
- Прибрано все, що пов’язано з «Підтримка проєкту» (SUPPORT.md, FUNDING.yml, секції донатів)

## 2.0.9
- **Налаштовуване відсікання тиші** — 3 параметри з окремими перемикачами увімк/вимк:
  - **Поріг тиші** (silence_threshold) — RMS, нижче якого вважаємо тишею (50–400, за замовч. 180)
  - **Час до відсікання тиші** (silence_timeout) — секунди майже повної тиші → одразу порожній Transcript (1–5 с, за замовч. 2.0)
  - **Мін. довжина мови** (min_speech_duration) — коротші буфери не йдуть у verify (0.5–3 с, за замовч. 1.0)
- Кожне правило можна вимкнути окремо
- Швидкий порожній Transcript при тиші → Voice Satellite закриває сесію за своїм VAD (3–6 с), без хвоста 30–60 с
- Лог `Fast-reject: ...` показує причину відсікання

## 2.0.8
- **Fix: кашель / коротка тиша більше не тримає сесію 30 с**
- Додано швидкий шлях (fast-path): якщо буфер дуже короткий або майже тиша — одразу повертається порожній `Transcript` **без** запуску важкої моделі ECAPA
- Voice Satellite знову може закривати слухання за своїм VAD (наприклад 6 с)
- Тривалість слухання як і раніше повністю на клієнті — аддон лише не блокує його своєю обробкою

## 2.0.7
- **Listening duration fully client-owned** — removed early reject and all add-on listen timeouts
- Handler only buffers until client AudioStop (Voice Satellite / Kiosk VAD), then verifies and forwards
- Removed `early_reject` config option (no longer needed)
- No more 5s/30s/60s session control from the add-on

## 2.0.6
- **Fix: після кашлю / хибного match більше немає очікування 30 с** — прибрано жорсткий `timeout=30` на AudioStop
- Тривалість слухання повністю на стороні клієнта (Voice Satellite / Kiosk VAD), аддон лише чекає їхній AudioStop
- Після успішного verify немає add-on-side deadline

## 2.0.5
- **Fix: 60 с listening на тиші** — при early-reject (немає мови / чужий голос) одразу повертається порожній Transcript, щоб Voice Satellite / HA не чекали max session timeout
- Новий параметр **early_reject** (за замовчуванням `true`) — можна вимкнути для діагностики
- Оновлені переклади (uk / en / ru)

## 2.0.4
- Виправлено відсутній endpoint `/api/analyze_blob` (перевірка запису з мікрофона перед Save)
- Синхронізовано `__version__` у пакеті
- Прибрано `hassio_role: manager` (достатньо hassio_api для Supervisor info)
- Прибрано мертвий CSS Restart-секції
- Pin базового образу STT, CI, SECURITY.md, примітка про перший старт

## 2.0.3
- Прибрано кнопки Restart з UI (hot-reload — рестарт більше не потрібен)
- Виправлено DOCS.md: дефолти порогів і hot-reload узгоджені з config.yaml
- Оновлені підказки в UI після Enrollment / видалення voiceprint
- Покращено Dockerfile (HEALTHCHECK, чіткіші залежності)
- Додано LICENSE (MIT)
- Розширено .gitignore

## 2.0.2
- Виправлено SyntaxError у handler.py (зламана відступність)

## 2.0.1
- Повні версії verify.py та handler.py
- Збережено hot-reload voiceprints

## 2.0.0
- **Повністю автономний** — більше не залежить від образу jxlarrea/wyoming-voice-match
- **Hot-reload voiceprints** — після Enrollment рестарт аддона більше НЕ потрібен
- М’якші пороги за замовчуванням (verify 0.35 / extraction 0.30)
- Оновлені повідомлення в UI
- Код і модель ECAPA-TDNN включені безпосередньо в аддон

## 1.5.2
- Restart: зрозуміліший статус
- Кнопка «Відкрити сторінку аддона» через Supervisor API

## 1.5.1
- Стилізований select спікера
- Покращені кнопки видалення та Restart

## 1.5.0
