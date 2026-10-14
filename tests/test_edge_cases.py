# ruff: noqa: RUF001
"""Edge cases: unusual signatures, values, processors, annotations and callables.

Each test pins down what happens in a corner, so that the answer is a decision
and not an accident.
"""

import asyncio
import copy
import dataclasses
import pickle
from collections import OrderedDict, defaultdict, deque, namedtuple
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache, partial, wraps
from inspect import signature
from math import isnan
from typing import Annotated, Any, Final, NamedTuple, Optional, Self
from uuid import UUID

import pytest

from pyargprocessors import (
    InvalidProcessorError,
    Process,
    ProcessArgumentError,
    PyargprocessorsError,
    annotated_metadata,
    each,
    find_processors,
    optional,
    process,
    process_arguments,
    process_value,
)
from pyargprocessors import dataclass as processed_dataclass

type Num = Annotated[int, Process(int)]
type Text = Annotated[str, Process(str.strip), Process(str.lower)]
type Upper = Annotated[str, Process(str.upper)]


class TestUnusualSignatures:
    def test_positional_only_and_keyword_only(self) -> None:
        @process
        def fn(a: Num, /, b: Num, *, c: Num) -> tuple[int, int, int]:
            return a, b, c

        assert fn("1", "2", c="3") == (1, 2, 3)
        assert fn("1", b="2", c="3") == (1, 2, 3)

    def test_a_positional_only_name_reused_as_a_keyword(self) -> None:
        @process
        def fn(a: Text, /, **extras: Upper) -> tuple[str, dict[str, str]]:
            return a, extras

        assert fn(" X ", a=" y ") == ("x", {"a": " Y "})

    def test_a_keyword_named_like_the_var_keyword_parameter(self) -> None:
        @process
        def fn(**fields: Text) -> dict[str, str]:
            return fields

        assert fn(fields=" X ") == {"fields": "x"}

    def test_parameters_named_like_the_library_internals(self) -> None:
        @process
        def fn(name: Text, value: Text, fn: Text, args: Text, kwargs: Text) -> str:
            return name + value + fn + args + kwargs

        assert fn(name=" A", value=" B", fn=" C", args=" D", kwargs=" E") == "abcde"

    def test_empty_var_arguments(self) -> None:
        @process
        def fn(*items: Num, **fields: Num) -> tuple[tuple[int, ...], dict[str, int]]:
            return items, fields

        assert fn() == ((), {})

    def test_non_ascii_parameter_names(self) -> None:
        @process
        def fn(سعر: Num, größe: Num = 0) -> int:  # noqa: N803, PLC2401
            return سعر + größe

        assert fn(سعر="40", größe="2") == 42

    def test_many_marked_parameters(self) -> None:
        names = [f"p{index}" for index in range(200)]
        source = f"def fn({', '.join(f'{name}: Num' for name in names)}): return locals()"
        scope: dict[str, Any] = {"Num": Num}
        exec(source, scope)  # noqa: S102

        result = process(scope["fn"])(*(str(index) for index in range(200)))

        assert list(result.values()) == list(range(200))

    def test_a_mutable_default_is_shared_and_never_processed(self) -> None:
        default: list[str] = []

        @process
        def fn(items: Annotated[list[str], Process(sorted)] = default) -> list[str]:
            return items

        assert fn() is default
        assert fn(["b", "a"]) == ["a", "b"]

    def test_none_as_a_default_is_kept_but_none_passed_is_processed(self) -> None:
        @process
        def fn(limit: Num = None) -> int | None:  # type: ignore[assignment]
            return limit

        assert fn() is None
        with pytest.raises(ProcessArgumentError, match="Argument 'limit' with value None"):
            fn(None)

    def test_arguments_fail_in_signature_order_not_in_call_order(self) -> None:
        @process
        def fn(a: Num, b: Num) -> None: ...

        with pytest.raises(ProcessArgumentError) as info:
            fn(b="x", a="y")

        assert info.value.argument == "a"

    def test_later_arguments_are_not_processed_after_a_failure(self) -> None:
        seen: list[str] = []

        @process
        def fn(a: Num, b: Annotated[str, Process(seen.append)]) -> None: ...

        with pytest.raises(ProcessArgumentError):
            fn("x", "never")
        assert seen == []


class TestUnusualValues:
    @pytest.mark.parametrize("value", [0, "", [], False, 0.0])
    def test_falsy_values_are_processed(self, value: Any) -> None:
        assert process_value(Annotated[str, Process(repr)], value) == repr(value)

    def test_a_value_that_already_has_the_wanted_type(self) -> None:
        assert process_value(Num, 5) == 5
        assert process_value(Annotated[Decimal, Process(Decimal)], Decimal("1.5")) == Decimal("1.5")

    def test_some_converters_refuse_their_own_result(self) -> None:
        identifier = UUID(int=1)

        with pytest.raises(ProcessArgumentError, match="'UUID' object has no attribute"):
            process_value(Annotated[UUID, Process(UUID)], identifier)
        with pytest.raises(ProcessArgumentError, match="fromisoformat"):
            process_value(Annotated[datetime, Process(datetime.fromisoformat)], datetime.min)  # noqa: DTZ901

    def test_the_wrapped_function_is_the_way_around_processing(self) -> None:
        @process
        def fn(identifier: Annotated[UUID, Process(UUID)]) -> UUID:
            return identifier

        identifier = UUID(int=1)

        assert fn.__wrapped__(identifier) is identifier  # type: ignore[attr-defined]

    def test_replace_on_a_processed_dataclass_processes_every_field_again(self) -> None:
        @processed_dataclass
        class Item:
            name: Annotated[str, Process(str.strip)]
            identifier: Annotated[UUID, Process(UUID)]
            amount: Num = 1

        item = Item(" Tea ", str(UUID(int=1)))

        with pytest.raises(ProcessArgumentError, match="Argument 'identifier'"):
            dataclasses.replace(item, amount="3")

    def test_the_result_is_not_checked_against_the_annotation(self) -> None:
        assert process_value(Annotated[int, Process(str)], 5) == "5"

    def test_a_processor_that_returns_nothing_gives_none(self) -> None:
        values = ["b", "a"]

        assert process_value(Annotated[list[str], Process(list.sort)], values) is None
        assert values == ["a", "b"]

    def test_a_generator_is_consumed_by_its_processor(self) -> None:
        assert process_value(Annotated[list[int], Process(list)], (n for n in range(3))) == [
            0,
            1,
            2,
        ]

    def test_the_value_can_be_a_marker_or_a_function(self) -> None:
        marker = Process(int)

        assert process_value(Annotated[Any, Process(lambda value: value)], marker) is marker
        assert process_value(Annotated[str, Process(lambda fn: fn.__name__)], len) == "len"

    def test_not_a_number_and_infinity_are_valid_numbers(self) -> None:
        assert isnan(process_value(Annotated[float, Process(float)], "nan"))
        assert process_value(Annotated[float, Process(float)], "-inf") == float("-inf")
        assert process_value(Annotated[Decimal, Process(Decimal)], "NaN").is_nan()

    @pytest.mark.parametrize(
        ("processor", "raw", "expected"),
        [
            (bool, "false", True),
            (bool, "0", True),
            (bool, "", False),
            (int, " 42\n", 42),
            (int, "1_000", 1000),
            (int, "-0", 0),
            (int, 3.9, 3),
            (int, True, 1),
            (int, b"42", 42),
            (int, "٤٢", 42),
            (int, "４２", 42),
            (float, "1e3", 1000.0),
            (float, "١٫٥".replace("٫", "."), 1.5),
            (str, b"x", "b'x'"),
            (str, None, "None"),
            (Fraction, "1/3", Fraction(1, 3)),
            (partial(int, base=16), "ff", 255),
            (list, "abc", ["a", "b", "c"]),
            (str.strip, "\u00a0 x\u2003", "x"),
            (str.strip, "\u200bx", "\u200bx"),
            (str.casefold, "Straße", "strasse"),
            (str.lower, "Straße", "straße"),
        ],
    )
    def test_what_common_processors_really_do(
        self, processor: Any, raw: Any, expected: Any
    ) -> None:
        assert process_value(Annotated[Any, Process(processor)], raw) == expected

    def test_a_decimal_made_from_a_float_keeps_the_float_error(self) -> None:
        exact = Annotated[Decimal, Process(str), Process(Decimal)]

        assert process_value(Annotated[Decimal, Process(Decimal)], 0.1) != Decimal("0.1")
        assert process_value(exact, 0.1) == Decimal("0.1")

    def test_a_very_long_value(self) -> None:
        text = " x" * 500_000

        assert len(process_value(Text, text)) == 999_999

    def test_the_failing_value_is_kept_by_identity(self) -> None:
        value = ["not", "a", "number"]

        with pytest.raises(ProcessArgumentError) as info:
            process_value(Num, value)

        assert info.value.value is value


class TestUnusualProcessors:
    def test_a_processor_that_takes_no_argument(self) -> None:
        with pytest.raises(ProcessArgumentError, match="takes 0 positional arguments") as info:
            process_value(Annotated[int, Process(lambda: 1)], "x")

        assert isinstance(info.value.cause, TypeError)

    def test_a_processor_that_needs_two_arguments(self) -> None:
        with pytest.raises(ProcessArgumentError, match="missing 1 required positional argument"):
            process_value(Annotated[int, Process(lambda a, b: a)], "x")

    def test_exit_requests_are_not_wrapped(self) -> None:
        def interrupt(_: Any) -> Any:
            raise KeyboardInterrupt

        def leave(_: Any) -> Any:
            raise SystemExit(3)

        with pytest.raises(KeyboardInterrupt):
            process_value(Annotated[int, Process(interrupt)], "x")
        with pytest.raises(SystemExit):
            process_value(Annotated[int, Process(leave)], "x")

    def test_a_failure_without_a_message_shows_its_type(self) -> None:
        def refuse(_: Any) -> Any:
            raise ValueError

        with pytest.raises(ProcessArgumentError, match=r"failed to process, ValueError$"):
            process_value(Annotated[int, Process(refuse)], "x")

    def test_a_key_error_message_is_the_quoted_key(self) -> None:
        with pytest.raises(ProcessArgumentError, match=r"failed to process, 'x'$"):
            process_value(Annotated[int, Process({"a": 1}.__getitem__)], "x")

    def test_a_processor_that_is_itself_a_processed_function(self) -> None:
        @process
        def point(x: Num, y: Num = 0) -> tuple[int, int]:
            return x, y

        def to_point(text: str) -> tuple[int, int]:
            return point(*text.split(","))

        assert process_value(Annotated[tuple[int, int], Process(to_point)], "1,2") == (1, 2)

        with pytest.raises(
            ProcessArgumentError, match="Argument 'corner' with value '1,x'"
        ) as info:
            process_value(Annotated[tuple[int, int], Process(to_point)], "1,x", name="corner")

        inner = info.value.cause
        assert isinstance(inner, ProcessArgumentError)
        assert (inner.argument, inner.value) == ("y", "x")
        assert isinstance(inner.cause, ValueError)

    def test_a_stateful_processor_runs_once_per_passed_value(self) -> None:
        calls: list[Any] = []

        def record(value: Any) -> Any:
            calls.append(value)
            return value

        @process
        def fn(
            a: Annotated[Any, Process(record)],
            *rest: Annotated[Any, Process(record)],
            b: Annotated[Any, Process(record)] = 0,
        ) -> None: ...

        fn(1, 2, 3)

        assert calls == [1, 2, 3]

    def test_the_same_marker_twice_runs_twice(self) -> None:
        double = Process(lambda number: number * 2)

        assert process_value(Annotated[int, double, double], 3) == 12

    def test_markers_kept_in_constants(self) -> None:
        strip, lower = Process(str.strip), Process(str.lower)

        @process
        def fn(a: Annotated[str, strip, lower], b: Annotated[str, strip]) -> tuple[str, str]:
            return a, b

        assert fn(" A ", " B ") == ("a", "B")

    def test_a_subclass_of_the_marker_is_a_marker(self) -> None:
        class Convert(Process):
            pass

        assert process_value(Annotated[int, Convert(int)], "3") == 3

    def test_markers_compare_and_hash_by_their_function(self) -> None:
        assert len({Process(int), Process(int), Process(float)}) == 2
        assert Process(lambda value: value) != Process(lambda value: value)

    def test_a_marker_can_be_pickled_when_its_function_can(self) -> None:
        assert pickle.loads(pickle.dumps(Process(int))) == Process(int)  # noqa: S301

    def test_a_marker_is_not_a_processor(self) -> None:
        with pytest.raises(InvalidProcessorError, match="Process needs a callable"):
            Process(Process(int))  # type: ignore[arg-type]

    def test_the_marker_class_without_a_call_is_not_a_marker(self) -> None:
        assert process_value(Annotated[int, Process], "1") == "1"

    @pytest.mark.parametrize("processor", [int, len, str.strip, "".join, dict, print])
    def test_builtins_can_be_processors(self, processor: Any) -> None:
        assert Process(processor).fn is processor


class TestUnusualAnnotations:
    def test_nested_annotated_is_flattened_inner_first(self) -> None:
        inner = Annotated[str, Process(str.strip)]
        outer = Annotated[inner, Process(str.upper)]

        assert process_value(outer, " a ") == "A"

    def test_an_alias_of_an_alias_of_an_alias(self) -> None:
        type One = Annotated[str, Process(str.strip)]
        type Two = Annotated[One, Process(str.upper)]
        type Three = Two
        type Four = Annotated[Three, Process(list)]

        assert process_value(Four, " ab ") == ["A", "B"]

    def test_a_generic_alias(self) -> None:
        type Listed[T] = Annotated[list[T], Process(list)]

        assert process_value(Listed[int], (1, 2)) == [1, 2]
        assert process_value(Listed, "ab") == ["a", "b"]

    def test_an_alias_that_refers_to_itself_through_a_container(self) -> None:
        type Tree = Annotated[list[Tree], Process(tuple)]

        assert process_value(Tree, [[1], [2]]) == ([1], [2])

    @pytest.mark.parametrize(
        "annotation",
        [
            Text | None,
            Optional[Text],  # noqa: UP045
            list[Text],
            dict[str, Text],
            tuple[Text, ...],
            Final[Text],
            type[Text],
        ],
    )
    def test_a_marker_that_is_not_outermost_is_not_seen(self, annotation: Any) -> None:
        assert annotated_metadata(annotation) == ()
        assert process_value(annotation, " A ") == " A "

    def test_the_outermost_marker_can_wrap_any_type(self) -> None:
        maybe = Annotated[str | None, Process(optional(str.strip))]
        many = Annotated[list[str], Process(each(str.strip))]

        assert process_value(maybe, None) is None
        assert process_value(many, [" a "]) == ["a"]

    def test_a_string_annotation_is_not_evaluated_by_process_value(self) -> None:
        assert process_value("Text", " A ") == " A "

    def test_an_unknown_string_annotation_keeps_the_other_markers(self) -> None:
        def fn(a: "Text", b: "Missing", c: Num) -> None: ...  # type: ignore[name-defined]  # noqa: F821

        assert set(find_processors(fn)) == {"a", "c"}

    def test_metadata_that_only_looks_like_a_marker(self) -> None:
        class Lookalike:
            fn = int

        assert process_value(Annotated[int, Lookalike(), "Process(int)", int], "1") == "1"


class TestUnusualCallables:
    def test_a_lambda_has_no_annotations(self) -> None:
        fn = lambda value="x": value  # noqa: E731

        assert process(fn) is fn

    @pytest.mark.parametrize("builtin", [int, dict, len, print, str.strip])
    def test_a_builtin_is_returned_as_it_is(self, builtin: Any) -> None:
        assert find_processors(builtin) == {}
        assert process(builtin) is builtin

    def test_a_partial_keeps_what_it_bound_unprocessed(self) -> None:
        def fn(prefix: Text, amount: Num) -> tuple[str, int]:
            return prefix, amount

        assert process(partial(fn, " X "))("3") == (" X ", 3)
        assert process(partial(fn, amount="5"))(" X ") == ("x", "5")  # type: ignore[comparison-overlap]
        assert process(partial(fn, amount="5"))(" X ", amount="7") == ("x", 7)

    def test_a_callable_object(self) -> None:
        class Adder:
            def __call__(self, a: Num, b: Num = 0) -> int:
                return a + b

        assert process(Adder())("1", "2") == 3

    def test_a_bound_method(self) -> None:
        class Shop:
            def order(self, amount: Num) -> tuple[Any, int]:
                return self, amount

        shop = Shop()

        assert process(shop.order)("2") == (shop, 2)

    def test_class_methods_and_static_methods(self) -> None:
        class Shop:
            @classmethod
            @process
            def named(cls, name: Text) -> tuple[type, str]:
                return cls, name

            @staticmethod
            @process
            def price(amount: Num) -> int:
                return amount

        assert Shop.named(" A ") == (Shop, "a")
        assert Shop().named(" A ") == (Shop, "a")
        assert Shop.price("5") == Shop().price("5") == 5

    def test_an_overriding_method_must_be_decorated_again(self) -> None:
        class Base:
            @process
            def order(self, amount: Num) -> Any:
                return amount

        class Child(Base):
            def order(self, amount: Num) -> Any:
                return amount

        assert Base().order("2") == 2
        assert Child().order("2") == "2"

    def test_a_class_becomes_a_factory_function(self) -> None:
        class Order:
            def __init__(self, amount: Num) -> None:
                self.amount = amount

        make_order = process(Order)

        assert not isinstance(make_order, type)
        assert make_order.__wrapped__ is Order  # type: ignore[attr-defined]
        assert isinstance(make_order("2"), Order)
        assert make_order("2").amount == 2

    def test_a_dataclass_and_a_named_tuple(self) -> None:
        @dataclass
        class Point:
            x: Num
            y: Num = 0

        class Size(NamedTuple):
            width: Num
            height: Num = 0

        assert process(Point)("1", y="2") == Point(1, 2)
        assert process(Size)("3", "4") == Size(3, 4)

    def test_a_class_that_only_defines_new(self) -> None:
        class Token:
            def __new__(cls, value: Text) -> Self:
                token = super().__new__(cls)
                token.value = value  # type: ignore[attr-defined]
                return token

        assert process(Token)(" ABC ").value == "abc"  # type: ignore[attr-defined]

    def test_a_generator_function_fails_when_called_not_when_iterated(self) -> None:
        @process
        def countdown(start: Num) -> Iterator[int]:
            yield from range(start, 0, -1)

        assert list(countdown("3")) == [3, 2, 1]
        with pytest.raises(ProcessArgumentError):
            countdown("x")

    def test_a_coroutine_function_fails_when_called_not_when_awaited(self) -> None:
        @process
        async def fetch(amount: Num) -> int:
            return amount

        with pytest.raises(ProcessArgumentError):
            fetch("x")
        assert asyncio.run(fetch("2")) == 2

    def test_an_async_method(self) -> None:
        class Client:
            @process
            async def get(self, page: Num = 1) -> int:
                return page

        assert asyncio.run(Client().get("3")) == 3

    def test_recursion_processes_again_at_every_level(self) -> None:
        calls: list[Any] = []

        def record(value: Any) -> int:
            calls.append(value)
            return int(value)

        @process
        def factorial(number: Annotated[int, Process(record)]) -> int:
            return 1 if number <= 1 else number * factorial(number - 1)

        assert factorial("4") == 24
        assert calls == ["4", 3, 2, 1]

    def test_decorating_twice_processes_twice(self) -> None:
        @process
        @process
        def fn(number: Annotated[int, Process(lambda value: value + 1)]) -> int:
            return number

        assert fn(0) == 2

    def test_a_wrapping_decorator_that_hides_the_signature(self) -> None:
        def hiding(fn: Any) -> Any:
            def inner(*args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            return inner

        def keeping(fn: Any) -> Any:
            @wraps(fn)
            def inner(*args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            return inner

        def fn(amount: Num) -> Any:
            return amount

        assert process(hiding(fn))("2") == "2"
        assert process(keeping(fn))("2") == 2

    def test_under_a_cache_the_processed_values_are_the_key(self) -> None:
        calls: list[int] = []

        @process
        @lru_cache(maxsize=None)  # noqa: UP033
        def square(number: Num) -> int:
            calls.append(number)
            return number * number

        assert [square("3"), square(3), square(" 3 ")] == [9, 9, 9]
        assert calls == [3]

    def test_a_custom_signature_attribute_is_respected(self) -> None:
        def fn(*args: Any) -> Any:
            return args

        def model(amount: Num) -> None: ...

        fn.__signature__ = signature(model)  # type: ignore[attr-defined]
        fn.__annotations__ = model.__annotations__

        assert process(fn)("2") == (2,)

    def test_many_threads_share_nothing(self) -> None:
        @process
        def fn(number: Num, text: Text) -> tuple[int, str]:
            return number, text

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda index: fn(str(index), f" T{index} "), range(500)))

        assert results == [(index, f"t{index}") for index in range(500)]


class TestErrorsInTheCorners:
    def error(self) -> ProcessArgumentError:
        with pytest.raises(ProcessArgumentError) as info:
            process_value(Num, "two", name="limit")
        return info.value

    def test_it_belongs_to_three_families(self) -> None:
        error = self.error()

        assert isinstance(error, PyargprocessorsError)
        assert isinstance(error, TypeError)
        assert not isinstance(error, ValueError)

    def test_the_cause_is_chained_and_stored(self) -> None:
        error = self.error()

        assert error.cause is error.__cause__
        assert error.__suppress_context__ is True

    def test_its_parts(self) -> None:
        error = self.error()

        assert error.args == ("limit", "two", error.cause)
        assert str(error).startswith("Argument 'limit' with value 'two' failed to process, invalid")
        assert repr(error).startswith("ProcessArgumentError('limit', 'two', ValueError(")

    def test_it_can_be_copied_and_pickled(self) -> None:
        error = self.error()

        for clone in (copy.copy(error), pickle.loads(pickle.dumps(error))):  # noqa: S301
            assert (clone.argument, clone.value, str(clone)) == ("limit", "two", str(error))
            assert isinstance(clone.cause, ValueError)

    def test_notes_can_be_added_by_the_caller(self) -> None:
        error = self.error()
        error.add_note("at $[1]")

        assert error.__notes__ == ["at $[1]"]

    def test_an_except_clause_for_type_error_catches_it_first(self) -> None:
        caught = ""

        try:
            process_value(Num, "two")
        except TypeError:
            caught = "TypeError"
        except ProcessArgumentError:  # pragma: no cover
            caught = "ProcessArgumentError"

        assert caught == "TypeError"

    def test_inside_var_arguments(self) -> None:
        @process
        def fn(*items: Num, **fields: Num) -> None: ...

        with pytest.raises(ProcessArgumentError) as positional:
            fn("1", "x")
        with pytest.raises(ProcessArgumentError) as keyword:
            fn("1", size="x")

        assert positional.value.argument == "items"
        assert keyword.value.argument == "size"

    def test_the_value_reported_is_the_one_passed_not_the_one_half_processed(self) -> None:
        with pytest.raises(ProcessArgumentError) as info:
            process_value(
                Annotated[int, Process(str.strip), Process(str.upper), Process(int)], " x "
            )

        assert info.value.value == " x "

    def test_a_declaration_error_is_raised_once_and_early(self) -> None:
        def bad(amount: int = Process(int), other: int = Process(int)) -> None: ...  # type: ignore[assignment]

        with pytest.raises(InvalidProcessorError, match="default of 'amount'"):
            process(bad)


class TestEachAndOptionalCorners:
    @pytest.mark.parametrize("empty", [[], (), set(), frozenset(), {}])
    def test_empty_collections(self, empty: Any) -> None:
        assert each(int)(empty) == empty
        assert type(each(int)(empty)) is type(empty)

    def test_a_matrix(self) -> None:
        assert each(each(int))([["1", "2"], ("3",)]) == [[1, 2], (3,)]

    def test_subclasses_become_the_plain_builtin(self) -> None:
        point = namedtuple("point", "x y")("1", "2")  # noqa: PYI024
        ordered = OrderedDict(a="1")
        missing = defaultdict(list, a="1")

        assert type(each(int)(point)) is tuple
        assert type(each(int)(ordered)) is dict
        assert type(each(int)(missing)) is dict

    @pytest.mark.parametrize(
        "value",
        [
            "12",
            b"12",
            bytearray(b"12"),
            12,
            None,
            range(2),
            deque(["1"]),
            (n for n in "12"),
            {"1": 1}.keys(),
            {"1": 1}.values(),
        ],
    )
    def test_anything_else_is_rejected(self, value: Any) -> None:
        with pytest.raises(TypeError, match="expected a list, tuple, set or dict"):
            each(int)(value)

    def test_a_list_keeps_its_order_and_a_set_merges_equal_results(self) -> None:
        assert each(int)(["3", "1", "2"]) == [3, 1, 2]
        assert each(int)({"1", "01", " 1"}) == {1}

    def test_dict_keys_are_left_alone(self) -> None:
        assert each(str.upper)({" a ": "x", 1: "y", None: "z"}) == {" a ": "X", 1: "Y", None: "Z"}

    def test_unhashable_results_cannot_go_back_into_a_set(self) -> None:
        with pytest.raises(TypeError, match="unhashable"):
            each(list)({"ab"})

    def test_the_first_failing_item_stops_the_rest(self) -> None:
        seen: list[str] = []

        def record(value: str) -> int:
            seen.append(value)
            return int(value)

        with pytest.raises(ValueError, match="'x'"):
            each(record)(["1", "x", "3"])
        assert seen == ["1", "x"]

    @pytest.mark.parametrize("value", [0, "", False, [], 0.0])
    def test_optional_only_skips_none(self, value: Any) -> None:
        assert optional(repr)(value) == repr(value)

    def test_optional_twice_is_optional(self) -> None:
        assert optional(optional(int))(None) is None
        assert optional(optional(int))("1") == 1

    def test_optional_items_inside_each(self) -> None:
        assert each(optional(int))(["1", None, "3"]) == [1, None, 3]
        assert each(optional(int))({"a": None}) == {"a": None}

    def test_optional_does_not_hide_a_failure(self) -> None:
        with pytest.raises(ValueError, match="invalid literal"):
            optional(int)("x")


class TestProcessArgumentsCorners:
    def test_processors_for_absent_arguments_are_ignored(self) -> None:
        def fn(a: str = "") -> None: ...

        bound = signature(fn).bind()

        assert (
            process_arguments({"a": (Process(int),), "ghost": (Process(int),)}, bound).arguments
            == {}
        )

    def test_without_processors_a_copy_is_returned(self) -> None:
        def fn(a: str) -> None: ...

        bound = signature(fn).bind("x")
        processed = process_arguments({}, bound)

        assert processed == bound
        assert processed is not bound

    def test_applying_defaults_first_processes_them_too(self) -> None:
        def fn(a: Num = "9", *rest: Num, **extras: Num) -> None: ...  # type: ignore[assignment]

        bound = signature(fn).bind()
        bound.apply_defaults()

        assert process_arguments(find_processors(fn), bound).arguments == {
            "a": 9,
            "rest": (),
            "extras": {},
        }

    def test_partially_bound_arguments(self) -> None:
        def fn(a: Num, b: Num) -> None: ...

        bound = signature(fn).bind_partial(b="2")

        assert process_arguments(find_processors(fn), bound).arguments == {"b": 2}

    def test_an_empty_tuple_of_markers_does_nothing(self) -> None:
        def fn(a: str) -> None: ...

        assert process_arguments({"a": ()}, signature(fn).bind(" x ")).args == (" x ",)

    def test_the_result_can_be_changed_without_touching_the_original(self) -> None:
        def fn(a: Num) -> None: ...

        bound = signature(fn).bind("1")
        processed = process_arguments(find_processors(fn), bound)
        processed.arguments["a"] = 99

        assert bound.arguments == {"a": "1"}
