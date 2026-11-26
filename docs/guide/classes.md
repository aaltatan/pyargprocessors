# Classes and dataclasses

There are two ways to process the arguments of a constructor:

| | `process(cls)` | `@pyargprocessors.dataclass` |
| --- | --- | --- |
| returns | a **factory function** | the **class** |
| works on | any class, dataclass, `NamedTuple`, class with only `__new__` | dataclasses |
| `Settings(...)` itself | processes nothing | processes its fields |
| `isinstance`, subclassing, `match` | on the class, not the factory | as usual |

## `process(cls)`: a factory

`process(cls)` reads the markers of the constructor and returns a factory function, not a
class. Keep the class under its own name and give the factory another one:

```python
from dataclasses import dataclass
from typing import Annotated

from pyargprocessors import Process, process


def to_bool(text: str) -> bool:
    return text.strip().lower() in {"yes", "true", "on", "1"}


@dataclass(frozen=True)
class Settings:
    database_url: Annotated[str, Process(str.strip)]
    port: Annotated[int, Process(int)] = 8000
    debug: Annotated[bool, Process(to_bool)] = False


make_settings = process(Settings)

settings = make_settings(database_url=" postgres://db ", port="8080")
assert settings == Settings(database_url="postgres://db", port=8080)

Settings(database_url="sqlite://", port=9000)  # the class itself processes nothing
```

It works the same for a plain class (`__init__`), a `NamedTuple` and a class that only
defines `__new__`:

```python
from typing import Annotated, NamedTuple

from pyargprocessors import Process, process


class Point(NamedTuple):
    x: Annotated[float, Process(float)]
    y: Annotated[float, Process(float)]


make_point = process(Point)
assert make_point("1.5", "2") == Point(1.5, 2.0)
```

A builtin without a signature carries no markers: `process(int) is int`.

## `@dataclass`: the class processes its own fields

When the class itself should process its fields, use `pyargprocessors.dataclass` in place of
`dataclasses.dataclass`. It takes the same options, with or without parentheses, and returns
the class:

```python
from typing import Annotated

from pyargprocessors import Process, dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: Annotated[str, Process(str.strip)]
    port: Annotated[int, Process(int)] = 8000


settings = Settings(database_url=" postgres://db ", port="8080")
assert repr(settings) == "Settings(database_url='postgres://db', port=8080)"
assert isinstance(Settings(database_url="sqlite://"), Settings)
```

- Only the generated `__init__` is processed, so `__post_init__` already sees the processed
  values.
- A subclass decorated with `@dataclass` processes the fields it inherits too. A subclass made
  with `dataclasses.dataclass` processes nothing.
- With `init=False` there is no `__init__` to process and the class is left as
  `dataclasses.dataclass` made it.
- Type checkers treat it like `dataclasses.dataclass` (`dataclass_transform`).

```python
from datetime import datetime
from typing import Annotated

from pyargprocessors import Process, dataclass

type Moment = Annotated[datetime, Process(datetime.fromisoformat)]


@dataclass(frozen=True, kw_only=True)
class Event:
    at: Moment


@dataclass(frozen=True, kw_only=True)
class Shipped(Event):
    promised: Moment

    def __post_init__(self) -> None:
        if self.promised < self.at:  # compares datetimes, not text
            raise ValueError("promised before it was shipped")


shipped = Shipped(at="2026-10-12T09:15:00", promised="2026-10-13T18:00:00")
assert shipped.at == datetime(2026, 10, 12, 9, 15)  # the inherited field was processed too
```

## Nested objects

A nested object is one more processor. With `process(cls)`, wrap the factory in a function
that takes a dict:

```py
make_line = process(Line)  # a dataclass with its own markers


def to_line(data: dict) -> Line:
    return make_line(**data)


type Lines = Annotated[list[Line], Process(each(to_line))]
```

With `@dataclass` the nested class is its own processor:

```python
from typing import Annotated, Any

from pyargprocessors import Process, dataclass, each


def nested[T](cls: type[T]):
    def build(value: Any) -> T:
        return value if isinstance(value, cls) else cls(**value)

    return build


@dataclass(frozen=True)
class Parcel:
    reference: Annotated[str, Process(str.strip)]


@dataclass(frozen=True)
class Shipment:
    parcels: Annotated[tuple[Parcel, ...], Process(each(nested(Parcel))), Process(tuple)]


shipment = Shipment(parcels=[{"reference": " A-1 "}, {"reference": "A-2"}])
assert shipment.parcels == (Parcel("A-1"), Parcel("A-2"))
```

!!! warning "`dataclasses.replace` processes again"
    `replace()` calls `__init__` with every field, so every field is processed again. Use
    processors that accept their own result (as `nested` above does), see
    [Behaviour corners](../reference/behaviour.md).
