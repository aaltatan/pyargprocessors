# Behaviour corners

Corners decided on purpose, each pinned by a test in `tests/test_edge_cases.py`.

| Situation | What happens |
| --- | --- |
| `None` is passed explicitly | It **is** processed, and `Process(int)` fails on it. Use `optional(int)`. Only a default that is not passed is left alone. |
| The value already has the wanted type | It is processed again. `int(5)` and `Decimal(Decimal("1"))` are fine, `UUID(a_uuid)` and `datetime.fromisoformat(a_datetime)` are not. Call `fn.__wrapped__`, or use a processor that accepts both. |
| `Process(bool)` on `"false"` | `True`, like `bool("false")`. Write a `to_bool`. |
| `Process(Decimal)` on a JSON number | `Decimal(0.1)` keeps the float error. Use `Process(str), Process(Decimal)`. |
| `Process(int)` on `" 42 "`, `"1_000"`, `"٤٢"`, `3.9` | `42`, `1000`, `42`, `3`: whatever `int` itself accepts. |
| A processor returns nothing (`list.sort`) | The argument becomes `None`. The result is never checked against the type hint. |
| The marker is inside `X \| None`, `list[X]`, `Final[X]` | Not seen, nothing is processed. The marker must be outermost. |
| `from __future__ import annotations` | Works. A name imported only under `TYPE_CHECKING` stays a string and does not hide the other markers. An alias defined **inside a function** cannot be found. |
| `@process` twice on one function | The processors run twice. |
| `@process` above a decorator without `functools.wraps` | The real signature is hidden, nothing is processed. Put `@process` below it. |
| `@process` above `@lru_cache` | Works, and the cache key is the processed value: `"3"`, `3` and `" 3 "` share one entry. |
| A `functools.partial` | What the partial already bound is a default, so it is not processed. |
| A subclass overrides a processed method | The override is not processed unless it is decorated again. |
| `dataclasses.replace` on a `@dataclass` instance | Every field goes through `__init__` again, so it is processed again: see "The value already has the wanted type". |
| Recursion | Every level processes its own arguments. |
| `each` on a named tuple, an `OrderedDict` | The result is a plain `tuple`, a plain `dict`. |
| `each` on a string, a generator, a `deque`, a `range` | Rejected with a `TypeError`. |
| A builtin without a signature (`int`, `dict`) | It carries no markers: `process(int) is int`. |
| A library wants defaults processed too | Call `bound.apply_defaults()` before `process_arguments`. |
| Threads | Nothing is shared between calls. |

A few of them, checked:

```python
from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, process, process_value

assert process_value(Annotated[bool, Process(bool)], "false") is True
assert process_value(Annotated[Decimal, Process(Decimal)], 0.1) != Decimal("0.1")
assert process_value(Annotated[Decimal, Process(str), Process(Decimal)], 0.1) == Decimal("0.1")
assert process(int) is int

try:
    process_value(Annotated[int, Process(int)], None)
except ProcessArgumentError:
    pass
else:
    raise AssertionError("None is processed")

calls = []


@process
@lru_cache
def square(n: Annotated[int, Process(int)]) -> int:
    calls.append(n)
    return n * n


assert square("3") == square(" 3 ") == square(3) == 9
assert calls == [3]
```
