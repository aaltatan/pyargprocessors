# Errors

## `ProcessArgumentError`: a processor failed

A processor that fails on a value raises `ProcessArgumentError`, chained to the original
exception. It carries the name of the argument, the value as it was passed and the original
exception, which is what a form needs to show the message next to the right field:

```python
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, process


@process
def search(text: str, limit: Annotated[int, Process(int)] = 3) -> int:
    return limit


try:
    search("headphones", limit="two")
except ProcessArgumentError as error:
    assert error.argument == "limit"
    assert error.value == "two"  # as it was passed, before any processor ran
    assert isinstance(error.cause, ValueError)
    assert error.__cause__ is error.cause
    assert str(error) == (
        "Argument 'limit' with value 'two' failed to process, "
        "invalid literal for int() with base 10: 'two'"
    )
```

- Inside `**kwargs` the argument is the keyword itself (`'brand'`), inside `*args` it is the
  name of the parameter.
- Only the **first** bad argument is reported, in the order of the signature. To collect every
  bad field, see [Validation](validation.md#every-error-at-once).
- It is a `TypeError` too: write `except ProcessArgumentError` **before** `except TypeError`,
  which also catches a missing or unknown argument.
- It can be copied and pickled, so it survives a trip through `multiprocessing` or a task queue.
- `KeyboardInterrupt` and `SystemExit` raised inside a processor are never wrapped.

```python
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, process


@process
def done(*ids: Annotated[int, Process(int)], **tags: Annotated[str, Process(str.lower)]) -> None:
    pass


def answer(*args, **kwargs) -> str:
    try:
        done(*args, **kwargs)
    except ProcessArgumentError as error:
        return f"bad {error.argument}"
    except TypeError as error:
        return f"bad call: {error}"
    return "ok"


assert answer("1", "x") == "bad ids"
assert answer("1", colour=3) == "bad colour"
assert answer("1", colour="RED") == "ok"
```

## Nested failures: the path to a value

A processor that calls another processed function fails with a `ProcessArgumentError` whose
`cause` is another one, so the path to a value deep inside a JSON body can be rebuilt:

```python
from dataclasses import dataclass
from typing import Annotated, Any

from pyargprocessors import Process, ProcessArgumentError, each, process


@dataclass
class Line:
    sku: str
    quantity: Annotated[int, Process(int)]


make_line = process(Line)


def to_line(data: dict[str, Any]) -> Line:
    return make_line(**data)


@process
def order(lines: Annotated[list[Line], Process(each(to_line))]) -> list[Line]:
    return lines


def error_path(error: ProcessArgumentError) -> str:
    cause = error.cause
    nested = isinstance(cause, ProcessArgumentError)
    return f"{error.argument}.{error_path(cause)}" if nested else error.argument


try:
    order([{"sku": "tea", "quantity": "two"}])
except ProcessArgumentError as error:
    assert error_path(error) == "lines.quantity"
```

## `InvalidProcessorError`: a marker that cannot work

Raised when the function is decorated (or the marker created), never on a call:

| Problem | Example |
| --- | --- |
| The processor is not callable | `Process("int")` |
| The marker is used as a default value | `amount: int = Process(int)`, write `Annotated[int, Process(int)]` |
| The marker is on a parameter that is not an argument | `find_processors(fn, skip=1)`, see [Building on top](building-on-top.md) |

Both derive from `PyargprocessorsError` and from `TypeError`. See
[Exceptions](../reference/exceptions.md).
