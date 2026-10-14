"""Edge cases of `from __future__ import annotations`, where every annotation is a string."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from pyargprocessors import Process, find_processors, process, resolved_annotations
from pyargprocessors import dataclass as processed_dataclass

if TYPE_CHECKING:
    from decimal import Decimal

type Text = Annotated[str, Process(str.strip), Process(str.lower)]
Num = Annotated[int, Process(int)]


@process
def order(name: Text, amount: Num = 1) -> tuple[str, int]:
    return name, amount


@process
def pay(name: Text, price: Decimal, amount: Num = 1) -> tuple[str, Any, int]:
    return name, price, amount


@dataclass
class Line:
    name: Text
    amount: Num = 1


@processed_dataclass
class ProcessedLine:
    name: Text
    amount: Num = 1


class TestStringAnnotations:
    def test_module_level_names_are_resolved(self) -> None:
        assert order.__annotations__["name"] == "Text"
        assert order(" Tea ", "2") == ("tea", 2)

    def test_a_name_only_imported_for_type_checkers_does_not_hide_the_markers(self) -> None:
        assert resolved_annotations(pay)["price"] == "Decimal"
        assert pay(" Tea ", "2.5", "2") == ("tea", "2.5", 2)

    def test_dataclass_fields(self) -> None:
        assert process(Line)(" Tea ", "2") == Line("tea", 2)

    def test_processed_dataclass_fields(self) -> None:
        assert ProcessedLine(" Tea ", "2") == ProcessedLine("tea", 2)

    def test_methods_and_string_return_types(self) -> None:
        class Shop:
            @process
            def order(self, name: Text) -> Shop:
                self.name = name
                return self

        assert Shop().order(" Tea ").name == "tea"

    def test_an_alias_defined_inside_a_function_cannot_be_found(self) -> None:
        type Local = Annotated[str, Process(str.upper)]

        def fn(name: Local, amount: Num) -> tuple[str, int]:
            return name, amount

        assert set(find_processors(fn)) == {"amount"}
        assert process(fn)("tea", "2") == ("tea", 2)

    def test_the_marker_itself_written_inline_is_found(self) -> None:
        def fn(name: Annotated[str, Process(str.upper)]) -> str:
            return name

        assert process(fn)("tea") == "TEA"
