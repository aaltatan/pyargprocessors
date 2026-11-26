# each and optional

Two small helpers build a processor out of another one. They are plain functions that take a
processor and return a new one, so they combine.

```py
type Prices = Annotated[list[Decimal], Process(each(Decimal))]        # every item of a list
type Limit = Annotated[int | None, Process(optional(int))]            # None is kept as None
type Tags = Annotated[list[str] | None, Process(optional(each(str.lower)))]
```

## `each(fn)`

Applies `fn` to each item of a list, tuple, set or frozenset, keeping its type, and to each
value of a dict. Anything else, a string included, is rejected with a `TypeError`.

```python
from decimal import Decimal

from pyargprocessors import each

assert each(int)(["1", "2"]) == [1, 2]
assert each(int)(("1", "2")) == (1, 2)
assert each(int)({"1", "2"}) == {1, 2}
assert each(str.upper)({"size": "l", "milk": "oat"}) == {"size": "L", "milk": "OAT"}
assert each(Decimal)(frozenset({"0.5"})) == frozenset({Decimal("0.5")})

try:
    each(int)("12")
except TypeError as error:
    assert str(error) == "expected a list, tuple, set or dict, got '12'"
```

- A subclass becomes the plain built-in: a named tuple gives a `tuple`, an `OrderedDict` a
  `dict`.
- A generator, a `deque` or a `range` is rejected, like a string.

## `optional(fn)`

Applies `fn` to every value except `None`, which is kept:

```python
from pyargprocessors import optional

assert optional(int)("2") == 2
assert optional(int)(None) is None
```

`optional` only skips `None`. A form sends `""` for a field left empty; put a step of your own
in front of it:

```python
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, optional, process_value


def blank_to_none(text: str | None) -> str | None:
    return text if text and text.strip() else None


type MaybeMoney = Annotated[Decimal | None, Process(blank_to_none), Process(optional(Decimal))]

assert process_value(MaybeMoney, "   ") is None
assert process_value(MaybeMoney, "9.5") == Decimal("9.5")
```

## Combining them

```python
from typing import Annotated

from pyargprocessors import Process, each, optional, process

type Tags = Annotated[list[str] | None, Process(optional(each(str.lower)))]


@process
def tag(*, tags: Tags = None) -> list[str] | None:
    return tags


assert tag(tags=["Home", "SHOP"]) == ["home", "shop"]
assert tag(tags=None) is None
```

!!! tip "`None` passed explicitly is processed"
    Only a default that is **not passed** is left alone. `Process(int)` fails on an explicit
    `None`; use `Process(optional(int))`.
