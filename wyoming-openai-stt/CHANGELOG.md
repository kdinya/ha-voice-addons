# Changelog

## 2.0.0
- **Security fix:** `entrypoint.sh` no longer re-interpolates the `languages` option into a Python source string. A crafted `languages` value could previously break out of the string literal and execute arbitrary Python inside the container. All options (including `languages`) are now parsed once, entirely as JSON data, inside a single Python process, then handed to bash via a shell-quoted env file — no user-controlled value is ever placed into Python source text.
- `entrypoint.sh` now honors an `OPTIONS_FILE` environment variable override (defaults to `/data/options.json` as before), which also makes it possible to test the parsing logic in CI.
- CI: added a regression test (`tests/test_entrypoint_injection.sh`) that feeds a code-injection payload through `languages` and asserts it is never executed.
- Synced with Voice Match 3.0.0.

## 1.5.4
- Pin базового образу на 0.5.0

## 1.5.3
- Синхронізація з Voice Match 2.0.3

## 1.5.2
- Синхронізація версії з Voice Match 1.5.2

## 1.5.1
- Синхронізація версії з Voice Match 1.5.1
- Оновлена документація репозиторію (README)

## 1.5.0
- Синхронізація версії з Voice Match 1.5.0
- Авто-Release workflow у репозиторії

## 1.4.0
- Іконка, kdinya URL, попередження про порожній API key
