# Recipes

Each recipe is a runnable script in
[`examples/`](https://github.com/aaltatan/pyargprocessors/tree/main/examples); the snippets
below are the parts that matter, and the outputs are what the scripts print. The test suite
checks that output exactly.

| You receive | You want | Recipe |
| --- | --- | --- |
| A web form: every field is a string | Typed arguments of a search function | [Search form](#a-search-form) |
| A web form, and you must show **every** error | Clean values and one message per field | [Validate a whole form](#validate-a-whole-form) |
| Environment variables | A frozen, typed settings object | [Settings](#settings-from-the-environment) |
| `argv` words | Commands that are plain typed functions | [Command line](#a-command-line) |
| A decoded JSON body, with nested objects | An `async` handler with `UUID`, `datetime`, dataclasses | [JSON API](#a-json-api-handler) |
| Webhook JSON with a `type` and nested objects | Real dataclass events to `match` on | [Webhook events](#webhook-events) |
| Functions your users register in your library | Their arguments processed by your own binding | [Rules library](#a-rules-library) |

## A search form

`examples/form.py`: a shop's search form sends raw strings (`"20"`, `"yes"`, `" SONIC "`, a
file path, an empty field) and the function receives typed, clean arguments.

```py
def to_bool(text: str) -> bool:
    return text.strip().lower() in {"yes", "true", "on", "1"}


def load_names(path: str) -> frozenset[str]:
    return frozenset(line.strip().lower() for line in FILES[path].splitlines())


type Money = Annotated[Decimal, Process(Decimal)]
type MaybeMoney = Annotated[Decimal | None, Process(optional(Decimal))]
type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Names = Annotated[frozenset[str], Process(load_names)]


@process
def search(
    text: Text,
    *,
    low: Money = Decimal(0),
    high: MaybeMoney = None,
    in_stock: Annotated[bool, Process(to_bool)] = False,
    exclude: Names = frozenset(),
    limit: Annotated[int, Process(int)] = 3,
    **fields: Text,
) -> list[Product]: ...


@process
def brands(names: Annotated[list[str], Process(each(str.lower))]) -> list[str]: ...


FORM = {
    "text": "  HeadPhones ",
    "low": "20",
    "high": None,
    "in_stock": "yes",
    "exclude": "discontinued.txt",
    "limit": "2",
    "brand": " SONIC ",
}

search(**FORM)
search(" LAMP ")                       # defaults are not processed: only `text` is
brands(["SONIC", "Acme", "Boom"])      # `each` processes every item
process_value(Money, "19.90")          # a processed type without a function
search("headphones", limit="two")      # fails before the function runs
```

```bash
uv run python -m examples.form
```

```text
Pro Headphones (Sonic) $349.00 4.9*
Studio Headphones (Sonic) $149.00 4.7*
['Desk Lamp']
['sonic', 'boom']
Decimal('19.90')
ProcessArgumentError on 'limit': Argument 'limit' with value 'two' failed to process, invalid literal for int() with base 10: 'two'
```

## Validate a whole form

`examples/validation.py`: processors that check (`required`, `between(13, 120)`,
`one_of("free", "pro")`), and a `clean(SignUp, form)` that processes a `TypedDict` field by
field and returns **every** error at once.

```py
def checked(value: str | None) -> bool:
    """A checkbox is sent as "on" when ticked, and not sent at all otherwise."""
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
```

```bash
uv run python -m examples.validation
```

```text
{'email': 'ada@example.com', 'age': 36, 'plan': 'pro', 'referrer': None, 'newsletter': True, 'topics': ['python', 'typing']}
{}
{'referrer': None, 'newsletter': False, 'topics': []}
email: enter a valid email address
age: must be between 13 and 120
plan: choose one of: free, pro
{'email': 'this field is required', 'age': 'this field is required', 'plan': 'this field is required'}
```

## Settings from the environment

`examples/settings.py`: environment variables become a frozen dataclass through
`process(Settings)`: a validated port, a flag, an enum, a tuple of hosts, a `timedelta`, a
`Path`. A bad variable stops the start-up with its name.

```py
def valid_port(port: int) -> int:
    if not 0 < port < 65536:
        msg = f"a port is between 1 and 65535, got {port}"
        raise ValueError(msg)
    return port


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
    values = {
        name.removeprefix(prefix).lower(): value
        for name, value in environ.items()
        if name.startswith(prefix)
    }
    return make_settings(**values)
```

```bash
uv run python -m examples.settings
```

```text
postgres://db.internal/shop
8080 True WARNING
('a.example.com', 'b.example.com')
0:00:02.500000 data
8000
APP_PORT: a port is between 1 and 65535, got 99999
```

## A command line

`examples/cli.py`: a to-do tool. The dispatcher hands raw words to commands that are plain
typed functions; `--due=tomorrow`, `--priority=HIGH` and `--tags=Home,shop` become a `date`,
an enum and a set.

```py
type Title = Annotated[str, Process(str.strip), Process(str.capitalize)]
type Day = Annotated[date | None, Process(parse_day)]
type Level = Annotated[Priority, Process(str.lower), Process(Priority)]
type Tags = Annotated[frozenset[str], Process(split_commas), Process(each(str.lower))]


def command[**P](fn: Callable[P, str]) -> Callable[P, str]:
    COMMANDS[fn.__name__] = processed = process(fn)
    return processed


@command
def add(title: Title, *, due: Day = None, priority: Level = Priority.NORMAL, tags: Tags = frozenset()) -> str: ...


@command
def done(*ids: Annotated[int, Process(int)]) -> str: ...


def run(argv: list[str]) -> str:
    name, *words = argv
    args = [word for word in words if not word.startswith("--")]
    options = dict(word.removeprefix("--").split("=", 1) for word in words if word.startswith("--"))

    try:
        return COMMANDS[name](*args, **options)
    except ProcessArgumentError as error:
        return f"error: bad value {error.value!r} for '{error.argument}': {error.cause}"
    except TypeError as error:  # a missing or unknown argument
        return f"error: {error}"
```

```bash
uv run python -m examples.cli
```

```text
#1 Buy milk (priority high, due Sat 10 Oct, home, shop)
#2 Call the bank (priority normal, due Mon 12 Oct)
#3 Water the plants (priority normal)
done: Buy milk, Water the plants
error: bad value 'someday' for 'due': Invalid isoformat string: 'someday'
error: bad value 'urgent' for 'priority': 'urgent' is not a valid Priority
error: bad value 'x' for 'ids': invalid literal for int() with base 10: 'x'
error: missing a required argument: 'title'
```

## A JSON API handler

`examples/api.py`: an `async` handler receives a decoded JSON body with a list of nested
objects. A bad value deep inside is answered with its path, `{"field": "lines.quantity", ...}`.

```py
@dataclass(frozen=True, slots=True)
class Line:
    sku: Annotated[str, Process(str.upper)]
    quantity: Annotated[int, Process(int)]
    price: Annotated[Decimal, Process(Decimal)]


make_line = process(Line)


def to_line(data: dict[str, Any]) -> Line:
    return make_line(**data)


type Lines = Annotated[list[Line], Process(each(to_line))]
type Coupon = Annotated[str | None, Process(optional(str.upper))]


@process
async def create_order(
    order_id: Annotated[UUID, Process(UUID)],
    placed_at: Annotated[datetime, Process(datetime.fromisoformat)],
    lines: Lines,
    ship_to: Annotated[Address, Process(to_address)],
    coupon: Coupon = None,
) -> dict[str, Any]: ...


def error_path(error: ProcessArgumentError) -> str:
    cause = error.cause
    return f"{error.argument}.{error_path(cause)}" if _is_nested(cause) else error.argument


async def handle(body: str) -> tuple[int, dict[str, Any]]:
    try:
        return 201, await create_order(**json.loads(body))
    except ProcessArgumentError as error:  # before `TypeError`, which it also is
        return 422, {"field": error_path(error), "error": str(root_cause(error))}
    except TypeError as error:  # a missing or unknown key
        return 400, {"error": str(error)}
```

```bash
uv run python -m examples.api
```

```text
201 {'id': '8f14e45f-ceea-467f-a9d1-5c2f1c1f2a10', 'placed': '2026-10-09 14:30', 'items': ['2 x TEA-01', '1 x MUG-07'], 'city': 'Damascus', 'coupon': None, 'total': '21.00'}
('id', '8f14e45f-ceea-467f-a9d1-5c2f1c1f2a10') ('placed', '2026-10-09 14:30') ('items', ['2 x TEA-01', '1 x MUG-07']) ('city', 'Damascus') ('coupon', 'AUTUMN') ('total', '21.00')
422 {'field': 'order_id', 'error': 'badly formed hexadecimal UUID string'}
422 {'field': 'lines.quantity', 'error': "invalid literal for int() with base 10: 'two'"}
422 {'field': 'lines', 'error': "expected a list, tuple, set or dict, got 'tea-01'"}
400 {'error': "got an unexpected keyword argument 'gift'"}
```

## Webhook events

`examples/events.py`: a carrier's webhook JSON becomes typed tracking events with
[`@dataclass`](guide/classes.md#dataclass-the-class-processes-its-own-fields). The classes
process their own fields, nested ones included, then `__post_init__` checks across fields,
`match` picks the event, and `dataclasses.replace` still works.

```py
def nested[T](cls: type[T]) -> Callable[[Any], T]:
    def build(value: Any) -> T:
        return value if isinstance(value, cls) else cls(**value)

    return build


# The processors accept what they produce, because `replace()` processes every field again.
type Id = Annotated[UUID, Process(to_uuid)]
type Moment = Annotated[datetime, Process(to_datetime)]
type Kilos = Annotated[Decimal, Process(str), Process(Decimal)]  # str first: no float error


@dataclass(frozen=True, kw_only=True)
class Event:
    event_id: Id
    at: Moment


@dataclass(frozen=True, kw_only=True)
class Shipped(Event):
    to: Annotated[Address, Process(nested(Address))]
    parcels: Annotated[tuple[Parcel, ...], Process(each(nested(Parcel))), Process(tuple)]
    promised: Moment
    service: Annotated[Service, Process(str.lower), Process(Service)] = Service.STANDARD

    def __post_init__(self) -> None:
        if self.promised < self.at:
            msg = f"promised for {self.promised:%d %b}, before it was shipped"
            raise ValueError(msg)


@dataclass(frozen=True, kw_only=True)
class Delivered(Event):
    signed_by: Annotated[str | None, Process(optional(str.strip))] = None


EVENTS: dict[str, type[Event]] = {"shipped": Shipped, "delivered": Delivered}


def parse(payload: Mapping[str, Any]) -> Event:
    fields = {name: value for name, value in payload.items() if name != "type"}
    return EVENTS[payload["type"]](**fields)
```

```bash
uv run python -m examples.events
```

```text
express to Damascus: 2 parcels, 1.55 kg
delivered, signed by Ada Lovelace
delivered, left at the door
Shipped True
Address(name='Ada Lovelace', city='Damascus', postcode='DM 101')
Parcel(reference='A-1', weight=Decimal('1.2'))
2026-10-14 True
parcels.weight: 'heavy' failed (InvalidOperation)
ValueError: promised for 11 Oct, before it was shipped
```

## A rules library

`examples/rules.py`: [building on top](guide/building-on-top.md). A tiny rules library turns
`(object, *arguments) -> bool` functions into rules that are built first and tested later,
from Python or from JSON, with `find_processors(skip=1)`, `process_arguments` and
`input_annotation`.

```py
def rule[T](fn: Callable[..., bool]) -> Callable[..., Predicate[T]]:
    name = fn.__name__
    processors = find_processors(fn, name=f"rule {name}", skip=1)
    arguments = Signature(list(signature(fn).parameters.values())[1:])

    def factory(*args: Any, **kwargs: Any) -> Predicate[T]:
        bound = process_arguments(processors, arguments.bind(*args, **kwargs))
        return lambda obj: fn(obj, *bound.args, **bound.kwargs)

    RULES[name] = factory
    SENDS[name] = {  # what the JSON must send, from `input_annotation`
        parameter: _sent_type(fn, parameter, processors.get(parameter, ()))
        for parameter in arguments.parameters
    }
    return factory


def compile_rules[T](definition: list[dict[str, Any]]) -> Predicate[T]:
    predicates = [RULES[item["rule"]](*item.get("args", [])) for item in definition]
    return lambda obj: all(predicate(obj) for predicate in predicates)


@rule
def age__gte(user: User, years: Annotated[int, Process(int)], on: date = date(2026, 10, 9)) -> bool: ...


@rule
def country__in(user: User, *countries: Text) -> bool: ...


@rule
def name__not_in(user: User, names: Names) -> bool: ...


DEFINITION = [
    {"rule": "age__gte", "args": ["18"]},
    {"rule": "country__in", "args": [" uk ", "IE"]},
    {"rule": "name__not_in", "args": ["lists/blocked.txt"]},
]
```

```bash
uv run python -m examples.rules
```

```text
['Ada']
['lists/blocked.txt']
{'age__gte': {'years': 'int', 'on': 'date'}, 'country__in': {'countries': 'str'}, 'name__not_in': {'names': 'str'}}
ProcessArgumentError: Argument 'years' with value 'eighteen' failed to process, invalid literal for int() with base 10: 'eighteen'
InvalidProcessorError: 'rule bad' cannot process 'user': it is not passed as an argument
```

The file of blocked names is read **once**, when the rule is built, not once per user.

## More end-to-end scenarios

The test suite has three more, raw text in and answer out, in `tests/e2e/`: a query string
(`parse_qs` gives lists), the lines of a CSV file, and a JSON-RPC server whose methods know
their own types.
