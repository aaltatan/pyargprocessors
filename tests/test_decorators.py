import asyncio
from datetime import date
from decimal import Decimal
from enum import StrEnum
from inspect import iscoroutinefunction, signature
from typing import Annotated, Any

import pytest

from pyargprocessors import InvalidProcessorError, Process, ProcessArgumentError, process


class Milk(StrEnum):
    OAT = "oat"
    SOY = "soy"


def normalize(text: str) -> str:
    return text.strip().lower()


type Text = Annotated[str, Process(normalize)]


@process
def order(name: Text, amount: Annotated[int, Process(int)] = 1) -> tuple[str, int]:
    """Order a drink."""
    return name, amount


class TestProcessingArguments:
    def test_positional_and_keyword(self) -> None:
        assert order(" Tea ", "2") == ("tea", 2)
        assert order(name=" Tea ", amount="2") == ("tea", 2)

    def test_defaults_are_not_processed(self) -> None:
        @process
        def pour(ml: Annotated[int, Process(int)] = "a lot") -> Any:  # type: ignore[assignment]
            return ml

        assert pour() == "a lot"

    def test_var_positional_and_var_keyword(self) -> None:
        @process
        def where(*names: Text, strict: Annotated[bool, Process(bool)] = False, **fields: Text):
            return names, strict, fields

        assert where(" A ", "B", strict=1, brand=" SONIC ") == (
            ("a", "b"),
            True,
            {"brand": "sonic"},
        )

    @pytest.mark.parametrize(
        ("processor", "raw", "expected"),
        [
            (Decimal, "2.50", Decimal("2.50")),
            (date.fromisoformat, "2026-10-09", date(2026, 10, 9)),
            (Milk, "oat", Milk.OAT),
            (lambda value: value * 2, 21, 42),
        ],
    )
    def test_any_callable_can_process(self, processor: Any, raw: Any, expected: Any) -> None:
        @process
        def keep(value: Annotated[Any, Process(processor)]) -> Any:
            return value

        assert keep(raw) == expected

    def test_every_call_is_processed(self) -> None:
        calls: list[str] = []

        def load(path: str) -> str:
            calls.append(path)
            return path.upper()

        @process
        def use(data: Annotated[str, Process(load)]) -> str:
            return data

        assert [use("a.csv"), use("b.csv")] == ["A.CSV", "B.CSV"]
        assert calls == ["a.csv", "b.csv"]

    def test_methods(self) -> None:
        class Shop:
            @process
            def order(self, name: Text) -> tuple[Any, str]:
                return self, name

        shop = Shop()
        assert shop.order(" Tea ") == (shop, "tea")

    def test_async_functions_stay_async(self) -> None:
        @process
        async def fetch(name: Text) -> str:
            return name

        assert iscoroutinefunction(fetch)
        assert asyncio.run(fetch(" Tea ")) == "tea"


class TestTheDecoratedFunction:
    def test_keeps_its_name_doc_and_signature(self) -> None:
        assert order.__name__ == "order"
        assert order.__doc__ == "Order a drink."
        assert list(signature(order).parameters) == ["name", "amount"]

    def test_without_markers_it_is_returned_as_it_is(self) -> None:
        def plain(name: str) -> str:
            return name

        assert process(plain) is plain


class TestFailures:
    def test_failure_names_the_argument_and_value(self) -> None:
        with pytest.raises(
            ProcessArgumentError, match="Argument 'amount' with value 'two' failed to process"
        ) as info:
            order("tea", "two")

        assert isinstance(info.value.__cause__, ValueError)
        assert (info.value.argument, info.value.value) == ("amount", "two")

    def test_bad_arguments_fail_before_processing(self) -> None:
        calls: list[Any] = []

        @process
        def use(data: Annotated[str, Process(calls.append)], other: str) -> None: ...

        with pytest.raises(TypeError, match="missing a required argument: 'other'"):
            use("x")
        assert calls == []

    def test_the_function_does_not_run_when_processing_fails(self) -> None:
        ran: list[int] = []

        @process
        def use(amount: Annotated[int, Process(int)]) -> None:
            ran.append(amount)

        with pytest.raises(ProcessArgumentError):
            use("x")
        assert ran == []

    def test_marker_as_default_value(self) -> None:
        def bad(amount: int = Process(int)) -> int:  # type: ignore[assignment]
            return amount

        with pytest.raises(InvalidProcessorError, match="uses Process as the default of 'amount'"):
            process(bad)
