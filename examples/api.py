"""JSON API: turn a decoded request body into the arguments of an `async` handler.

`json.loads` gives strings, numbers, lists, dicts and nulls. The handler wants
a `UUID`, a `datetime`, `Decimal` prices and nested objects:

    order_id: Annotated[UUID, Process(UUID)]
    lines: Annotated[list[Line], Process(each(to_line))]    a list of objects
    ship_to: Annotated[Address, Process(to_address)]        one nested object
    coupon: Annotated[str | None, Process(optional(str.upper))] = None
                                                            null stays None

A nested object is processed by its own factory (`process(Line)`), so a bad
value deep inside the body is reported with the whole path to it.

Run it with `uv run python -m examples.api`.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pyargprocessors import Process, ProcessArgumentError, each, optional, process


@dataclass(frozen=True, slots=True)
class Line:
    sku: Annotated[str, Process(str.upper)]
    quantity: Annotated[int, Process(int)]
    price: Annotated[Decimal, Process(Decimal)]


@dataclass(frozen=True, slots=True)
class Address:
    city: Annotated[str, Process(str.strip), Process(str.title)]
    postcode: Annotated[str, Process(str)]  # some clients send it as a number


make_line = process(Line)
make_address = process(Address)


def to_line(data: dict[str, Any]) -> Line:
    return make_line(**data)


def to_address(data: dict[str, Any]) -> Address:
    return make_address(**data)


type Lines = Annotated[list[Line], Process(each(to_line))]
type Coupon = Annotated[str | None, Process(optional(str.upper))]


@process
async def create_order(
    order_id: Annotated[UUID, Process(UUID)],
    placed_at: Annotated[datetime, Process(datetime.fromisoformat)],
    lines: Lines,
    ship_to: Annotated[Address, Process(to_address)],
    coupon: Coupon = None,
) -> dict[str, Any]:
    """Create an order. By the time this runs, every argument has its real type."""
    await asyncio.sleep(0)  # stands in for a database call
    total = sum((line.price * line.quantity for line in lines), Decimal(0))
    return {
        "id": str(order_id),
        "placed": f"{placed_at:%Y-%m-%d %H:%M}",
        "items": [f"{line.quantity} x {line.sku}" for line in lines],
        "city": ship_to.city,
        "coupon": coupon,
        "total": str(total),
    }


def error_path(error: ProcessArgumentError) -> str:
    """Return the path to the bad value, following nested failures: `lines.quantity`."""
    cause = error.cause
    return f"{error.argument}.{error_path(cause)}" if _is_nested(cause) else error.argument


def root_cause(error: ProcessArgumentError) -> Exception:
    return root_cause(error.cause) if _is_nested(error.cause) else error.cause


def _is_nested(error: Exception) -> bool:
    return isinstance(error, ProcessArgumentError)


async def handle(body: str) -> tuple[int, dict[str, Any]]:
    """Answer a request body with a status code and a JSON-ready dictionary."""
    try:
        return 201, await create_order(**json.loads(body))
    except ProcessArgumentError as error:  # before `TypeError`, which it also is
        return 422, {"field": error_path(error), "error": str(root_cause(error))}
    except TypeError as error:  # a missing or unknown key
        return 400, {"error": str(error)}


ORDER = {
    "order_id": "8f14e45f-ceea-467f-a9d1-5c2f1c1f2a10",
    "placed_at": "2026-10-09T14:30:00",
    "lines": [
        {"sku": "tea-01", "quantity": "2", "price": "4.50"},
        {"sku": "mug-07", "quantity": 1, "price": "12.00"},
    ],
    "ship_to": {"city": "  damascus ", "postcode": 12345},
    "coupon": None,
}


def main() -> None:
    def request(**changes: Any) -> tuple[int, dict[str, Any]]:
        return asyncio.run(handle(json.dumps({**ORDER, **changes})))

    print(*request())
    print(*request(coupon="autumn")[1].items())
    print(*request(order_id="not-a-uuid"))
    print(*request(lines=[{"sku": "tea-01", "quantity": "two", "price": "4.50"}]))
    print(*request(lines="tea-01"))
    print(*request(gift=True))


if __name__ == "__main__":
    main()
