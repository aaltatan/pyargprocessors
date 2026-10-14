import asyncio
import dataclasses
from datetime import date
from decimal import Decimal
from enum import StrEnum
from inspect import iscoroutinefunction, signature
from typing import Annotated, Any

import pytest

from pyargprocessors import InvalidProcessorError, Process, ProcessArgumentError, dataclass, process


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


class TestDataclass:
    def test_the_class_processes_its_own_fields(self) -> None:
        @dataclass
        class Line:
            name: Text
            amount: Annotated[int, Process(int)] = 1

        assert Line(" Tea ", "2") == Line("tea", 2)
        assert Line(name=" Tea ", amount="2").amount == 2
        assert Line(" Tea ").amount == 1
        assert isinstance(Line, type)
        assert dataclasses.is_dataclass(Line)

    def test_options_are_passed_to_dataclasses(self) -> None:
        @dataclass(frozen=True, slots=True, kw_only=True)
        class Settings:
            port: Annotated[int, Process(int)] = 8000

        settings = Settings(port="8080")

        assert settings.port == 8080
        assert "__slots__" in vars(Settings)
        with pytest.raises(dataclasses.FrozenInstanceError):
            settings.port = 1  # type: ignore[misc]
        with pytest.raises(TypeError):
            Settings("8080")  # type: ignore[misc]

    def test_post_init_sees_processed_values(self) -> None:
        @dataclass
        class Order:
            amount: Annotated[int, Process(int)]
            doubled: int = dataclasses.field(init=False)

            def __post_init__(self) -> None:
                self.doubled = self.amount * 2

        assert Order("3").doubled == 6

    def test_subclasses_process_inherited_fields(self) -> None:
        @dataclass
        class Base:
            name: Text

        @dataclass
        class Child(Base):
            amount: Annotated[int, Process(int)] = 1

        assert Child(" Tea ", "2") == Child("tea", 2)
        assert isinstance(Child("tea"), Base)

    def test_without_an_own_init_nothing_changes(self) -> None:
        @dataclass(init=False)
        class Empty:
            amount: Annotated[int, Process(int)] = 0

        assert Empty.__init__ is object.__init__

    def test_keeps_its_signature(self) -> None:
        @dataclass
        class Line:
            name: Text
            amount: Annotated[int, Process(int)] = 1

        assert list(signature(Line).parameters) == ["name", "amount"]

    def test_failure_names_the_field_and_value(self) -> None:
        @dataclass
        class Line:
            amount: Annotated[int, Process(int)]

        with pytest.raises(ProcessArgumentError, match="Argument 'amount' with value 'two'"):
            Line("two")

    def test_marker_as_default_value_names_the_class(self) -> None:
        with pytest.raises(InvalidProcessorError, match="'Bad' uses Process as the default"):

            @dataclass
            class Bad:
                amount: int = Process(int)  # type: ignore[assignment]

    def test_has_the_signature_of_dataclasses_dataclass(self) -> None:
        def described(fn: Any) -> list[tuple[str, Any, Any]]:
            return [(p.name, p.kind, p.default) for p in signature(fn).parameters.values()]

        assert described(dataclass) == described(dataclasses.dataclass)

    def test_an_unknown_option_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="unexpected keyword argument 'frozn'"):
            dataclass(frozn=True)  # type: ignore[call-overload]
