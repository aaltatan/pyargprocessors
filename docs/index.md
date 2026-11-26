# pyargprocessors

**Turn the raw arguments a function receives into the objects it wants.**

Values that come from JSON, a web form, a command line or an environment variable are
strings, numbers, booleans, lists, dicts or null. Functions want dates, decimals, enums,
clean text or loaded data. Usually the conversion ends up at the top of every function body:

```py
def search(text, low="0", limit="3"):
    text = text.strip().lower()
    low = Decimal(low)
    limit = int(limit)
    ...
```

With `pyargprocessors` the conversion is part of the signature, written as a `Process`
marker next to the parameter, and the body starts with real work.

## A first taste

```python
from decimal import Decimal
from typing import Annotated

from pyargprocessors import Process, process

type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Money = Annotated[Decimal, Process(Decimal)]


@process
def add_item(name: Text, price: Money, quantity: Annotated[int, Process(int)] = 1) -> str:
    return f"{quantity} x {name} = ${price * quantity}"


assert add_item("  Green TEA ", "2.50", "3") == "3 x green tea = $7.50"
assert add_item("Milk", "1.20") == "1 x milk = $1.20"
```

`Text` and `Money` are named once and reused. `quantity` was not passed in the second call,
so its default `1` was used as it is: defaults are never processed.

## What you get

- A **processor** is any function of one value: `int`, `Decimal`, `str.strip`,
  `date.fromisoformat`, an enum class, your own `load_rows`.
- The marker sits inside `Annotated`, so the parameter keeps its real type and its real default.
- A `type` alias names a processed type once; several processors run left to right.
- `*args` and `**kwargs` are processed item by item.
- A failure says which argument and which value, and keeps the original exception.
- `@process` works on functions, methods and `async` functions; `process(cls)` on classes,
  dataclasses and named tuples; `@dataclass` makes a dataclass process its own fields.
- A processor that raises is a validator.
- Libraries that bind arguments themselves reuse the same two building blocks.
- **Zero dependencies**, Python 3.12+.

It is the argument processing of its siblings
[pyspecification](https://github.com/aaltatan/pyspecification) (predicates) and
[pyflowstep](https://github.com/aaltatan/pyflowstep) (flows) as a package of its own.

## Where next

- [Installation](install.md)
- [User guide](guide/index.md): every piece, one page each.
- [Recipes](recipes.md): forms, settings, a CLI, a JSON API, webhooks, a rules library.
- [Reference](reference/index.md): the API, the exceptions, and the corners decided on purpose.
