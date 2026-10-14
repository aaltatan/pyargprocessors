# pyargprocessors

A lightweight, typed Python library that does one thing: turn the **raw arguments** a function receives into the objects it wants, with a `Process` marker written next to the parameter.

`pyargprocessors` focuses on a functional style:

- a processor is a plain function of one value: `int`, `Decimal`, `str.strip`, `date.fromisoformat`, an enum class, your own `load_rows`
- the marker sits inside `Annotated`, next to the parameter it changes
- a `type` alias names a processed type once, so many functions share it
- several processors on one parameter run left to right
- `*args` and `**kwargs` are processed item by item
- a failure says which argument and which value, and keeps the original exception
- `@process` works on plain functions, methods and `async` functions, and `process(cls)` on classes, dataclasses and named tuples
- `@dataclass` is `dataclasses.dataclass` whose class processes its own fields
- a processor that raises is a validator
- libraries that bind arguments themselves reuse the same two building blocks

It is the argument processing of its siblings [pyspecification](https://github.com/aaltatan/pyspecification) (predicates) and [pyflowstep](https://github.com/aaltatan/pyflowstep) (flows) as a package of its own, and has **zero dependencies**.

---

## Why use pyargprocessors?

Values that come from JSON, a web form, a command line or an environment variable are strings, numbers, booleans, lists, dicts or null. Functions want dates, decimals, enums, clean text or loaded data. Usually the conversion ends up at the top of every function body:

```python
def search(text, low="0", limit="3"):
    text = text.strip().lower()
    low = Decimal(low)
    limit = int(limit)
    ...
```

With `pyargprocessors` the conversion is part of the signature, and the body starts with real work:

```python
type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Money = Annotated[Decimal, Process(Decimal)]


@process
def search(text: Text, low: Money = Decimal(0), limit: Annotated[int, Process(int)] = 3): ...


search("  HeadPhones ", "20", limit="2")   # text="headphones", low=Decimal("20"), limit=2
```

---

## Installation

```bash
pip install pyargprocessors
```

or with uv:

```bash
uv add pyargprocessors
```

Requires Python 3.12+.

---

## Quick start

```python
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, process

type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Money = Annotated[Decimal, Process(Decimal)]


@process
def add_item(name: Text, price: Money, quantity: Annotated[int, Process(int)] = 1) -> str:
    return f"{quantity} x {name} = ${price * quantity}"


print(add_item("  Green TEA ", "2.50", "3"))   # 3 x green tea = $7.50
print(add_item("Milk", "1.20"))                # 1 x milk = $1.20
```

---

## Core concepts

### Process

`Process(fn)` marks a parameter: `fn` is applied to the value that is passed for it. It is written inside `Annotated`, so the parameter keeps its real type and its real default.

```python
from typing import Annotated

from pyargprocessors import Process, process


@process
def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0) -> None: ...


wait("#result", "10")   # timeout is 10.0
wait("#result")         # timeout is 5.0, the default is not processed
```

A processor can be **any** callable of one value: a class, a method, a lambda, a `functools.partial`, a function that reads a file.

### process

`@process` reads the markers once, when the function is decorated, and applies them on every call, before the function runs.

```python
@process
def greet(name: Annotated[str, Process(str.title)]) -> str:
    return f"Hello {name}"


greet("ada lovelace")   # 'Hello Ada Lovelace'
```

- Methods work, put `@process` under `@classmethod` or `@staticmethod`.
- `async` functions stay `async`. Generators and coroutines fail when they are **called**, not when they are iterated or awaited.
- A function without markers is returned as it is, so `@process` costs nothing there.
- The decorated function keeps its name, docstring and signature, and `fn.__wrapped__` is the original function, for callers that already hold real objects.

### Classes, dataclasses and named tuples

`process(cls)` reads the markers of the constructor and returns a **factory function**, not a class. Keep the class under its own name and give the factory another one:

```python
@dataclass(frozen=True)
class Settings:
    database_url: Annotated[str, Process(str.strip)]
    port: Annotated[int, Process(int)] = 8000
    debug: Annotated[bool, Process(to_bool)] = False


make_settings = process(Settings)

make_settings(database_url=" postgres://db ", port="8080")   # database_url='postgres://db', port=8080
Settings(database_url="sqlite://", port=9000)                # the class itself processes nothing
```

It works the same for a plain class (`__init__`), a `NamedTuple` and a class that only defines `__new__`.

### dataclass

When the class itself should process its fields, use `pyargprocessors.dataclass` in place of `dataclasses.dataclass`. It takes the same options, with or without parentheses, and returns the class, not a factory:

```python
from pyargprocessors import Process, dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: Annotated[str, Process(str.strip)]
    port: Annotated[int, Process(int)] = 8000


Settings(database_url=" postgres://db ", port="8080")   # Settings(database_url='postgres://db', port=8080)
isinstance(Settings(database_url="sqlite://"), Settings)   # True
```

- Only the generated `__init__` is processed, so `__post_init__` already sees the processed values.
- A subclass decorated with `@dataclass` processes the fields it inherits too. A subclass made with `dataclasses.dataclass` processes nothing.
- With `init=False` there is no `__init__` to process and the class is left as `dataclasses.dataclass` made it.
- Type checkers treat it like `dataclasses.dataclass` (`dataclass_transform`).
- A nested object needs no factory: the nested class is its own processor, see [`examples/events.py`](examples/events.py).

### Name it once, reuse it

A `type` alias gives a processed type a name, so many functions can share it:

```python
from decimal import Decimal

type Money = Annotated[Decimal, Process(Decimal)]
type Text = Annotated[str, Process(str.strip), Process(str.lower)]   # several processors run left to right


@process
def price_between(low: Money, high: Money) -> list[Product]: ...


@process
def search(text: Text, min_stars: Annotated[float, Process(float)] = 0) -> list[Product]: ...
```

Aliases can build on aliases, `Annotated[Text, Process(slugify)]` runs the processors of `Text` first.

### Loading data from a value

Because a processor is any function of one value, the caller can pass a path and the function can receive what was loaded from it:

```python
def load_names(path: str) -> frozenset[str]:
    return frozenset(Path(path).read_text().splitlines())


type Names = Annotated[frozenset[str], Process(load_names)]


@process
def exclude(products: list[Product], names: Names) -> list[Product]:
    return [product for product in products if product.name not in names]


exclude(products, "discontinued.txt")
```

### `*args` and `**kwargs`

On `*args` the processor applies to each item, and on `**kwargs` to each value:

```python
@process
def where(*names: Text, in_stock: Annotated[bool, Process(to_bool)] = False, **fields: Text): ...


where(" A ", "B", in_stock="yes", brand=" SONIC ")
# names=("a", "b"), in_stock=True, fields={"brand": "sonic"}
```

### Lists and nulls: `each` and `optional`

Two small helpers build a processor out of another one:

```python
from pyargprocessors import each, optional

type Prices = Annotated[list[Decimal], Process(each(Decimal))]         # every item of a list
type Limit = Annotated[int | None, Process(optional(int))]            # None is kept as None
type Tags = Annotated[list[str] | None, Process(optional(each(str.lower)))]
```

- `each(fn)` applies `fn` to each item of a list, tuple, set or frozenset, keeping its type, and to each value of a dict. Anything else, a string included, is rejected.
- `optional(fn)` applies `fn` to every value except `None`.

### One value, no function

`process_value` applies the markers of an annotation to a single value, so a processed type is useful outside a function call too:

```python
from pyargprocessors import process_value

process_value(Money, "19.90")                   # Decimal('19.90')
process_value(Text, "  Tea ")                   # 'tea'
process_value(Limit, form["limit"], name="limit")
```

### Which values are processed

- Only values that are **actually passed**, positionally or by keyword. Default values are never processed.
- Arguments are bound to the signature first, so a missing or extra argument raises the usual `TypeError` before any processor runs.
- The marker must be the outermost annotation of the parameter. `Money | None` hides the marker inside a union and nothing is processed; write `Annotated[Decimal | None, Process(optional(Decimal))]`.
- Type checkers see the parameter's real type, so `wait("#result", "10")` is reported when you write it by hand. That is the point: processors are for values that arrive untyped.

---

## Errors

A processor that fails on a value raises `ProcessArgumentError`, chained to the original exception. It carries the name of the argument, the value as it was passed and the original exception, which is what a form needs to show the message next to the right field:

```python
try:
    search("headphones", limit="two")
except ProcessArgumentError as error:
    error.argument    # 'limit'
    error.value       # 'two', as it was passed, before any processor ran
    error.cause       # ValueError("invalid literal for int() with base 10: 'two'"), also `__cause__`
```

```text
pyargprocessors.exceptions.ProcessArgumentError: Argument 'limit' with value 'two' failed to process, invalid literal for int() with base 10: 'two'
```

- Inside `**kwargs` the argument is the keyword itself (`'brand'`), inside `*args` it is the name of the parameter.
- Only the **first** bad argument is reported, in the order of the signature. To collect every bad field, process them one by one with `process_value`, see [`examples/validation.py`](examples/validation.py).
- A processor that calls another processed function fails with a `ProcessArgumentError` whose `cause` is another one, so the path to a value deep inside a JSON body can be rebuilt (`lines.quantity`), see [`examples/api.py`](examples/api.py).
- It is a `TypeError` too: write `except ProcessArgumentError` **before** `except TypeError`.
- It can be copied and pickled, so it survives a trip through `multiprocessing` or a task queue.
- `KeyboardInterrupt` and `SystemExit` raised inside a processor are never wrapped.

A marker that cannot work raises `InvalidProcessorError` when the function is decorated:

| Problem                                              | Example                                                           |
| ---------------------------------------------------- | ----------------------------------------------------------------- |
| The processor is not callable                        | `Process("int")`                                                  |
| The marker is used as a default value                | `amount: int = Process(int)`, write `Annotated[int, Process(int)]` |
| The marker is on a parameter that is not an argument | see `skip` below                                                  |

Both derive from `PyargprocessorsError` and from `TypeError`.

---

## Building on top

A library that binds arguments itself, a rule factory, a step factory, a command dispatcher, does not need `@process`. It uses the two functions the decorator is made of:

- `find_processors(fn)` once, when the function is registered
- `process_arguments(processors, bound)` every time arguments are bound

```python
from inspect import Signature, signature

from pyargprocessors import find_processors, process_arguments


def rule(fn):
    processors = find_processors(fn, skip=1)   # the first parameter is the object under test
    arguments = Signature(list(signature(fn).parameters.values())[1:])

    def factory(*args, **kwargs):
        bound = process_arguments(processors, arguments.bind(*args, **kwargs))
        return lambda obj: fn(obj, *bound.args, **bound.kwargs)

    return factory


@rule
def name__eq(name: str, value: Text) -> bool:
    return name == value


name__eq("  Tea ")("tea")   # True, "  Tea " was processed once, when the rule was built
```

- `skip=n` says the first `n` parameters are not passed as arguments, so a marker on them raises `InvalidProcessorError` instead of being silently ignored.
- `name=` is how error messages call the function, for when the public name differs from `fn.__name__`.
- `process_arguments` returns new `BoundArguments` and leaves the given ones untouched.
- `input_annotation(Process(load_names))` returns `str`, the type hint of the processor's own parameter. A JSON schema uses it to describe what the caller must send, and falls back to the parameter's type when it is `None` (`int`, `Decimal`, an enum class).
- `annotated_metadata(annotation)` and `resolved_annotations(fn)` read `Annotated` metadata through `type` aliases, for libraries that add markers of their own.

---

## Use cases

| You receive                                    | You want                                                | See                                                                |
| ---------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------ |
| A web form: every field is a string            | Typed arguments of a search function                    | [`examples/form.py`](examples/form.py)                             |
| A web form, and you must show **every** error  | Clean values and one message per field                  | [`examples/validation.py`](examples/validation.py)                 |
| Environment variables                          | A frozen, typed settings object                         | [`examples/settings.py`](examples/settings.py)                     |
| `argv` words                                   | Commands that are plain typed functions                 | [`examples/cli.py`](examples/cli.py)                               |
| A decoded JSON body, with nested objects       | An `async` handler with `UUID`, `datetime`, dataclasses | [`examples/api.py`](examples/api.py)                               |
| Webhook JSON with a `type` and nested objects  | Real dataclass events to `match` on                     | [`examples/events.py`](examples/events.py)                         |
| Functions your users register in your library  | Their arguments processed by your own binding           | [`examples/rules.py`](examples/rules.py)                           |
| A query string (`parse_qs` gives lists)        | Single values, repeated values, paging, sorting         | [`tests/e2e/test_query_string.py`](tests/e2e/test_query_string.py) |
| The lines of a CSV file                        | Typed rows, and the problems line by line               | [`tests/e2e/test_csv_import.py`](tests/e2e/test_csv_import.py)     |
| A JSON-RPC request, params by position or name | A table of methods that know their own types            | [`tests/e2e/test_json_rpc.py`](tests/e2e/test_json_rpc.py)         |

### A processor can validate

A processor that raises rejects the value. Chained after a converter, it sees the converted value:

```python
def between(low: int, high: int):
    def check(number: int) -> int:
        if not low <= number <= high:
            raise ValueError(f"must be between {low} and {high}")
        return number

    return check


type Age = Annotated[int, Process(int), Process(between(13, 120))]

process_value(Age, "36")    # 36
process_value(Age, "7")     # ProcessArgumentError: ... failed to process, must be between 13 and 120
```

### An empty form field

A form sends `""` for a field left empty, and `optional` only skips `None`. Put your own first step in front of it:

```python
def blank_to_none(text: str | None) -> str | None:
    return text if text and text.strip() else None


type MaybeMoney = Annotated[Decimal | None, Process(blank_to_none), Process(optional(Decimal))]
```

### Nested objects

A nested object is one more processor: the factory of its own class.

```python
make_line = process(Line)   # a dataclass with its own markers


def to_line(data: dict) -> Line:
    return make_line(**data)


type Lines = Annotated[list[Line], Process(each(to_line))]
```

---

## Good to know

Corners that are decided on purpose, each pinned by a test in [`tests/test_edge_cases.py`](tests/test_edge_cases.py):

| Situation                                                | What happens                                                                                                                                                                                       |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `None` is passed explicitly                              | It **is** processed, and `Process(int)` fails on it. Use `optional(int)`. Only a default that is not passed is left alone.                                                                         |
| The value already has the wanted type                    | It is processed again. `int(5)` and `Decimal(Decimal("1"))` are fine, `UUID(a_uuid)` and `datetime.fromisoformat(a_datetime)` are not. Call `fn.__wrapped__`, or use a processor that accepts both. |
| `Process(bool)` on `"false"`                             | `True`, like `bool("false")`. Write a `to_bool`.                                                                                                                                                   |
| `Process(Decimal)` on a JSON number                      | `Decimal(0.1)` keeps the float error. Use `Process(str), Process(Decimal)`.                                                                                                                        |
| `Process(int)` on `" 42 "`, `"1_000"`, `"٤٢"`, `3.9`      | `42`, `1000`, `42`, `3`: whatever `int` itself accepts.                                                                                                                                            |
| A processor returns nothing (`list.sort`)                | The argument becomes `None`. The result is never checked against the type hint.                                                                                                                    |
| The marker is inside `X \| None`, `list[X]`, `Final[X]`   | Not seen, nothing is processed. The marker must be outermost.                                                                                                                                      |
| `from __future__ import annotations`                     | Works. A name imported only under `TYPE_CHECKING` stays a string and does not hide the other markers. An alias defined **inside a function** cannot be found.                                      |
| `@process` twice on one function                         | The processors run twice.                                                                                                                                                                          |
| `@process` above a decorator without `functools.wraps`   | The real signature is hidden, nothing is processed. Put `@process` below it.                                                                                                                       |
| `@process` above `@lru_cache`                            | Works, and the cache key is the processed value: `"3"`, `3` and `" 3 "` share one entry.                                                                                                           |
| A `functools.partial`                                    | What the partial already bound is a default, so it is not processed.                                                                                                                               |
| A subclass overrides a processed method                  | The override is not processed unless it is decorated again.                                                                                                                                        |
| `dataclasses.replace` on a `@dataclass` instance          | Every field goes through `__init__` again, so it is processed again: see "The value already has the wanted type".                                                                                 |
| Recursion                                                | Every level processes its own arguments.                                                                                                                                                           |
| `each` on a named tuple, an `OrderedDict`                | The result is a plain `tuple`, a plain `dict`.                                                                                                                                                     |
| `each` on a string, a generator, a `deque`, a `range`    | Rejected with a `TypeError`.                                                                                                                                                                       |
| A builtin without a signature (`int`, `dict`)            | It carries no markers: `process(int) is int`.                                                                                                                                                      |
| A library wants defaults processed too                   | Call `bound.apply_defaults()` before `process_arguments`.                                                                                                                                          |
| Threads                                                  | Nothing is shared between calls.                                                                                                                                                                   |

---

## Examples

Runnable examples live in [`examples/`](examples). Their exact output is checked by the test suite.

- [`examples/form.py`](examples/form.py) — every way to use `Process`, side by side. A search form sends raw strings (`"20"`, `"yes"`, `" SONIC "`, a file path, an empty field) and the function receives typed, clean arguments:

  ```bash
  uv run python -m examples.form
  ```

  ```python
  @process
  def search(
      text: Text,
      *,
      low: Money = Decimal(0),
      high: MaybeMoney = None,
      in_stock: Annotated[bool, Process(to_bool)] = False,
      exclude: Names = frozenset(),
      limit: Annotated[int, Process(int)] = 3,
      **fields: Text,
  ) -> list[Product]: ...
  ```

- [`examples/validation.py`](examples/validation.py) — processors that check (`required`, `between(13, 120)`, `one_of("free", "pro")`), and a `clean(SignUp, form)` that processes a `TypedDict` field by field and returns **every** error at once:

  ```bash
  uv run python -m examples.validation
  ```

  ```python
  values, errors = clean(SignUp, form)
  # errors == {"email": "enter a valid email address", "age": "must be between 13 and 120"}
  ```

- [`examples/settings.py`](examples/settings.py) — environment variables become a frozen dataclass through `process(Settings)`: a validated port, a flag, an enum, a tuple of hosts, a `timedelta`, a `Path`. A bad variable stops the start-up with its name:

  ```bash
  uv run python -m examples.settings
  ```

- [`examples/cli.py`](examples/cli.py) — a to-do command line. The dispatcher hands raw words to commands that are plain typed functions; `--due=tomorrow`, `--priority=HIGH` and `--tags=Home,shop` become a `date`, an enum and a set:

  ```bash
  uv run python -m examples.cli
  ```

  ```python
  @command
  def add(title: Title, *, due: Day = None, priority: Level = Priority.NORMAL, tags: Tags = frozenset()) -> str: ...


  @command
  def done(*ids: Annotated[int, Process(int)]) -> str: ...
  ```

- [`examples/api.py`](examples/api.py) — an `async` handler receives a decoded JSON body with a list of nested objects. A bad value deep inside is answered with its path, `{"field": "lines.quantity", ...}`:

  ```bash
  uv run python -m examples.api
  ```

- [`examples/events.py`](examples/events.py) — [`@dataclass`](#dataclass): a carrier's webhook JSON becomes typed tracking events. The classes process their own fields, nested ones included, then `__post_init__` checks across fields, `match` picks the event, and `dataclasses.replace` still works:

  ```bash
  uv run python -m examples.events
  ```

  ```python
  @dataclass(frozen=True, kw_only=True)
  class Shipped(Event):   # inherits processed `event_id: Id` and `at: Moment`
      to: Annotated[Address, Process(nested(Address))]
      parcels: Annotated[tuple[Parcel, ...], Process(each(nested(Parcel))), Process(tuple)]
      ...


  Shipped(**payload).to   # Address(name='Ada Lovelace', city='Damascus', postcode='DM 101')
  ```

- [`examples/rules.py`](examples/rules.py) — [building on top](#building-on-top): a tiny rules library with `find_processors(skip=1)`, `process_arguments` and `input_annotation`, compiling rules from JSON:

  ```bash
  uv run python -m examples.rules
  ```

---

## API reference

| Name                                        | Kind      | Description                                                              |
| ------------------------------------------- | --------- | ------------------------------------------------------------------------ |
| `Process(fn)`                               | marker    | Apply `fn` to the value passed for a parameter                           |
| `process`                                   | decorator | Apply the markers of a function, or of a constructor, on every call      |
| `dataclass`                                 | decorator | `dataclasses.dataclass` whose `__init__` applies the markers of its fields |
| `process_value(annotation, value, name=)`   | function  | Apply the markers of an annotation to one value                          |
| `each(fn)`                                  | function  | A processor applying `fn` to each item of a collection                   |
| `optional(fn)`                              | function  | A processor applying `fn` to every value except `None`                   |
| `find_processors(fn, name=, skip=)`         | function  | The markers of every parameter of `fn` that has some                     |
| `process_arguments(processors, bound)`      | function  | New `BoundArguments` with every marked value processed                   |
| `input_annotation(processor)`               | function  | The type hint of the value a processor accepts, or `None`                |
| `annotated_metadata(annotation)`            | function  | The extra arguments of `Annotated[...]`, looking through `type` aliases  |
| `resolved_annotations(fn)`                  | function  | The annotations describing a call to `fn`, with strings evaluated        |
| `ProcessArgumentError`                      | exception | A processor failed; has `.argument`, `.value` and `.cause`               |
| `InvalidProcessorError`                     | exception | A marker that cannot work                                                |
| `PyargprocessorsError`                      | exception | Base class of both                                                       |

---

## Development

```bash
uv sync
uv run pytest --cov --cov-report term-missing
```

The test suite also runs every docstring example (`--doctest-modules`).

| Tests                              | What they cover                                                        |
| ---------------------------------- | ---------------------------------------------------------------------- |
| `tests/test_*.py`                  | Each module on its own                                                 |
| `tests/test_examples.py`           | The exact output of every example                                      |
| `tests/test_user_stories.py`       | One story per kind of user, built on the examples                      |
| `tests/e2e/`                       | Raw text in, answer out: a query string, a CSV file, a JSON-RPC server |
| `tests/test_edge_cases.py`         | Unusual signatures, values, processors, annotations and callables      |
| `tests/test_future_annotations.py` | `from __future__ import annotations`                                   |

## License

GPL-3.0
