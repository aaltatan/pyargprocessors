"""Settings: turn environment variables into a typed, frozen settings object.

Everything in the environment is a string ("8080", "true", "a.example.com,
b.example.com"), while the application wants a port number, a flag, a tuple of
hosts, a `timedelta` and a `Path`. The fields of a dataclass carry the markers,
and `process(Settings)` gives a factory that processes what it is given:

    make_settings = process(Settings)
    make_settings(database_url=" postgres://db ", port="8080")

Decorating a class returns a factory function, not a class, so keep the class
under its own name and give the factory another one.

Run it with `uv run python -m examples.settings`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pyargprocessors import Process, ProcessArgumentError, each, process


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"


def to_bool(text: str) -> bool:
    """Read flag-like values: yes/no, true/false, on/off, 1/0."""
    return text.strip().lower() in {"yes", "true", "on", "1"}


def split_commas(text: str) -> tuple[str, ...]:
    """Split "a, b,,c" into its non-empty parts."""
    return tuple(part for part in text.split(",") if part.strip())


def valid_port(port: int) -> int:
    """Processors validate too: reject what cannot be a TCP port."""
    if not 0 < port < 65536:  # noqa: PLR2004
        msg = f"a port is between 1 and 65535, got {port}"
        raise ValueError(msg)
    return port


def seconds(amount: float) -> timedelta:
    return timedelta(seconds=amount)


type Hosts = Annotated[tuple[str, ...], Process(split_commas), Process(each(str.strip))]
type Seconds = Annotated[timedelta, Process(float), Process(seconds)]


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: Annotated[str, Process(str.strip)]
    port: Annotated[int, Process(int), Process(valid_port)] = 8000
    debug: Annotated[bool, Process(to_bool)] = False
    log_level: Annotated[LogLevel, Process(str.upper), Process(LogLevel)] = LogLevel.INFO
    allowed_hosts: Hosts = ("localhost",)
    timeout: Seconds = timedelta(seconds=30)
    data_dir: Annotated[Path, Process(Path)] = Path("data")


make_settings = process(Settings)


def load_settings(environ: Mapping[str, str], prefix: str = "APP_") -> Settings:
    """Build the settings from every variable starting with `prefix`."""
    values = {
        name.removeprefix(prefix).lower(): value
        for name, value in environ.items()
        if name.startswith(prefix)
    }
    return make_settings(**values)


# Stands in for `os.environ`, to keep the example self-contained.
ENVIRON = {
    "PATH": "/usr/bin",
    "APP_DATABASE_URL": " postgres://db.internal/shop ",
    "APP_PORT": "8080",
    "APP_DEBUG": "true",
    "APP_LOG_LEVEL": "warning",
    "APP_ALLOWED_HOSTS": "a.example.com, b.example.com,",
    "APP_TIMEOUT": "2.5",
}


def main() -> None:
    settings = load_settings(ENVIRON)
    print(settings.database_url)
    print(settings.port, settings.debug, settings.log_level)
    print(settings.allowed_hosts)
    print(settings.timeout, settings.data_dir.as_posix())  # `data_dir` kept its default

    # Variables that are not set keep their defaults, which are not processed.
    print(load_settings({"APP_DATABASE_URL": "sqlite://"}).port)

    # A bad variable stops the application at start-up, with its name.
    try:
        load_settings({**ENVIRON, "APP_PORT": "99999"})
    except ProcessArgumentError as error:
        print(f"APP_{error.argument.upper()}: {error.cause}")


if __name__ == "__main__":
    main()
