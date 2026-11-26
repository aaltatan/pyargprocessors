# Validation

## A processor that raises is a validator

A processor that raises rejects the value. Chained after a converter, it sees the converted
value:

```python
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, process_value


def between(low: int, high: int):
    def check(number: int) -> int:
        if not low <= number <= high:
            raise ValueError(f"must be between {low} and {high}")
        return number

    return check


type Age = Annotated[int, Process(int), Process(between(13, 120))]

assert process_value(Age, "36") == 36

try:
    process_value(Age, "7")
except ProcessArgumentError as error:
    assert str(error) == "Argument 'value' with value '7' failed to process, must be between 13 and 120"
```

A validator must **return** the value: a processor that returns nothing (like `list.sort`)
turns the argument into `None`. The result is never checked against the type hint.

## Every error at once

`@process` stops at the **first** bad argument, in the order of the signature. A form wants
every problem at once, next to its field. Declare the field types once, on a `TypedDict`, and
process them one by one with `process_value`:

```python
from collections.abc import Mapping
from inspect import get_annotations
from typing import Annotated, Any, TypedDict

from pyargprocessors import Process, ProcessArgumentError, process_value


def required(text: str | None) -> str:
    if text is None or not text.strip():
        raise ValueError("this field is required")
    return text


def email(text: str) -> str:
    name, at, domain = text.partition("@")
    if not (name and at and "." in domain):
        raise ValueError("enter a valid email address")
    return text


type Text = Annotated[str, Process(required), Process(str.strip), Process(str.lower)]
type Email = Annotated[Text, Process(email)]  # the processors of `Text` run first


class SignUp(TypedDict):
    email: Email
    name: Text


def clean(fields: type, form: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for name, annotation in get_annotations(fields).items():
        try:
            values[name] = process_value(annotation, form.get(name), name=name)
        except ProcessArgumentError as error:
            errors[name] = str(error.cause)

    return values, errors


assert clean(SignUp, {"email": " Ada@Example.COM ", "name": "Ada"}) == (
    {"email": "ada@example.com", "name": "ada"},
    {},
)
assert clean(SignUp, {"email": "ada.example.com"}) == (
    {},
    {"email": "enter a valid email address", "name": "this field is required"},
)
```

The full version, with ages, plans, checkboxes and lists, is the
[validation recipe](../recipes.md#validate-a-whole-form).
