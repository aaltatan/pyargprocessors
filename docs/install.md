# Installation

pyargprocessors needs **Python 3.12 or newer** (it uses `type` aliases) and has no
dependencies.

=== "pip"

    ```bash
    pip install pyargprocessors
    ```

=== "uv"

    ```bash
    uv add pyargprocessors
    ```

Check it:

```python
from typing import Annotated

from pyargprocessors import Process, process_value

assert process_value(Annotated[int, Process(int)], "42") == 42
```

Everything is importable from the package root:

```python
import pyargprocessors

assert sorted(pyargprocessors.__all__) == [
    "InvalidProcessorError",
    "Process",
    "ProcessArgumentError",
    "PyargprocessorsError",
    "annotated_metadata",
    "dataclass",
    "each",
    "find_processors",
    "input_annotation",
    "optional",
    "process",
    "process_arguments",
    "process_value",
    "resolved_annotations",
]
```

## Development

```bash
uv sync
uv run pytest --cov --cov-report term-missing
```

The test suite also runs every docstring example (`--doctest-modules`) and checks the exact
output of every script in `examples/`.
