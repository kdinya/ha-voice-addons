# HA Voice Add-ons

https://github.com/kdinya/ha-voice-addons

| Аддон | Порт |
|-------|------|
| Voice Match | 10350 |
| Wyoming OpenAI STT | 10300 |

## Встановлення в HA

```
https://github.com/kdinya/ha-voice-addons
```

## Релізи (для розробника)

1. Підняти `version` у `*/config.yaml`
2. Оновити `*/CHANGELOG.md` секцією `## x.y.z`
3. Push у `main`
4. Тег:

```bash
git tag 1.5.0
git push origin 1.5.0
```

GitHub Action сам створить Release з текстом з CHANGELOG.

## Enrollment

1. Обрати спікера зі списку або ввести нове ім’я  
2. Запис з мікрофона (зберігається як WAV) або файли  
3. Перевірити зразки → видалити погані  
4. Enrollment → Restart  
