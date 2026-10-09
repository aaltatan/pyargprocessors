"""Validation: clean a whole form and report every bad field at once.

A processor is any function of one value, so it can also *check* the value and
raise. Chained after a converter it sees the converted value:

    type Age = Annotated[int, Process(int), Process(between(13, 120))]

`@process` stops at the first bad argument. A form wants every problem at once,
next to its field, so this example processes the fields one by one with
`process_value` and collects the failures:

    values, errors = clean(SignUp, form)

The field types are declared once, on a `TypedDict`.

Run it with `uv run python -m examples.validation`.
"""

from collections.abc import Callable, Mapping
from inspect import get_annotations
from typing import Annotated, Any, TypedDict

from pyargprocessors import Process, ProcessArgumentError, each, optional, process_value


def required(text: str | None) -> str:
    if text is None or not text.strip():
        msg = "this field is required"
        raise ValueError(msg)
    return text


def blank_to_none(text: str | None) -> str | None:
    """Treat a field left empty, which a form sends as "", as not given."""
    return text if text and text.strip() else None


def email(text: str) -> str:
    name, at, domain = text.partition("@")
    if not (name and at and "." in domain):
        msg = "enter a valid email address"
        raise ValueError(msg)
    return text


def between(low: int, high: int) -> Callable[[int], int]:
    """Return a processor that accepts only numbers in [low, high]."""

    def check(number: int) -> int:
        if not low <= number <= high:
            msg = f"must be between {low} and {high}"
            raise ValueError(msg)
        return number

    return check


def one_of(*choices: str) -> Callable[[str], str]:
    def check(text: str) -> str:
        if text not in choices:
            msg = f"choose one of: {', '.join(choices)}"
            raise ValueError(msg)
        return text

    return check


def checked(value: str | None) -> bool:
    """Read a checkbox: sent as "on" when ticked, and not sent at all otherwise."""
    return value == "on"


type Text = Annotated[str, Process(required), Process(str.strip), Process(str.lower)]
type Email = Annotated[Text, Process(email)]  # the processors of `Text` run first
type Age = Annotated[int, Process(required), Process(int), Process(between(13, 120))]
type Plan = Annotated[Text, Process(one_of("free", "pro"))]
type Topics = Annotated[list[str], Process(each(str.strip)), Process(each(str.lower))]


class SignUp(TypedDict):
    email: Email
    age: Age
    plan: Plan
    referrer: Annotated[str | None, Process(blank_to_none), Process(optional(str.strip))]
    newsletter: Annotated[bool, Process(checked)]
    topics: Topics


def clean(fields: type, form: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Process every field of `form`, returning the clean values and the errors by field."""
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for name, annotation in get_annotations(fields).items():
        try:
            values[name] = process_value(annotation, form.get(name), name=name)
        except ProcessArgumentError as error:
            errors[name] = str(error.cause)

    return values, errors


GOOD_FORM = {
    "email": "  Ada@Example.COM ",
    "age": "36",
    "plan": "PRO",
    "referrer": "   ",
    "newsletter": "on",
    "topics": [" Python", "TYPING "],
}

BAD_FORM = {"email": "ada.example.com", "age": "7", "plan": "gold", "referrer": "", "topics": []}


def main() -> None:
    values, errors = clean(SignUp, GOOD_FORM)
    print(values)
    print(errors)

    values, errors = clean(SignUp, BAD_FORM)
    print(values)
    for field, message in errors.items():
        print(f"{field}: {message}")

    # Nothing sent at all: the required fields say so, the others get their empty value.
    print(clean(SignUp, {"topics": []})[1])


if __name__ == "__main__":
    main()
