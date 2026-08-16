# Changelog

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
- Запис → WAV 16 kHz mono
- Перевірка якості зразків
- GitHub Actions авто-Release
