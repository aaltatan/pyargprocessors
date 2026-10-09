"""Argument processing: turn the raw values a function receives into the objects it wants.

Values often come from JSON, a web form or a command line, where everything is
a string, number, boolean, list, dict or null, while functions want dates,
decimals, enums, clean text or loaded data. Mark the parameter with
`Process(fn)` inside `Annotated` and `fn` is applied to the value passed for it:

    @process
    def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0) -> None: ...

    wait("#result", "10")  # timeout is 10.0

Name a processed type once with a `type` alias and reuse it in many functions:

    type Text = Annotated[str, Process(str.strip), Process(str.lower)]
    type Rows = Annotated[list[Row], Process(load_rows)]  # the caller passes a path

Only values that are actually passed are processed. Default values never are.

`process` is the ready-made decorator. A library that binds arguments itself
(a rule factory, a step factory) uses `find_processors` once, when the function
is decorated, and `process_arguments` every time arguments are bound.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import reduce
from inspect import BoundArguments, Parameter, signature
from typing import Any

from .annotations import annotated_metadata, resolved_annotations
from .exceptions import InvalidProcessorError, ProcessArgumentError


@dataclass(frozen=True, slots=True)
class Process:
    """Mark a parameter: apply `fn` to the value passed for it.

    Use it inside `Annotated`, directly or through a `type` alias. Several
    markers on one parameter run left to right. On `*args` the function is
    applied to each item, on `**kwargs` to each value.

    Example:
    ```python
    >>> from typing import Annotated
    >>> from pyargprocessors import process
    >>> type Text = Annotated[str, Process(str.strip), Process(str.lower)]
    >>> @process
    ... def order(name: Text, amount: Annotated[int, Process(int)] = 1) -> tuple[str, int]:
    ...     return name, amount
    >>> order("  Tea ", "2")
    ('tea', 2)
    >>> order(" Milk")
    ('milk', 1)
    >>> order("tea", "two")
    Traceback (most recent call last):
    ...
    pyargprocessors.exceptions.ProcessArgumentError: Argument 'amount' with value 'two' failed...

    ```

    """

    fn: Callable[[Any], Any]

    def __post_init__(self) -> None:
        if not callable(self.fn):
            msg = f"Process needs a callable, got {self.fn!r}"
            raise InvalidProcessorError(msg)


def find_processors(
    fn: Callable[..., Any],
    *,
    name: str | None = None,
    skip: int = 0,
) -> dict[str, tuple[Process, ...]]:
    """Return the `Process` markers of every parameter of `fn` that has some.

    `name` is how error messages call `fn`, its own name by default. The first
    `skip` parameters of `fn` are not passed as arguments (the subject of a
    step, the object a rule tests), so they can carry no marker.

    Raises:
        InvalidProcessorError: If a marker is used as a default value, or sits on a skipped
            parameter.

    Example:
    ```python
    >>> from typing import Annotated
    >>> def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0): ...
    >>> find_processors(wait)
    {'timeout': (Process(fn=<class 'float'>),)}

    ```

    """
    label = name or getattr(fn, "__name__", repr(fn))

    try:
        parameters = signature(fn).parameters
    except ValueError:  # builtins without a signature carry no markers
        return {}

    annotations = resolved_annotations(fn)

    for parameter in parameters.values():
        if isinstance(parameter.default, Process):
            msg = (
                f"'{label}' uses Process as the default of '{parameter.name}'; write it as "
                f"`{parameter.name}: Annotated[<type>, Process(...)]` so the parameter can keep "
                "a real default"
            )
            raise InvalidProcessorError(msg)

    found = {parameter: _markers(annotations.get(parameter)) for parameter in parameters}
    processors = {parameter: markers for parameter, markers in found.items() if markers}

    for parameter in list(parameters)[:skip]:
        if parameter in processors:
            msg = f"'{label}' cannot process '{parameter}': it is not passed as an argument"
            raise InvalidProcessorError(msg)

    return processors


def process_arguments(
    processors: Mapping[str, tuple[Process, ...]],
    bound: BoundArguments,
) -> BoundArguments:
    """Return new bound arguments with every marked value processed.

    Values of unmarked parameters are kept as they are, and the original
    `bound` object is left untouched.

    Raises:
        ProcessArgumentError: If a processor raises; the original exception is chained.

    Example:
    ```python
    >>> def brew(shots: int, *toppings: str, **extras: str): ...
    >>> bound = signature(brew).bind("2", " foam ", " cocoa ", size="L", note="Hot")
    >>> strip, lower = (Process(str.strip),), (Process(str.lower),)
    >>> processors = {"shots": (Process(int),), "toppings": strip, "extras": lower}
    >>> process_arguments(processors, bound).arguments
    {'shots': 2, 'toppings': ('foam', 'cocoa'), 'extras': {'size': 'l', 'note': 'hot'}}

    ```

    """
    parameters = bound.signature.parameters
    processed = {
        name: _process_parameter(processors.get(name, ()), parameters[name], value)
        for name, value in bound.arguments.items()
    }
    return BoundArguments(bound.signature, processed)  # type: ignore[arg-type]


def process_value(annotation: Any, value: Any, *, name: str = "value") -> Any:
    """Apply the `Process` markers of `annotation` to one value.

    It lets a processed type be reused outside a function call: on one field of
    a form, on a setting, in a test. An annotation without markers returns the
    value as it is. `name` is how a failure calls the value.

    Raises:
        ProcessArgumentError: If a processor raises; the original exception is chained.

    Example:
    ```python
    >>> from typing import Annotated
    >>> type Text = Annotated[str, Process(str.strip), Process(str.lower)]
    >>> process_value(Text, "  Tea ")
    'tea'
    >>> process_value(str, "  Tea ")
    '  Tea '

    ```

    """
    return _process_value(_markers(annotation), name, value)


def input_annotation(processor: Process) -> Any:
    """Return the annotation of the value `processor` accepts, or `None` if it has none.

    A JSON schema uses it to describe what the caller must send.

    Example:
    ```python
    >>> def load_rows(path: str) -> list[dict]: ...
    >>> input_annotation(Process(load_rows))
    <class 'str'>
    >>> input_annotation(Process(int)) is None
    True

    ```

    """
    try:
        first = next(iter(signature(processor.fn).parameters), None)
    except (TypeError, ValueError):  # builtins without a signature
        return None

    return resolved_annotations(processor.fn).get(first) if first else None


def _markers(annotation: Any) -> tuple[Process, ...]:
    return tuple(item for item in annotated_metadata(annotation) if isinstance(item, Process))


def _process_parameter(markers: tuple[Process, ...], parameter: Parameter, value: Any) -> Any:
    match parameter.kind:
        case Parameter.VAR_POSITIONAL:
            return tuple(_process_value(markers, parameter.name, item) for item in value)
        case Parameter.VAR_KEYWORD:
            return {key: _process_value(markers, key, item) for key, item in value.items()}
        case _:
            return _process_value(markers, parameter.name, value)


def _process_value(markers: tuple[Process, ...], name: str, value: Any) -> Any:
    try:
        return reduce(lambda current, marker: marker.fn(current), markers, value)
    except Exception as error:
        raise ProcessArgumentError(name, value, error) from error
