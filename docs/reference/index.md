# Reference

- [API](api.md): every public name of `pyargprocessors`.
- [Exceptions](exceptions.md): the exception hierarchy and when each one is raised.
- [Behaviour corners](behaviour.md): situations decided on purpose, each pinned by a test.

Everything is importable from the package root:

```py
from pyargprocessors import (
    InvalidProcessorError,
    Process,
    ProcessArgumentError,
    PyargprocessorsError,
    annotated_metadata,
    dataclass,
    each,
    find_processors,
    input_annotation,
    optional,
    process,
    process_arguments,
    process_value,
    resolved_annotations,
)
```
