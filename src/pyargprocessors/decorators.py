"""The decorators that make a function, or a dataclass, process its own arguments.

    @process
    def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0) -> None: ...

    wait("#result", "10")  # timeout is 10.0

    @dataclass(frozen=True)
    class Settings:
        port: Annotated[int, Process(int)] = 8000

    Settings(port="8080")  # Settings(port=8080)

The markers are read once, when the function is decorated, and applied on
every call, before the function runs.
"""

import dataclasses
from collections.abc import Callable, Mapping
from functools import wraps
from inspect import iscoroutinefunction, markcoroutinefunction, signature
from typing import dataclass_transform, overload

from .processors import Process, find_processors, process_arguments


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
    return _processing(fn, find_processors(fn))


@overload
def dataclass[T](cls: type[T], /) -> type[T]: ...


@overload
def dataclass[T](
    cls: None = None,
    /,
    *,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> Callable[[type[T]], type[T]]: ...


@dataclass_transform(field_specifiers=(dataclasses.field, dataclasses.Field))
def dataclass[T](  # noqa: PLR0913
    cls: type[T] | None = None,
    /,
    *,
    init: bool = True,
    repr: bool = True,  # noqa: A002
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> type[T] | Callable[[type[T]], type[T]]:
    """Make a dataclass, like `dataclasses.dataclass`, whose `__init__` processes its arguments.

    Unlike `process(cls)`, which returns a factory function, the class itself
    is returned, so `Settings(port="8080")`, `isinstance` and subclassing work
    as usual. It takes the same options as `dataclasses.dataclass`, with or
    without parentheses. A class with no `__init__` of its own (`init=False`)
    is left as `dataclasses.dataclass` made it.

    Raises:
        InvalidProcessorError: If a `Process` marker is used as the default of a field.
        ProcessArgumentError: Raised by the class when a processor fails.

    Example:
    ```python
    >>> from typing import Annotated
    >>> from pyargprocessors import Process
    >>> @dataclass(frozen=True)
    ... class Settings:
    ...     host: Annotated[str, Process(str.strip)]
    ...     port: Annotated[int, Process(int)] = 8000
    >>> Settings(" localhost ", port="8080")
    Settings(host='localhost', port=8080)
    >>> Settings("localhost")
    Settings(host='localhost', port=8000)
    >>> Settings("localhost", port="http")
    Traceback (most recent call last):
    ...
    pyargprocessors.exceptions.ProcessArgumentError: Argument 'port' with value 'http' failed...

    ```

    """

    def wrap(cls: type[T]) -> type[T]:
        made = dataclasses.dataclass(
            cls,
            init=init,
            repr=repr,
            eq=eq,
            order=order,
            unsafe_hash=unsafe_hash,
            frozen=frozen,
            match_args=match_args,
            kw_only=kw_only,
            slots=slots,
            weakref_slot=weakref_slot,
        )
        own_init = vars(made).get("__init__")

        if own_init is not None:
            made.__init__ = _processing(own_init, find_processors(own_init, name=made.__name__))  # type: ignore[misc]

        return made

    return wrap if cls is None else wrap(cls)


def _processing[**P, R](
    fn: Callable[P, R],
    processors: Mapping[str, tuple[Process, ...]],
) -> Callable[P, R]:
    if not processors:
        return fn

    fn_signature = signature(fn)

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        bound = process_arguments(processors, fn_signature.bind(*args, **kwargs))
        return fn(*bound.args, **bound.kwargs)

    return markcoroutinefunction(wrapper) if iscoroutinefunction(fn) else wrapper
