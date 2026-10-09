"""Turn the raw arguments a function receives into the objects it wants.

`pyargprocessors` does one thing: a `Process(fn)` marker, written next to a
parameter inside `Annotated`, applies `fn` to the value passed for it.

```python
>>> from typing import Annotated
>>> from pyargprocessors import Process, process
>>> type Text = Annotated[str, Process(str.strip), Process(str.lower)]
>>> @process
... def order(name: Text, amount: Annotated[int, Process(int)] = 1) -> tuple[str, int]:
...     return name, amount
>>> order("  Tea ", "2")
('tea', 2)

```

Libraries that bind arguments themselves build on `find_processors` and
`process_arguments` instead of the `process` decorator.
"""

from .annotations import annotated_metadata, resolved_annotations
from .combinators import each, optional
from .decorators import process
from .exceptions import InvalidProcessorError, ProcessArgumentError, PyargprocessorsError
from .processors import (
    Process,
    find_processors,
    input_annotation,
    process_arguments,
    process_value,
)

__all__ = [
    "InvalidProcessorError",
    "Process",
    "ProcessArgumentError",
    "PyargprocessorsError",
    "annotated_metadata",
    "each",
    "find_processors",
    "input_annotation",
    "optional",
    "process",
    "process_arguments",
    "process_value",
    "resolved_annotations",
]
