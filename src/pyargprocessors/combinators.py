"""Build a processor out of another one.

A processor is any function of one value, so these are plain functions that
take a processor and return a new one:

    type Prices = Annotated[list[Decimal], Process(each(Decimal))]
    type Limit = Annotated[int | None, Process(optional(int))]

They combine: `Process(optional(each(int)))` accepts a list of numbers or null.
"""

from collections.abc import Callable, Mapping
from typing import Any


def each(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Return a processor applying `fn` to each item of a collection.

    A list, tuple, set or frozenset stays one; on a dict `fn` is applied to
    each value. A subclass (a named tuple, an `OrderedDict`) becomes the plain
    built-in. Anything else, a string included, is rejected.

    Example:
    ```python
    >>> each(int)(["1", "2"])
    [1, 2]
    >>> each(str.upper)({"size": "l", "milk": "oat"})
    {'size': 'L', 'milk': 'OAT'}
    >>> each(int)("12")
    Traceback (most recent call last):
    ...
    TypeError: expected a list, tuple, set or dict, got '12'

    ```

    """

    def process_each(values: Any) -> Any:
        match values:
            case Mapping():
                return {key: fn(value) for key, value in values.items()}
            case list():
                return [fn(value) for value in values]
            case tuple():
                return tuple(fn(value) for value in values)
            case set():
                return {fn(value) for value in values}
            case frozenset():
                return frozenset(fn(value) for value in values)
            case _:
                msg = f"expected a list, tuple, set or dict, got {values!r}"
                raise TypeError(msg)

    return process_each


def optional(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Return a processor applying `fn` to every value except `None`, which is kept.

    Example:
    ```python
    >>> optional(int)("2")
    2
    >>> optional(int)(None) is None
    True

    ```

    """

    def process_optional(value: Any) -> Any:
        return None if value is None else fn(value)

    return process_optional
