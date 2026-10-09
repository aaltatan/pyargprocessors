from decimal import Decimal
from typing import Annotated, Any

import pytest

from pyargprocessors import Process, ProcessArgumentError, each, optional, process


class TestEach:
    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            (["1", "2"], [1, 2]),
            (("1", "2"), (1, 2)),
            ({"1", "2"}, {1, 2}),
            (frozenset({"1"}), frozenset({1})),
            ([], []),
        ],
    )
    def test_keeps_the_collection_type(self, values: Any, expected: Any) -> None:
        result = each(int)(values)

        assert result == expected
        assert type(result) is type(expected)

    def test_dict_values(self) -> None:
        assert each(int)({"a": "1", "b": "2"}) == {"a": 1, "b": 2}

    @pytest.mark.parametrize("value", ["12", b"12", 12, None])
    def test_rejects_anything_else(self, value: Any) -> None:
        with pytest.raises(TypeError, match="expected a list, tuple, set or dict"):
            each(int)(value)

    def test_inside_a_marker(self) -> None:
        @process
        def total(prices: Annotated[list[Decimal], Process(each(Decimal))]) -> Decimal:
            return sum(prices, Decimal(0))

        assert total(["1.50", "2.25"]) == Decimal("3.75")

    def test_failure_reports_the_whole_value(self) -> None:
        @process
        def total(prices: Annotated[list[int], Process(each(int))]) -> int:
            return sum(prices)

        with pytest.raises(ProcessArgumentError, match=r"'prices' with value \['1', 'x'\]"):
            total(["1", "x"])


class TestOptional:
    def test_none_is_kept(self) -> None:
        assert optional(int)(None) is None

    def test_other_values_are_processed(self) -> None:
        assert optional(int)("2") == 2
        assert optional(str.strip)("") == ""

    def test_inside_a_marker(self) -> None:
        @process
        def limit(value: Annotated[int | None, Process(optional(int))] = None) -> int | None:
            return value

        assert limit("5") == 5
        assert limit(None) is None

    def test_combines_with_each(self) -> None:
        processor = optional(each(optional(int)))

        assert processor(None) is None
        assert processor(["1", None]) == [1, None]
