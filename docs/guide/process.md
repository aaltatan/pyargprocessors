# Process and @process

## `Process(fn)`

`Process(fn)` marks a parameter: `fn` is applied to the value that is passed for it. It is
written inside `Annotated`, so the parameter keeps its real type and its real default.

```python
from typing import Annotated

from pyargprocessors import Process, process


@process
def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0) -> float:
    return timeout


assert wait("#result", "10") == 10.0
assert wait("#result") == 5.0  # the default is not processed
```

A processor can be **any** callable of one value: a class, a method, a lambda, a
`functools.partial`, a function that reads a file. A marker that is not callable fails at once:

```python
from pyargprocessors import InvalidProcessorError, Process

try:
    Process("int")
except InvalidProcessorError as error:
    assert str(error) == "Process needs a callable, got 'int'"
```

## Several processors

Several markers on one parameter run **left to right**, each one receiving what the previous
one returned:

```python
from typing import Annotated

from pyargprocessors import Process, process


@process
def greet(name: Annotated[str, Process(str.strip), Process(str.title)]) -> str:
    return f"Hello {name}"


assert greet("  ada lovelace ") == "Hello Ada Lovelace"
```

## `@process`

`@process` reads the markers once, when the function is decorated, and applies them on every
call, before the function runs.

- Arguments are bound to the signature first, so a missing or extra argument raises the usual
  `TypeError` before any processor runs.
- Only values that are **actually passed**, positionally or by keyword, are processed.
  Default values never are.
- A function without markers is returned as it is, so `@process` costs nothing there.
- The decorated function keeps its name, docstring and signature, and `fn.__wrapped__` is the
  original function, for callers that already hold real objects.

```python
from typing import Annotated

from pyargprocessors import Process, process


def plain(x: int) -> int:
    return x


assert process(plain) is plain  # no markers, nothing to wrap


@process
def double(x: Annotated[int, Process(int)]) -> int:
    """Double a number."""
    return x * 2


assert double("4") == 8
assert double.__name__ == "double"
assert double.__doc__ == "Double a number."
assert double.__wrapped__(4) == 8  # the original, without processing
```

## `*args` and `**kwargs`

On `*args` the processors apply to each item, and on `**kwargs` to each value:

```python
from typing import Annotated

from pyargprocessors import Process, process

type Text = Annotated[str, Process(str.strip), Process(str.lower)]


@process
def where(*names: Text, **fields: Text) -> tuple[tuple[str, ...], dict[str, str]]:
    return names, fields


assert where(" A ", "B", brand=" SONIC ") == (("a", "b"), {"brand": "sonic"})
```

## Methods and `async` functions

Methods work; put `@process` **under** `@classmethod` or `@staticmethod`. `async` functions
stay `async`.

```python
import asyncio
import inspect
from typing import Annotated

from pyargprocessors import Process, process

type Count = Annotated[int, Process(int)]


class Basket:
    def __init__(self) -> None:
        self.items: dict[str, int] = {}

    @process
    def add(self, name: str, count: Count = 1) -> None:
        self.items[name] = self.items.get(name, 0) + count

    @classmethod
    @process
    def of(cls, count: Count) -> "Basket":
        basket = cls()
        basket.add("apple", count)
        return basket


basket = Basket.of("3")
basket.add("apple", "2")
assert basket.items == {"apple": 5}


@process
async def fetch(page: Count) -> int:
    return page


assert inspect.iscoroutinefunction(fetch)
assert asyncio.run(fetch("2")) == 2
```

Generators and coroutines fail when they are **called**, not when they are iterated or
awaited: the arguments are processed before the function body is entered.

## The marker must be outermost

The marker must be the outermost annotation of the parameter. Inside a union, a `list[...]`
or `Final[...]` it is not seen and nothing is processed:

```py
low: Money | None = None                                            # hidden: nothing is processed
low: Annotated[Decimal | None, Process(optional(Decimal))] = None   # seen
```

Using the marker as a default value is a mistake caught when the function is decorated:

```python
from pyargprocessors import InvalidProcessorError, Process, process

try:

    @process
    def pay(amount: int = Process(int)) -> int:  # type: ignore[assignment]
        return amount

except InvalidProcessorError as error:
    assert "write it as `amount: Annotated[<type>, Process(...)]`" in str(error)
```

!!! note "Type checkers"
    Type checkers see the parameter's real type, so `wait("#result", "10")` is reported when
    you write it by hand. That is the point: processors are for values that arrive untyped.
