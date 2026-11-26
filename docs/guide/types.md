# Processed types

## Name it once, reuse it

A `type` alias gives a processed type a name, so many functions can share it:

```python
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, process

type Money = Annotated[Decimal, Process(Decimal)]
type Text = Annotated[str, Process(str.strip), Process(str.lower)]


@process
def price_between(low: Money, high: Money) -> tuple[Decimal, Decimal]:
    return low, high


@process
def search(text: Text, min_stars: Annotated[float, Process(float)] = 0) -> tuple[str, float]:
    return text, min_stars


assert price_between("10", "20.5") == (Decimal("10"), Decimal("20.5"))
assert search(" HeadPhones ", "4.5") == ("headphones", 4.5)
```

## Aliases build on aliases

`Annotated[Text, Process(...)]` runs the processors of `Text` first, then its own:

```python
from typing import Annotated

from pyargprocessors import Process, process_value

type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Slug = Annotated[Text, Process(lambda text: text.replace(" ", "-"))]

assert process_value(Slug, "  Green Tea ") == "green-tea"
```

Generic aliases work too: `type Tagged[T] = Annotated[T, Process(...)]` and `Tagged[int]`.

## Loading data from a value

Because a processor is any function of one value, the caller can pass a path and the function
can receive what was loaded from it:

```py
def load_names(path: str) -> frozenset[str]:
    return frozenset(Path(path).read_text().splitlines())


type Names = Annotated[frozenset[str], Process(load_names)]


@process
def exclude(products: list[Product], names: Names) -> list[Product]:
    return [product for product in products if product.name not in names]


exclude(products, "discontinued.txt")
```

## One value, no function: `process_value`

`process_value(annotation, value, *, name="value")` applies the markers of an annotation to a
single value, so a processed type is useful outside a function call too: on one field of a
form, on a setting, in a test.

```python
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, process_value

type Money = Annotated[Decimal, Process(Decimal)]

assert process_value(Money, "19.90") == Decimal("19.90")
assert process_value(str, "  Tea ") == "  Tea "  # no markers: the value as it is

try:
    process_value(Money, "free", name="price")
except ProcessArgumentError as error:
    assert error.argument == "price"  # `name` is how the failure calls the value
```

## `from __future__ import annotations`

String annotations work: they are evaluated when the function is decorated. A name imported
only under `TYPE_CHECKING` stays a string and does not hide the other markers. An alias
defined **inside a function** cannot be found, so define aliases at module level.
