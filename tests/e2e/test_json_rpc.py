"""End to end: the text of a JSON-RPC 2.0 request comes in, the text of the response goes out.

The server keeps a table of methods. It knows nothing about their types: it
passes `params` as they were decoded, by position (a list) or by name (a dict).
"""

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pyargprocessors import Process, ProcessArgumentError, optional, process

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    SYP = "SYP"


RATES = {Currency.USD: Decimal(1), Currency.EUR: Decimal("0.92"), Currency.SYP: Decimal(13000)}

# JSON numbers arrive as floats: going through `str` keeps 0.1 from becoming 0.1000000000000000055.
type Money = Annotated[Decimal, Process(str), Process(Decimal)]
type Code = Annotated[Currency, Process(str.strip), Process(str.upper), Process(Currency)]
type Day = Annotated[date | None, Process(optional(date.fromisoformat))]

METHODS: dict[str, Callable[..., Any]] = {}
CALLS: list[str] = []


def method[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    METHODS[fn.__name__] = processed = process(fn)
    return processed


@method
def convert(amount: Money, source: Code, target: Code, *, on: Day = None) -> dict[str, Any]:
    CALLS.append("convert")
    converted = (amount / RATES[source] * RATES[target]).quantize(Decimal("0.01"))
    return {"amount": str(converted), "currency": target, "on": on and on.isoformat()}


@method
def total(*amounts: Money) -> str:
    CALLS.append("total")
    return str(sum(amounts, Decimal(0)))


@method
def ping() -> str:
    return "pong"


def call(request: Any) -> dict[str, Any] | None:
    """Answer one request object, or return `None` for a notification."""
    if not isinstance(request, dict) or "method" not in request:
        return _error(None, INVALID_REQUEST, "Invalid Request")

    request_id, params = request.get("id"), request.get("params", [])
    args, kwargs = ((), params) if isinstance(params, dict) else (params, {})

    try:
        answer = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": METHODS[request["method"]](*args, **kwargs),
        }
    except KeyError:
        answer = _error(request_id, METHOD_NOT_FOUND, "Method not found")
    except ProcessArgumentError as error:
        data = {"param": error.argument, "value": error.value, "reason": str(error.cause)}
        answer = _error(request_id, INVALID_PARAMS, "Invalid params", data)
    except TypeError as error:
        answer = _error(request_id, INVALID_PARAMS, "Invalid params", {"reason": str(error)})

    return answer if "id" in request else None


def serve(text: str) -> str:
    """Answer the text of a request, or of a batch of requests."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps(_error(None, PARSE_ERROR, "Parse error"))

    if isinstance(payload, list):
        return json.dumps([answer for item in payload if (answer := call(item)) is not None])

    answer = call(payload)
    return json.dumps(answer) if answer is not None else ""


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error = {"code": code, "message": message} | ({"data": data} if data else {})
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def rpc(name: str, params: Any = None, request_id: Any = 1) -> dict[str, Any]:
    request = {"jsonrpc": "2.0", "method": name, "id": request_id}
    return json.loads(
        serve(json.dumps(request if params is None else {**request, "params": params}))
    )


class TestResults:
    def test_params_by_position(self) -> None:
        assert rpc("convert", ["100", " usd ", "eur"])["result"] == {
            "amount": "92.00",
            "currency": "EUR",
            "on": None,
        }

    def test_params_by_name(self) -> None:
        params = {"amount": "1", "source": "USD", "target": "syp", "on": "2026-10-09"}

        assert rpc("convert", params)["result"] == {
            "amount": "13000.00",
            "currency": "SYP",
            "on": "2026-10-09",
        }

    def test_null_stays_null(self) -> None:
        params = {"amount": "1", "source": "USD", "target": "USD", "on": None}

        assert rpc("convert", params)["result"]["on"] is None

    def test_json_numbers_and_strings_give_the_same_exact_decimal(self) -> None:
        assert rpc("total", [0.1, 0.2])["result"] == "0.3"
        assert rpc("total", ["0.1", "0.2"])["result"] == "0.3"
        assert rpc("total", [1, "2.50", 3.25])["result"] == "6.75"

    def test_no_params_at_all(self) -> None:
        assert rpc("total")["result"] == "0"
        assert rpc("ping")["result"] == "pong"

    def test_a_method_without_markers_is_registered_untouched(self) -> None:
        assert METHODS["ping"] is ping
        assert METHODS["ping"].__name__ == "ping"

    def test_the_response_carries_the_request_id(self) -> None:
        assert rpc("ping", request_id="abc")["id"] == "abc"


class TestErrors:
    def test_a_processor_failure_says_which_param(self) -> None:
        assert rpc("convert", ["100", "usd", "btc"])["error"] == {
            "code": INVALID_PARAMS,
            "message": "Invalid params",
            "data": {"param": "target", "value": "btc", "reason": "'BTC' is not a valid Currency"},
        }

    def test_the_sent_value_is_echoed_as_it_was_sent(self) -> None:
        data = rpc("convert", [{"cents": 100}, "usd", "eur"])["error"]["data"]

        assert data["param"] == "amount"
        assert data["value"] == {"cents": 100}

    def test_a_failure_inside_var_positional_params(self) -> None:
        data = rpc("total", ["1", "two", "3"])["error"]["data"]

        assert (data["param"], data["value"]) == ("amounts", "two")

    def test_missing_params_fail_before_any_processor_runs(self) -> None:
        CALLS.clear()

        assert rpc("convert", ["100", "btc"])["error"]["data"] == {
            "reason": "missing a required argument: 'target'",
        }
        assert CALLS == []

    def test_unknown_named_params(self) -> None:
        params = {"amount": "1", "source": "usd", "target": "eur", "rate": 2}

        assert rpc("convert", params)["error"]["data"] == {
            "reason": "got an unexpected keyword argument 'rate'",
        }

    def test_a_keyword_only_param_cannot_be_sent_by_position(self) -> None:
        reason = rpc("convert", ["1", "usd", "eur", "2026-10-09"])["error"]["data"]["reason"]

        assert reason == "too many positional arguments"

    def test_unknown_method(self) -> None:
        assert rpc("refund")["error"] == {"code": METHOD_NOT_FOUND, "message": "Method not found"}

    def test_text_that_is_not_json(self) -> None:
        assert json.loads(serve("{not json"))["error"]["code"] == PARSE_ERROR

    def test_json_that_is_not_a_request(self) -> None:
        assert json.loads(serve('"convert"'))["error"]["code"] == INVALID_REQUEST


class TestBatchesAndNotifications:
    def test_a_notification_runs_and_answers_nothing(self) -> None:
        CALLS.clear()

        assert serve(json.dumps({"jsonrpc": "2.0", "method": "total", "params": ["1"]})) == ""
        assert CALLS == ["total"]

    def test_a_bad_notification_is_silent_and_does_not_run(self) -> None:
        CALLS.clear()

        assert serve(json.dumps({"jsonrpc": "2.0", "method": "total", "params": ["x"]})) == ""
        assert CALLS == []

    def test_a_batch_answers_each_call_on_its_own(self) -> None:
        batch = [
            {"jsonrpc": "2.0", "method": "total", "params": ["1", "2"], "id": 1},
            {"jsonrpc": "2.0", "method": "total", "params": ["1", "x"], "id": 2},
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "2.0", "method": "nope", "id": 3},
            42,
        ]
        answers = json.loads(serve(json.dumps(batch)))

        assert [answer["id"] for answer in answers] == [1, 2, 3, None]
        assert answers[0]["result"] == "3"
        assert [answer["error"]["code"] for answer in answers[1:]] == [
            INVALID_PARAMS,
            METHOD_NOT_FOUND,
            INVALID_REQUEST,
        ]

    def test_an_empty_batch(self) -> None:
        assert serve("[]") == "[]"
