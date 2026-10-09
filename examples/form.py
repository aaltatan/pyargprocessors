"""Processing: turn raw strings from a web form into typed function arguments.

A shop lets users search its catalog with a form. Everything a form sends is a
string ("4", "yes", "  HeadPhones "), while the search function wants numbers,
booleans, clean text and even loaded data. `Process` bridges that gap, right
next to the parameter it applies to:

    limit: Annotated[int, Process(int)] = 3   one parameter
    type Money = Annotated[Decimal, Process(Decimal)]
                                              named once, reused in many functions
    type Text = Annotated[str, Process(str.strip), Process(str.lower)]
                                              several processors, left to right
    **fields: Text                            every extra keyword
    type Names = Annotated[frozenset[str], Process(load_names)]
                                              the form sends a path, the function gets the data
    Process(optional(Decimal))                an empty field (None) stays None
    Process(each(str.lower))                  every item of a list

Run it with `uv run python -m examples.form`.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, each, optional, process, process_value


@dataclass(frozen=True, slots=True)
class Product:
    name: str
    brand: str
    price: Decimal
    stars: float
    in_stock: bool


# Stands in for the file system, to keep the example self-contained.
FILES = {"discontinued.txt": "Travel Headphones\nKids Headphones\n"}


def to_bool(text: str) -> bool:
    """Read checkbox-like values: yes/no, true/false, on/off, 1/0."""
    return text.strip().lower() in {"yes", "true", "on", "1"}


def load_names(path: str) -> frozenset[str]:
    """Read one product name per line from a file."""
    return frozenset(line.strip().lower() for line in FILES[path].splitlines())


# Processed types, named once and reused by the functions below.
type Money = Annotated[Decimal, Process(Decimal)]
type MaybeMoney = Annotated[Decimal | None, Process(optional(Decimal))]
type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Names = Annotated[frozenset[str], Process(load_names)]

CATALOG = (
    Product("Studio Headphones", "Sonic", Decimal("149.00"), 4.7, in_stock=True),
    Product("Travel Headphones", "Sonic", Decimal("89.00"), 4.2, in_stock=True),
    Product("Budget Headphones", "Sonic", Decimal("19.00"), 3.1, in_stock=True),
    Product("Pro Headphones", "Sonic", Decimal("349.00"), 4.9, in_stock=True),
    Product("Kids Headphones", "Sonic", Decimal("39.00"), 4.4, in_stock=False),
    Product("Bass Headphones", "Boom", Decimal("129.00"), 4.6, in_stock=True),
    Product("Desk Lamp", "Lumen", Decimal("45.00"), 4.8, in_stock=True),
)


@process
def search(  # noqa: PLR0913
    text: Text,
    *,
    low: Money = Decimal(0),
    high: MaybeMoney = None,
    in_stock: Annotated[bool, Process(to_bool)] = False,
    exclude: Names = frozenset(),
    limit: Annotated[int, Process(int)] = 3,
    **fields: Text,
) -> list[Product]:
    """Return the best rated products matching a search form."""
    found = [
        product
        for product in CATALOG
        if text in product.name.lower()
        and low <= product.price
        and (high is None or product.price <= high)
        and (product.in_stock or not in_stock)
        and product.name.lower() not in exclude
        and all(getattr(product, key).lower() == value for key, value in fields.items())
    ]
    return sorted(found, key=lambda product: product.stars, reverse=True)[:limit]


@process
def brands(names: Annotated[list[str], Process(each(str.lower))]) -> list[str]:
    """Return the known brands among the given names."""
    known = {product.brand.lower() for product in CATALOG}
    return [name for name in names if name in known]


# What the web form sends: every value is a raw, untrimmed string, an empty field is None.
FORM = {
    "text": "  HeadPhones ",
    "low": "20",
    "high": None,
    "in_stock": "yes",
    "exclude": "discontinued.txt",
    "limit": "2",
    "brand": " SONIC ",
}


def main() -> None:
    for product in search(**FORM):  # type: ignore[arg-type]
        print(f"{product.name} ({product.brand}) ${product.price} {product.stars}*")

    # Defaults are not processed: only `text` is.
    print([product.name for product in search(" LAMP ")])

    # `each` processes every item of a list.
    print(brands(["SONIC", "Acme", "Boom"]))

    # A processed type works on a single value too, without any function.
    print(repr(process_value(Money, "19.90")))

    # A bad value fails before the function runs, and says which field it was.
    try:
        search("headphones", limit="two")  # type: ignore[arg-type]
    except ProcessArgumentError as error:
        print(f"ProcessArgumentError on '{error.argument}': {error}")


if __name__ == "__main__":
    main()
