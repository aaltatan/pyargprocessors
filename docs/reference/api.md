# API

| Name | Kind | Description |
| --- | --- | --- |
| [`Process(fn)`](#process) | marker | Apply `fn` to the value passed for a parameter |
| [`process`](#process_1) | decorator | Apply the markers of a function, or of a constructor, on every call |
| [`dataclass`](#dataclass) | decorator | `dataclasses.dataclass` whose `__init__` applies the markers of its fields |
| [`process_value`](#process_value) | function | Apply the markers of an annotation to one value |
| [`each`](#each) | function | A processor applying `fn` to each item of a collection |
| [`optional`](#optional) | function | A processor applying `fn` to every value except `None` |
| [`find_processors`](#find_processors) | function | The markers of every parameter of `fn` that has some |
| [`process_arguments`](#process_arguments) | function | New `BoundArguments` with every marked value processed |
| [`input_annotation`](#input_annotation) | function | The type hint of the value a processor accepts, or `None` |
| [`annotated_metadata`](#annotated_metadata) | function | The extra arguments of `Annotated[...]`, looking through `type` aliases |
| [`resolved_annotations`](#resolved_annotations) | function | The annotations describing a call to `fn`, with strings evaluated |
| `ProcessArgumentError` | exception | A processor failed; see [Exceptions](exceptions.md) |
| `InvalidProcessorError` | exception | A marker that cannot work; see [Exceptions](exceptions.md) |
| `PyargprocessorsError` | exception | Base class of both |

## Markers and decorators

### `Process`

```py
@dataclass(frozen=True, slots=True)
class Process:
    fn: Callable[[Any], Any]
```

Mark a parameter: apply `fn` to the value passed for it. Use it inside `Annotated`, directly
or through a `type` alias. Several markers on one parameter run left to right. On `*args` the
function is applied to each item, on `**kwargs` to each value.

Raises `InvalidProcessorError` if `fn` is not callable.

Guide: [Process and @process](../guide/process.md).

### `process`

```py
def process[**P, R](fn: Callable[P, R], /) -> Callable[P, R]
```

Apply the `Process` markers of `fn` to the arguments of every call. Arguments are bound to
the signature first. A function without markers is returned as it is. `async` functions stay
`async`. On a class, returns a factory function built from its constructor.

Raises `InvalidProcessorError` (on decoration) if a marker is used as a default value; the
decorated function raises `ProcessArgumentError` when a processor fails.

Guide: [Process and @process](../guide/process.md), [Classes](../guide/classes.md).

### `dataclass`

```py
def dataclass(
    cls=None, /, *,
    init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False,
    match_args=True, kw_only=False, slots=False, weakref_slot=False,
)
```

Make a dataclass, like `dataclasses.dataclass`, whose generated `__init__` processes its
arguments. Works with or without parentheses and returns the class. A class with no
`__init__` of its own (`init=False`) is left as `dataclasses.dataclass` made it. Decorated
with `dataclass_transform`.

Raises `InvalidProcessorError` if a marker is used as the default of a field; the class raises
`ProcessArgumentError` when a processor fails.

Guide: [Classes and dataclasses](../guide/classes.md).

## Processing values

### `process_value`

```py
def process_value(annotation: Any, value: Any, *, name: str = "value") -> Any
```

Apply the `Process` markers of `annotation` to one value. An annotation without markers
returns the value as it is. `name` is how a failure calls the value.

Raises `ProcessArgumentError` if a processor raises.

Guide: [Processed types](../guide/types.md#one-value-no-function-process_value).

### `each`

```py
def each(fn: Callable[[Any], Any]) -> Callable[[Any], Any]
```

Return a processor applying `fn` to each item of a list, tuple, set or frozenset (keeping its
type) and to each value of a dict. A subclass becomes the plain built-in. Anything else
raises `TypeError`.

### `optional`

```py
def optional(fn: Callable[[Any], Any]) -> Callable[[Any], Any]
```

Return a processor applying `fn` to every value except `None`, which is kept.

Guide: [each and optional](../guide/combinators.md).

## Building blocks

### `find_processors`

```py
def find_processors(
    fn: Callable[..., Any], *, name: str | None = None, skip: int = 0,
) -> dict[str, tuple[Process, ...]]
```

Return the `Process` markers of every parameter of `fn` that has some. `name` is how error
messages call `fn`. The first `skip` parameters are not passed as arguments and can carry no
marker. A builtin without a signature returns `{}`.

Raises `InvalidProcessorError` if a marker is used as a default value or sits on a skipped
parameter.

### `process_arguments`

```py
def process_arguments(
    processors: Mapping[str, tuple[Process, ...]], bound: BoundArguments,
) -> BoundArguments
```

Return new bound arguments with every marked value processed. Unmarked values are kept, and
`bound` is left untouched.

Raises `ProcessArgumentError` if a processor raises.

### `input_annotation`

```py
def input_annotation(processor: Process) -> Any
```

Return the annotation of the first parameter of `processor.fn`, or `None` if it has none
(including builtins without a signature).

### `annotated_metadata`

```py
def annotated_metadata(annotation: Any) -> tuple[Any, ...]
```

Return the extra arguments of `Annotated[...]`, looking through `type` aliases, subscripted
generic aliases included. Inner metadata comes before outer. A non-`Annotated` annotation
gives `()`.

### `resolved_annotations`

```py
def resolved_annotations(fn: Callable[..., Any]) -> dict[str, Any]
```

Return the annotations describing a call to `fn`, with strings evaluated when possible. For a
class this is its `__init__` (or `__new__` when it defines no `__init__`), for a callable
object its `__call__`, for a `functools.partial` the function it wraps. A name that cannot be
evaluated stays a string; the others are still evaluated.

Guide: [Building on top](../guide/building-on-top.md).
