# Командний рядок `sipl`

Після встановлення пакета (`pip install -e .` або `pip install sipl-toolkit`) доступна
команда `sipl`. Те саме можна запустити як `python -m sipl`.

```
sipl COMMAND FILE [опції]
```

`FILE` - шлях до програми SIPL (UTF-8) або `-`, щоб прочитати програму зі стандартного вводу.

## Команди

| Команда | Що робить |
|---|---|
| `sipl check FILE` | перевіряє синтаксис; друкує `OK` |
| `sipl parse FILE` | друкує AST програми |
| `sipl run FILE` | виконує програму й друкує кінцевий стан |
| `sipl trace FILE` | виконує програму й друкує всі події виконання |
| `sipl tree FILE` | друкує дерево синтаксичного виводу |

### Спільні опції

| Опція | Команди | Значення |
|---|---|---|
| `--json` | усі | вивести результат у форматі JSON (див. нижче) |
| `-s ІМ'Я=ЧИСЛО`, `--set ІМ'Я=ЧИСЛО` | `run`, `trace` | початкове значення змінної; можна повторювати |
| `--max-steps N` | `run`, `trace` | ліміт кроків виконання (за замовчуванням 100000) |
| `--format text\|dot` | `tree` | формат без `--json`: текст (за замовчуванням) або Graphviz DOT |
| `--rules` | `tree` | показати поруч із категорією правило БНФ курсу (`<оператор> S1`) |

Крок - це одне присвоювання, один `skip` або одна перевірка умови `if`/`while`.

### Приклади

```bash
sipl check examples/power.sipl
sipl run examples/power.sipl -s X=2 -s Y=10
sipl run examples/power.sipl -s X=2 -s Y=10 --json
sipl trace examples/gcd.sipl -s A=48 -s B=18
sipl tree examples/power.sipl --format dot | dot -Tsvg -o tree.svg
echo "begin X := 2 * 3 end" | sipl run -
```

## Коди завершення

Коди стабільні й не змінюються між версіями з однаковим `format_version`.

| Код | Значення |
|---|---|
| 0 | успіх |
| 1 | синтаксична помилка в програмі |
| 2 | неправильні аргументи командного рядка (наприклад, `-s X=abc`) |
| 3 | помилка виконання (змінна без значення) |
| 4 | перевищено ліміт кроків |
| 5 | не вдалося прочитати вхідний файл |

Без `--json` повідомлення про помилку друкується в stderr у форматі
`ФАЙЛ:РЯДОК:КОЛОНКА: помилка: ПОВІДОМЛЕННЯ`. 

З `--json` нічого не друкується в stderr, усе є в JSON-об'єкті в stdout. 

Виняток - код 2: про неправильні аргументи завжди повідомляє сам `argparse` у stderr.

## Формат JSON

Кожна команда з `--json` друкує один JSON-об'єкт такого вигляду:

```json
{
  "format_version": 1,
  "command": "run",
  "status": "ok",
  "...": "поля конкретної команди",
  "error": null
}
```

| Поле | Тип | Значення |
|---|---|---|
| `format_version` | число | версія формату; збільшується лише при несумісних змінах |
| `command` | рядок | `check`, `parse`, `run`, `trace` або `tree` |
| `status` | рядок | `ok` або `error` |
| `error` | об'єкт або `null` | опис помилки, якщо `status` = `error` |

### Поля команд

| Команда | Поля | Якщо синтаксична помилка |
|---|---|---|
| `check` | - | - |
| `parse` | `ast`: AST програми | `ast: null` |
| `run` | `state`: кінцевий стан, `steps`: кількість кроків | `state: null`, `steps: null` |
| `trace` | `events`: список подій | `events: null` |
| `tree` | `tree`: дерево синтаксичного виводу | `tree: null` |

Якщо помилка сталася під час виконання (`run`), `state` і `steps` містять стан і кількість
кроків на момент помилки. У `trace` останньою подією завжди є `execution_finished`.

### Помилка

```json
{
  "stage": "parse",
  "message": "неочікуване '='; очікувалось: ':='",
  "span": {"line": 1, "column": 9, "end_line": 1, "end_column": 10}
}
```

`stage`: `parse` (синтаксис), `run` (виконання) або `input` (читання файлу).
`span` може бути `null`, якщо помилка не прив'язана до місця в коді.

### Позиція (`span`)

`{"line", "column", "end_line", "end_column"}` - рядки й колонки рахуються з 1,
`end_column` вказує на символ одразу після кінця фрагмента.

### AST (`parse`)

Кожен вузол - об'єкт з полем `type`, полями вузла і `span`:

```json
{
  "type": "Assign",
  "target": {"type": "Var", "name": "X", "span": {"...": "..."}},
  "value": {"type": "Num", "value": 1, "span": {"...": "..."}},
  "span": {"...": "..."}
}
```

| `type` | Поля | Правило курсу |
|---|---|---|
| `Program` | `body` | P1 |
| `Assign` | `target` (`Var`), `value` | S1 |
| `Seq` | `first`, `second` | S2 |
| `If` | `cond`, `then_branch`, `else_branch` | S3 |
| `While` | `cond`, `body` | S4 |
| `Block` | `body` | S5 |
| `Skip` | - | S6 |
| `Num` | `value` | A1 |
| `Var` | `name` | A2 |
| `BinOp` | `op` (`+`, `-`, `*`), `left`, `right` | A3–A5 |
| `Compare` | `op` (`=`, `>`), `left`, `right` | B1–B2 |
| `Or` | `left`, `right` | B3 |
| `Not` | `operand` | B4 |

Дужки (A6, B5) в AST не зберігаються.

### Події (`trace`)

Кожна подія має `event`, `step` (кількість виконаних кроків на момент події) і `span`.

| `event` | Додаткові поля |
|---|---|
| `before_statement` | `statement`: `assign`, `skip`, `if`, `while` |
| `after_statement` | `statement` |
| `variable_changed` | `name`, `old` (`null`, якщо значення не було), `new` |
| `condition_checked` | `statement`: `if` або `while`, `result` |
| `execution_finished` | `status`: `ok` або `error`, `state`, `error` |

### Дерево виводу (`tree`)

Кожен вузол має `kind` (`nonterminal` або `terminal`), `label` (категорія курсу, як
`<оператор>`, або сам токен), `rule` (`S1`, `A6`, ... або `null` для терміналів), `text`
(фрагмент вихідного коду), `span` і `children`.