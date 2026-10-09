"""The decorator that makes a plain function process its own arguments.

    @process
    def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0) -> None: ...

    wait("#result", "10")  # timeout is 10.0

The markers are read once, when the function is decorated, and applied on
every call, before the function runs.
"""

from collections.abc import Callable
from functools import wraps
from inspect import iscoroutinefunction, markcoroutinefunction, signature

from .processors import find_processors, process_arguments


def process[**P, R](fn: Callable[P, R], /) -> Callable[P, R]:
    """Apply the `Process` markers of `fn` to the arguments of every call.

    Arguments are bound to the signature first, so a missing or extra argument
    raises the usual `TypeError` before any processor runs. A function without
    markers is returned as it is. `async` functions stay `async`.

    Raises:
        InvalidProcessorError: If a `Process` marker is used as a default value.
        ProcessArgumentError: Raised by the decorated function when a processor fails.

    Example:
    ```python
    >>> from decimal import Decimal
    >>> from typing import Annotated
    >>> from pyargprocessors import Process
    >>> type Money = Annotated[Decimal, Process(Decimal)]
    >>> @process
    ... def total(price: Money, *fees: Money, count: Annotated[int, Process(int)] = 1) -> Decimal:
    ...     return price * count + sum(fees)
    >>> total("2.50", "0.25", count="2")
    Decimal('5.25')
    >>> total("2.50")
    Decimal('2.50')
    >>> total("free")
    Traceback (most recent call last):
    ...
    pyargprocessors.exceptions.ProcessArgumentError: Argument 'price' with value 'free' failed...

    ```

    """
    processors = find_processors(fn)

    if not processors:
        return fn

    fn_signature = signature(fn)

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        bound = process_arguments(processors, fn_signature.bind(*args, **kwargs))
        return fn(*bound.args, **bound.kwargs)

    return markcoroutinefunction(wrapper) if iscoroutinefunction(fn) else wrapper
