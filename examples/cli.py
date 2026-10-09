"""Command line: turn `argv` strings into the arguments of command functions.

A to-do tool takes its commands from the command line, where everything is a
string: `add " Buy milk " --due=tomorrow --priority=HIGH --tags=Home,shop`.
Each command is a plain function, and its signature says what it wants:

    due: Day = None                     "today", "tomorrow", "+3" or an ISO date
    priority: Level = Priority.NORMAL   an enum, whatever the case typed
    tags: Tags = frozenset()            "Home,shop" becomes {"home", "shop"}
    *ids: Annotated[int, Process(int)]  every remaining word

The dispatcher knows nothing about types: it hands the raw words to the command.

Run it with `uv run python -m examples.cli`.
"""

from collections.abc import Callable
from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, each, process

# A fixed "today", to keep the example reproducible.
TODAY = date(2026, 10, 9)


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


def parse_day(text: str) -> date:
    """Read "today", "tomorrow", "+3" (days from today) or an ISO date."""
    match text.strip().lower():
        case "today":
            return TODAY
        case "tomorrow":
            return TODAY + timedelta(days=1)
        case offset if offset.startswith("+"):
            return TODAY + timedelta(days=int(offset))
        case day:
            return date.fromisoformat(day)


def split_commas(text: str) -> frozenset[str]:
    return frozenset(part.strip() for part in text.split(",") if part.strip())


type Title = Annotated[str, Process(str.strip), Process(str.capitalize)]
type Day = Annotated[date | None, Process(parse_day)]
type Level = Annotated[Priority, Process(str.lower), Process(Priority)]
type Tags = Annotated[frozenset[str], Process(split_commas), Process(each(str.lower))]

COMMANDS: dict[str, Callable[..., str]] = {}
TODOS: dict[int, str] = {}


def command[**P](fn: Callable[P, str]) -> Callable[P, str]:
    """Register a command under its function name, processing its arguments."""
    COMMANDS[fn.__name__] = processed = process(fn)
    return processed


@command
def add(
    title: Title,
    *,
    due: Day = None,
    priority: Level = Priority.NORMAL,
    tags: Tags = frozenset(),
) -> str:
    """Add a to-do."""
    number = len(TODOS) + 1
    TODOS[number] = title
    details = [f"priority {priority}", *([f"due {due:%a %d %b}"] if due else []), *sorted(tags)]
    return f"#{number} {title} ({', '.join(details)})"


@command
def done(*ids: Annotated[int, Process(int)]) -> str:
    """Complete one or more to-dos."""
    return f"done: {', '.join(TODOS.pop(number) for number in ids)}"


def run(argv: list[str]) -> str:
    """Dispatch `argv` to a command: plain words are arguments, `--key=value` are options."""
    name, *words = argv
    args = [word for word in words if not word.startswith("--")]
    options = dict(word.removeprefix("--").split("=", 1) for word in words if word.startswith("--"))

    try:
        return COMMANDS[name](*args, **options)
    except ProcessArgumentError as error:
        return f"error: bad value {error.value!r} for '{error.argument}': {error.cause}"
    except TypeError as error:  # a missing or unknown argument
        return f"error: {error}"


def main() -> None:
    print(run(["add", "  buy milk ", "--due=tomorrow", "--priority=HIGH", "--tags=Home,shop"]))
    print(run(["add", "call the bank", "--due=+3"]))
    print(run(["add", "water the plants"]))
    print(run(["done", "1", "3"]))
    print(run(["add", "pay rent", "--due=someday"]))
    print(run(["add", "pay rent", "--priority=urgent"]))
    print(run(["done", "2", "x"]))
    print(run(["add"]))


if __name__ == "__main__":
    main()
