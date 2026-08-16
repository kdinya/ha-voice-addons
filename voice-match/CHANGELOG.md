# Changelog

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
