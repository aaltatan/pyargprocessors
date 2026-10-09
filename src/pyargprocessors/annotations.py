"""Read the annotations that carry markers such as `Process`."""

from collections.abc import Callable
from functools import partial
from inspect import get_annotations, isroutine, unwrap
from typing import Annotated, Any, TypeAliasType, get_args, get_origin


def resolved_annotations(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return the annotations describing a call to `fn`, with strings evaluated when possible.

    For a class this is its `__init__` (or its `__new__` when it defines no
    `__init__`, like a `NamedTuple`), for a callable object its `__call__`, and
    for a `functools.partial` the function it wraps.

    A name that cannot be evaluated, such as one imported only for type
    checkers, is left as a string; the other annotations are still evaluated.

    Example:
    ```python
    >>> def wait(selector: "str", timeout: float = 5.0): ...
    >>> resolved_annotations(wait)
    {'selector': <class 'str'>, 'timeout': <class 'float'>}

    ```

    """
    target = _annotated_function(fn)

    try:
        return get_annotations(target, eval_str=True)
    except NameError:
        scope = getattr(unwrap(target), "__globals__", {})
        return {
            name: _evaluated(annotation, scope)
            for name, annotation in get_annotations(target).items()
        }


def annotated_metadata(annotation: Any) -> tuple[Any, ...]:
    """Return the extra arguments of `Annotated[...]`, looking through `type` aliases.

    Example:
    ```python
    >>> type Port = Annotated[int, "tcp", 8080]
    >>> annotated_metadata(Port)
    ('tcp', 8080)
    >>> annotated_metadata(int)
    ()
    >>> type Tagged[T] = Annotated[T, "tag"]
    >>> annotated_metadata(Tagged[int])
    ('tag',)
    >>> annotated_metadata(Annotated[Tagged[Port], "outer"])
    ('tcp', 8080, 'tag', 'outer')
    >>> type Fixed[T] = Annotated[int, "fixed"]
    >>> annotated_metadata(Fixed[str])
    ('fixed',)

    ```

    """
    annotation = _alias_value(annotation)

    if get_origin(annotation) is not Annotated:
        return ()

    inner, *metadata = get_args(annotation)
    return (*annotated_metadata(inner), *metadata)


def _alias_value(annotation: Any) -> Any:
    """Return what a `type` alias stands for, also when it is subscripted (`Alias[int]`)."""
    while True:
        origin = get_origin(annotation)

        if isinstance(annotation, TypeAliasType):
            annotation = annotation.__value__
        elif isinstance(origin, TypeAliasType):
            annotation = _substituted(origin.__value__, get_args(annotation))
        else:
            return annotation


def _substituted(value: Any, arguments: tuple[Any, ...]) -> Any:
    try:
        return value[arguments]
    except TypeError:  # the alias does not use its type parameters
        return value


def _evaluated(annotation: Any, scope: dict[str, Any]) -> Any:
    """Evaluate one string annotation the way `get_annotations(eval_str=True)` does."""
    if not isinstance(annotation, str):
        return annotation

    try:
        return eval(annotation, scope)  # noqa: S307
    except NameError:
        return annotation


def _annotated_function(fn: Callable[..., Any]) -> Callable[..., Any]:
    if isinstance(fn, partial):
        return _annotated_function(fn.func)

    if isinstance(fn, type):
        return fn.__new__ if fn.__init__ is object.__init__ else fn.__init__

    return fn if isroutine(fn) else type(fn).__call__
