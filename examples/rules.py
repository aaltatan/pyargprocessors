"""Building on top: a tiny rules library that processes the arguments of its rules.

A library that binds arguments itself does not use `@process`. It reads the
markers once, when a function is registered, and applies them when it binds
arguments. This one turns `(object, *arguments) -> bool` functions into rules
that are built first and tested later, from Python or from JSON:

    age__gte("18")(user)                                 Python
    {"rule": "age__gte", "args": ["18"]}                 JSON

- `find_processors(fn, skip=1)` because the first parameter is the object under
  test: nobody passes it when the rule is built, so it cannot be processed.
- `process_arguments(processors, bound)` once per rule, not once per object.
- `input_annotation(marker)` to tell whoever writes the JSON what to send.

Run it with `uv run python -m examples.rules`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from inspect import Signature, signature
from pathlib import PurePosixPath
from typing import Annotated, Any, get_args, get_origin

from pyargprocessors import (
    InvalidProcessorError,
    Process,
    ProcessArgumentError,
    find_processors,
    input_annotation,
    process_arguments,
    resolved_annotations,
)

type Predicate[T] = Callable[[T], bool]

RULES: dict[str, Callable[..., Predicate[Any]]] = {}
SENDS: dict[str, dict[str, str]] = {}


def rule[T](fn: Callable[..., bool]) -> Callable[..., Predicate[T]]:
    """Turn `fn(obj, *arguments)` into `factory(*arguments) -> predicate(obj)`."""
    name = fn.__name__
    processors = find_processors(fn, name=f"rule {name}", skip=1)
    arguments = Signature(list(signature(fn).parameters.values())[1:])

    def factory(*args: Any, **kwargs: Any) -> Predicate[T]:
        bound = process_arguments(processors, arguments.bind(*args, **kwargs))
        return lambda obj: fn(obj, *bound.args, **bound.kwargs)

    RULES[name] = factory
    SENDS[name] = {
        parameter: _sent_type(fn, parameter, processors.get(parameter, ()))
        for parameter in arguments.parameters
    }
    return factory


def _sent_type(fn: Callable[..., Any], parameter: str, markers: tuple[Process, ...]) -> str:
    """Name the type the JSON must send: what the first processor accepts, if it says so."""
    sent = input_annotation(markers[0]) if markers else None
    annotation = _plain_type(resolved_annotations(fn).get(parameter)) if sent is None else sent
    return annotation.__name__


def _plain_type(annotation: Any) -> Any:
    """Return `int` for `Annotated[int, ...]`, also behind a `type` alias."""
    annotation = getattr(annotation, "__value__", annotation)
    return get_args(annotation)[0] if get_origin(annotation) is Annotated else annotation


def compile_rules[T](definition: list[dict[str, Any]]) -> Predicate[T]:
    """Build one predicate that passes when every rule of a JSON definition passes."""
    predicates = [RULES[item["rule"]](*item.get("args", [])) for item in definition]
    return lambda obj: all(predicate(obj) for predicate in predicates)


@dataclass(frozen=True, slots=True)
class User:
    name: str
    born: date
    country: str


# Stands in for the file system, to keep the example self-contained.
FILES = {"lists/blocked.txt": "mallory\ntrudy\n"}
LOADED: list[str] = []


def load_names(path: str) -> frozenset[str]:
    """Read one name per line from a file."""
    LOADED.append(path)
    return frozenset(FILES[PurePosixPath(path).as_posix()].split())


type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Names = Annotated[frozenset[str], Process(load_names)]


@rule
def age__gte(user: User, years: Annotated[int, Process(int)], on: date = date(2026, 10, 9)) -> bool:
    return (on - user.born).days >= years * 365.25


@rule
def country__in(user: User, *countries: Text) -> bool:
    return user.country.lower() in countries


@rule
def name__not_in(user: User, names: Names) -> bool:
    return user.name.lower() not in names


USERS = (
    User("Ada", date(1990, 12, 10), "UK"),
    User("Mallory", date(1985, 3, 2), "UK"),
    User("Tim", date(2015, 6, 8), "UK"),
    User("Linus", date(1969, 12, 28), "FI"),
)

# What a JSON file holds: every argument is a raw string.
DEFINITION = [
    {"rule": "age__gte", "args": ["18"]},
    {"rule": "country__in", "args": [" uk ", "IE"]},
    {"rule": "name__not_in", "args": ["lists/blocked.txt"]},
]


def main() -> None:
    allowed = compile_rules(DEFINITION)
    print([user.name for user in USERS if allowed(user)])

    # The file was read once, when the rule was built, not once per user.
    print(LOADED)

    # What the JSON must send: a path for `names`, not a set of names.
    print(SENDS)

    try:
        compile_rules([{"rule": "age__gte", "args": ["eighteen"]}])
    except ProcessArgumentError as error:
        print(f"ProcessArgumentError: {error}")

    # The object under test is not an argument, so a marker on it is a mistake.
    try:

        @rule
        def bad(user: Annotated[User, Process(str)], years: int) -> bool:
            return bool(user and years)

    except InvalidProcessorError as error:
        print(f"InvalidProcessorError: {error}")


if __name__ == "__main__":
    main()
