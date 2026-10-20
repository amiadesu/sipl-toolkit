# SIPL Language Toolkit

[![CI](https://github.com/amiadesu/sipl-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/amiadesu/sipl-toolkit/actions/workflows/ci.yml)

## Обрані завдання лабораторної роботи

| ID | Завдання | Бали |
|---|---|---|
| CORE-01 | Формальна специфікація SIPL (граматика Lark, ≥10 позитивних і ≥10 негативних тестів) | 0.5 |
| CORE-02 | Парсер і типізоване AST із `SourceSpan` | 1.5 |
| CORE-03 | Інтерпретатор SIPL з лімітом кроків, покриття ядра ≥80% | 2.0 |
| CORE-04 | Подієва модель виконання та trace | 1.0 |
| CORE-05 | CLI: `parse`, `check`, `run`, `trace`, JSON-режим | 1.0 |
| CORE-06 | Conformance suite, незалежний від реалізації | 1.0 |
| VIS-01 | Візуалізація дерева синтаксичного виводу (text / JSON / DOT) | 1.5 |
| VIS-02 | Візуалізація AST та порівняння Parse Tree ↔ AST | 1.0 |
| REL-01 | CI: lint, тести, збірка пакета на кожен PR | 0.5 |
| REL-02 | GitHub Releases + SemVer + CHANGELOG | 0.5 |
| REL-03 | Публікація пакета в PyPI | 0.5 |
| | **Разом** | **11.0** |

## Вимоги

- Python >=3.11
- Node.js >=20 (для веб-інтерфейсу)

## Встановлення

```bash
git clone https://github.com/amiadesu/sipl-toolkit.git
cd sipl-toolkit
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
```

`.[dev]` - тести й лінтер, `.[web]` - backend веб-інтерфейсу. Для роботи лише з CLI
достатньо `pip install -e .`.

## Запуск

Командний рядок (опис команд, кодів завершення й JSON-формату - у [docs/cli.md](docs/cli.md)):

```bash
sipl check examples/power.sipl
sipl run examples/power.sipl -s X=2 -s Y=10
sipl trace examples/power.sipl -s X=2 -s Y=10
sipl tree examples/power.sipl --rules
```

Веб-інтерфейс (backend на http://localhost:8000, сторінка на http://localhost:5173):

```bash
./start.sh
```

## Тестування реалізації мови

```bash
ruff check .
pytest
python conformance/runner.py
```

Формат conformance-тестів описано в [conformance/README.md](conformance/README.md).

## Структура репозиторію

```
src/sipl/        ядро мови (бібліотека): граматика, парсер, AST, інтерпретатор, CLI
tests/           автоматичні тести
examples/        приклади SIPL-програм
conformance/     conformance suite, незалежний від реалізації
web/backend/     FastAPI backend веб-інтерфейсу
web/frontend/    веб-інтерфейс (React + Vite)
docs/            документація до проєкту
start.sh         запуск веб-інтерфейсу
```