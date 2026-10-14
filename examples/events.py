"""Events: a webhook sends JSON, the handler matches on real dataclasses.

A carrier posts tracking events as JSON: ids, timestamps and weights arrive as
strings or floats, nested objects as dicts. `pyargprocessors.dataclass` is
`dataclasses.dataclass` whose class processes its own fields, so the class
itself turns a payload into a typed event:

    @dataclass(frozen=True, kw_only=True)
    class Delivered(Event):
        signed_by: Annotated[str | None, Process(optional(str.strip))] = None

    Delivered(**payload)

Unlike `process(cls)`, which returns a factory function, the class stays a
class: a nested class is its own processor, subclasses process the fields they
inherit, `__post_init__` sees processed values, and `isinstance`, `match` and
`dataclasses.replace` work as usual.

Run it with `uv run python -m examples.events`.
"""

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pyargprocessors import Process, ProcessArgumentError, dataclass, each, optional


class Service(StrEnum):
    STANDARD = "standard"
    EXPRESS = "express"


def nested[T](cls: type[T]) -> Callable[[Any], T]:
    """Build `cls` from a dict; a value that already is one is kept."""

    def build(value: Any) -> T:
        return value if isinstance(value, cls) else cls(**value)

    return build


def to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def to_datetime(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


# The processors accept what they produce, because `replace()` processes every field again.
type Id = Annotated[UUID, Process(to_uuid)]
type Moment = Annotated[datetime, Process(to_datetime)]
type Kilos = Annotated[Decimal, Process(str), Process(Decimal)]  # str first: no float error
type Text = Annotated[str, Process(str.strip)]


@dataclass(frozen=True, slots=True)
class Address:
    name: Text
    city: Annotated[str, Process(str.strip), Process(str.title)]
    postcode: Annotated[str, Process(str), Process(str.upper)]  # some clients send a number


@dataclass(frozen=True, slots=True)
class Parcel:
    reference: Text
    weight: Kilos


@dataclass(frozen=True, kw_only=True)
class Event:
    event_id: Id
    at: Moment


@dataclass(frozen=True, kw_only=True)
class Shipped(Event):
    to: Annotated[Address, Process(nested(Address))]
    parcels: Annotated[tuple[Parcel, ...], Process(each(nested(Parcel))), Process(tuple)]
    promised: Moment
    service: Annotated[Service, Process(str.lower), Process(Service)] = Service.STANDARD

    def __post_init__(self) -> None:
        # A check across fields runs after the processors: it compares datetimes, not text.
        if self.promised < self.at:
            msg = f"promised for {self.promised:%d %b}, before it was shipped"
            raise ValueError(msg)

    @property
    def weight(self) -> Decimal:
        return sum((parcel.weight for parcel in self.parcels), Decimal(0))


@dataclass(frozen=True, kw_only=True)
class Delivered(Event):
    signed_by: Annotated[str | None, Process(optional(str.strip))] = None


EVENTS: dict[str, type[Event]] = {"shipped": Shipped, "delivered": Delivered}


def parse(payload: Mapping[str, Any]) -> Event:
    """Pick the class from `type` and let it process the other fields."""
    fields = {name: value for name, value in payload.items() if name != "type"}
    return EVENTS[payload["type"]](**fields)


def describe(event: Event) -> str:
    match event:
        case Shipped(service=Service.EXPRESS, to=Address(city=city)):
            return f"express to {city}: {len(event.parcels)} parcels, {event.weight} kg"
        case Shipped(to=Address(city=city)):
            return f"to {city}: {len(event.parcels)} parcels, {event.weight} kg"
        case Delivered(signed_by=None):
            return "delivered, left at the door"
        case Delivered(signed_by=name):
            return f"delivered, signed by {name}"
        case _:
            return "unknown event"


def where(error: ProcessArgumentError) -> tuple[str, ProcessArgumentError]:
    """Follow nested failures down to the bad value; return its path and its error."""
    path = [error.argument]
    while isinstance(error.cause, ProcessArgumentError):
        error = error.cause
        path.append(error.argument)
    return ".".join(path), error


SHIPPED = {
    "type": "shipped",
    "event_id": "0b7e2f4a-3c1d-4e5f-8a9b-1c2d3e4f5a6b",
    "at": "2026-10-12T09:15:00+03:00",
    "to": {"name": " Ada Lovelace ", "city": " damascus ", "postcode": "dm 101"},
    "parcels": [{"reference": " A-1 ", "weight": 1.2}, {"reference": "A-2", "weight": "0.35"}],
    "promised": "2026-10-13T18:00:00+03:00",
    "service": "EXPRESS",
}

PAYLOADS = [
    SHIPPED,
    {
        "type": "delivered",
        "event_id": "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
        "at": "2026-10-13T16:40:00+03:00",
        "signed_by": " Ada Lovelace ",
    },
    {
        "type": "delivered",
        "event_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
        "at": "2026-10-14T11:05:00+03:00",
    },
]


def main() -> None:
    events = [parse(payload) for payload in PAYLOADS]
    for event in events:
        print(describe(event))

    # The class itself processed the payload, nested objects included.
    shipped = events[0]
    print(type(shipped).__name__, isinstance(shipped, Event))
    print(shipped.to)  # type: ignore[attr-defined]
    print(shipped.parcels[0])  # type: ignore[attr-defined]

    # `replace` processes every field again; these processors accept their own results.
    later = replace(shipped, promised="2026-10-14T12:00:00+03:00")
    print(later.promised.date(), later.to == shipped.to)  # type: ignore[attr-defined]

    # A bad value deep inside a nested object is reported with its path.
    bad_weight = {**SHIPPED, "parcels": [{"reference": "A-1", "weight": "heavy"}]}
    try:
        parse(bad_weight)
    except ProcessArgumentError as error:
        path, inner = where(error)
        print(f"{path}: {inner.value!r} failed ({type(inner.cause).__name__})")

    # A check across fields, in `__post_init__`, is a plain exception of its own.
    too_early = {**SHIPPED, "promised": "2026-10-11T18:00:00+03:00"}
    try:
        parse(too_early)
    except ValueError as error:
        print(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
