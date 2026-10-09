"""Exceptions raised by pyargprocessors.

Every exception derives from `PyargprocessorsError`, so callers can catch the
whole family at once. They additionally derive from `TypeError`, to stay
compatible with code that expects the built-in exception type for a bad
argument.
"""

from typing import Any


class PyargprocessorsError(Exception):
    """Base class for every exception raised by pyargprocessors."""


class InvalidProcessorError(PyargprocessorsError, TypeError):
    """Raised when a `Process(...)` marker cannot work.

    For example a processor that is not callable, a marker used as a default
    value instead of inside `Annotated`, or a marker on a parameter whose value
    is not passed as an argument.
    """


class ProcessArgumentError(PyargprocessorsError, TypeError):
    """Raised when a `Process` function fails on the value given for an argument.

    `argument` is the name of the argument, `value` the value as it was passed,
    before any processor ran, and `cause` the exception the processor raised,
    which is also chained as `__cause__`.

    Example:
    ```python
    >>> error = ProcessArgumentError("limit", "two", ValueError("not a number"))
    >>> str(error)
    "Argument 'limit' with value 'two' failed to process, not a number"
    >>> error.argument, error.value, error.cause
    ('limit', 'two', ValueError('not a number'))

    ```

    """

    def __init__(self, argument: str, value: Any, cause: Exception) -> None:
        # the three values are the exception's `args`, so it can be copied and pickled
        super().__init__(argument, value, cause)
        self.argument = argument
        self.value = value
        self.cause = cause

    def __str__(self) -> str:
        reason = str(self.cause) or type(self.cause).__name__
        return f"Argument '{self.argument}' with value {self.value!r} failed to process, {reason}"
