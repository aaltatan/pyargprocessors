# Building on top

A library that binds arguments itself, a rule factory, a step factory, a command dispatcher,
does not need `@process`. It uses the two functions the decorator is made of:

- `find_processors(fn)` **once**, when the function is registered;
- `process_arguments(processors, bound)` every time arguments are bound.

```python
from inspect import Signature, signature
from typing import Annotated

from pyargprocessors import Process, find_processors, process_arguments

type Text = Annotated[str, Process(str.strip), Process(str.lower)]


def rule(fn):
    processors = find_processors(fn, skip=1)  # the first parameter is the object under test
    arguments = Signature(list(signature(fn).parameters.values())[1:])

    def factory(*args, **kwargs):
        bound = process_arguments(processors, arguments.bind(*args, **kwargs))
        return lambda obj: fn(obj, *bound.args, **bound.kwargs)

    return factory


@rule
def name__eq(name: str, value: Text) -> bool:
    return name == value


assert name__eq("  Tea ")("tea")  # "  Tea " was processed once, when the rule was built
```

## `find_processors(fn, *, name=None, skip=0)`

Returns `{parameter: (Process, ...)}` for every parameter of `fn` that has markers.

- `skip=n` says the first `n` parameters are not passed as arguments, so a marker on them
  raises `InvalidProcessorError` instead of being silently ignored.
- `name=` is how error messages call the function, for when the public name differs from
  `fn.__name__`.
- A builtin without a signature returns `{}`.

```python
from typing import Annotated

from pyargprocessors import InvalidProcessorError, Process, find_processors


def wait(selector: str, timeout: Annotated[float, Process(float)] = 5.0): ...


assert find_processors(wait) == {"timeout": (Process(float),)}


def bad(user: Annotated[str, Process(str)], years: int) -> bool: ...


try:
    find_processors(bad, name="rule bad", skip=1)
except InvalidProcessorError as error:
    assert str(error) == "'rule bad' cannot process 'user': it is not passed as an argument"
```

## `process_arguments(processors, bound)`

Returns **new** `BoundArguments` with every marked value processed; values of unmarked
parameters are kept and the given `bound` is left untouched. `*args` items and `**kwargs`
values are processed one by one.

```python
from inspect import signature

from pyargprocessors import Process, process_arguments


def brew(shots: int, *toppings: str, **extras: str): ...


bound = signature(brew).bind("2", " foam ", " cocoa ", size="L")
processors = {"shots": (Process(int),), "toppings": (Process(str.strip),)}

assert process_arguments(processors, bound).arguments == {
    "shots": 2,
    "toppings": ("foam", "cocoa"),
    "extras": {"size": "L"},
}
assert bound.arguments["shots"] == "2"  # untouched
```

Defaults are not in `bound.arguments`, so they are not processed. A library that wants them
processed too calls `bound.apply_defaults()` first.

## `input_annotation(processor)`

The type hint of the processor's own parameter, or `None` when it has none (`int`, `Decimal`,
an enum class). A JSON schema uses it to describe what the caller must **send**, and falls
back to the parameter's type when it is `None`.

```python
from pyargprocessors import Process, input_annotation


def load_rows(path: str) -> list[dict]: ...


assert input_annotation(Process(load_rows)) is str
assert input_annotation(Process(int)) is None
```

## Reading `Annotated` metadata

For libraries that add markers of their own:

- `annotated_metadata(annotation)` returns the extra arguments of `Annotated[...]`, looking
  through `type` aliases, generic ones included; inner metadata comes first.
- `resolved_annotations(fn)` returns the annotations describing a call to `fn`, with strings
  evaluated when possible. For a class it reads `__init__` (or `__new__` when there is no
  `__init__`), for a callable object `__call__`, for a `functools.partial` the wrapped function.

```python
from typing import Annotated

from pyargprocessors import annotated_metadata, resolved_annotations

type Port = Annotated[int, "tcp", 8080]

assert annotated_metadata(Port) == ("tcp", 8080)
assert annotated_metadata(Annotated[Port, "outer"]) == ("tcp", 8080, "outer")
assert annotated_metadata(int) == ()


def wait(selector: "str", timeout: float = 5.0): ...


assert resolved_annotations(wait) == {"selector": str, "timeout": float}
```

The [rules recipe](../recipes.md#a-rules-library) puts all of these together.
