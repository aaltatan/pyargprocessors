from functools import partial
from inspect import Signature, signature
from typing import Annotated, Any

import pytest

from pyargprocessors import (
    InvalidProcessorError,
    Process,
    ProcessArgumentError,
    find_processors,
    input_annotation,
    process_arguments,
    process_value,
)


def normalize(text: str) -> str:
    return text.strip().lower()


def load_rows(path: str) -> list[str]:
    return [f"row from {path}"]


type Text = Annotated[str, Process(normalize)]
type Rows = Annotated[list[str], Process(load_rows)]


class TestProcess:
    def test_holds_the_function(self) -> None:
        assert Process(int).fn is int

    def test_is_immutable_and_comparable(self) -> None:
        assert Process(int) == Process(int)
        assert Process(int) != Process(float)
        with pytest.raises(AttributeError):
            Process(int).fn = float  # type: ignore[misc]

    @pytest.mark.parametrize("fn", [None, 5, "int"])
    def test_needs_a_callable(self, fn: Any) -> None:
        with pytest.raises(InvalidProcessorError, match="Process needs a callable"):
            Process(fn)


class TestFindProcessors:
    def test_only_marked_parameters(self) -> None:
        def fn(a: Text, b: int, c: Annotated[int, Process(int), Process(abs)] = 0) -> None: ...

        assert find_processors(fn) == {
            "a": (Process(normalize),),
            "c": (Process(int), Process(abs)),
        }

    def test_no_markers(self) -> None:
        def fn(a: str, b=None) -> None: ...

        assert find_processors(fn) == {}

    def test_other_annotated_metadata_is_ignored(self) -> None:
        def fn(amount: Annotated[int, "documentation", Process(int), 42]) -> None: ...

        assert find_processors(fn) == {"amount": (Process(int),)}

    def test_string_annotations(self) -> None:
        def fn(name: "Text") -> None: ...

        assert find_processors(fn) == {"name": (Process(normalize),)}

    def test_var_parameters(self) -> None:
        def fn(*items: Text, **fields: Text) -> None: ...

        assert set(find_processors(fn)) == {"items", "fields"}

    def test_return_annotation_is_ignored(self) -> None:
        def fn(name: str) -> Text: ...

        assert find_processors(fn) == {}

    def test_class_uses_its_init(self) -> None:
        class Order:
            def __init__(self, name: Text) -> None: ...

        assert find_processors(Order) == {"name": (Process(normalize),)}

    def test_partial_uses_the_wrapped_function(self) -> None:
        def fn(prefix: str, name: Text) -> None: ...

        assert find_processors(partial(fn, "x")) == {"name": (Process(normalize),)}

    def test_marker_as_default_value(self) -> None:
        def bad(amount: int = Process(int)) -> None: ...  # type: ignore[assignment]

        with pytest.raises(
            InvalidProcessorError,
            match=r"'bad' uses Process as the default of 'amount'.*Annotated",
        ):
            find_processors(bad)

    def test_skipped_parameters_cannot_be_processed(self) -> None:
        def bad(subject: Text, key: str, amount: Annotated[int, Process(int)]) -> None: ...

        with pytest.raises(InvalidProcessorError, match="'bad' cannot process 'subject'"):
            find_processors(bad, skip=1)

    def test_skip_keeps_the_other_parameters(self) -> None:
        def fn(subject: object, key: str, amount: Annotated[int, Process(int)]) -> None: ...

        assert find_processors(fn, skip=2) == {"amount": (Process(int),)}

    def test_name_is_used_in_messages(self) -> None:
        def bad(subject: Text) -> None: ...

        with pytest.raises(InvalidProcessorError, match="'step click' cannot process 'subject'"):
            find_processors(bad, name="step click", skip=1)


class TestProcessArguments:
    def test_returns_new_bound_arguments(self) -> None:
        def fn(a: str, b: str = "") -> None: ...

        bound = signature(fn).bind(" A ")
        processed = process_arguments({"a": (Process(normalize),)}, bound)

        assert processed.arguments == {"a": "a"}
        assert bound.arguments == {"a": " A "}
        assert processed.args == ("a",)

    def test_unmarked_arguments_are_untouched(self) -> None:
        marker = object()

        def fn(value: object, amount: int) -> None: ...

        bound = signature(fn).bind(marker, "3")
        assert process_arguments({"amount": (Process(int),)}, bound).arguments == {
            "value": marker,
            "amount": 3,
        }

    def test_var_positional_processes_each_item(self) -> None:
        def fn(*toppings: str) -> None: ...

        bound = signature(fn).bind(" Foam", "COCOA ")
        processed = process_arguments({"toppings": (Process(normalize),)}, bound)
        assert processed.args == ("foam", "cocoa")

    def test_var_keyword_processes_each_value(self) -> None:
        def fn(**fields: str) -> None: ...

        bound = signature(fn).bind(brand=" SONIC ", color="Red")
        processed = process_arguments({"fields": (Process(normalize),)}, bound)
        assert processed.kwargs == {"brand": "sonic", "color": "red"}

    def test_failure_names_the_argument_and_value(self) -> None:
        def fn(amount: int) -> None: ...

        with pytest.raises(
            ProcessArgumentError, match="Argument 'amount' with value 'two' failed to process"
        ) as info:
            process_arguments({"amount": (Process(int),)}, signature(fn).bind("two"))

        assert isinstance(info.value.__cause__, ValueError)
        assert (info.value.argument, info.value.value) == ("amount", "two")

    def test_failure_inside_var_keyword_names_the_key(self) -> None:
        def fn(**fields: str) -> None: ...

        with pytest.raises(ProcessArgumentError, match="Argument 'brand' with value 5"):
            process_arguments({"fields": (Process(normalize),)}, signature(fn).bind(brand=5))

    def test_failure_in_the_second_processor_reports_the_original_value(self) -> None:
        def fn(n: int) -> None: ...

        processors = {"n": (Process(str.strip), Process(int))}
        with pytest.raises(ProcessArgumentError, match="Argument 'n' with value ' x '"):
            process_arguments(processors, signature(fn).bind(" x "))


class TestProcessValue:
    def test_applies_the_markers_left_to_right(self) -> None:
        annotation = Annotated[str, Process(str.strip), Process(str.upper), Process(list)]
        assert process_value(annotation, " ab ") == ["A", "B"]

    def test_looks_through_aliases(self) -> None:
        assert process_value(Rows, "a.csv") == ["row from a.csv"]

    def test_unmarked_annotation_keeps_the_value(self) -> None:
        marker = object()
        assert process_value(object, marker) is marker

    def test_failure_uses_the_given_name(self) -> None:
        with pytest.raises(ProcessArgumentError, match="Argument 'limit' with value 'two'"):
            process_value(Annotated[int, Process(int)], "two", name="limit")

    def test_a_marker_inside_a_union_is_not_seen(self) -> None:
        assert process_value(Text | None, " A ") == " A "


class TestInputAnnotation:
    @pytest.mark.parametrize(
        ("processor", "expected"),
        [
            (load_rows, str),
            (normalize, str),
            (int, None),
            (str.strip, None),
            (lambda value: value, None),
            (lambda: None, None),
        ],
    )
    def test_input_annotation(self, processor: Any, expected: Any) -> None:
        assert input_annotation(Process(processor)) is expected


class TestBuildingOnTop:
    def test_a_factory_that_keeps_its_first_parameter(self) -> None:
        def rule(fn: Any) -> Any:
            processors = find_processors(fn, skip=1)
            arguments = Signature(list(signature(fn).parameters.values())[1:])

            def factory(*args: Any, **kwargs: Any) -> Any:
                bound = process_arguments(processors, arguments.bind(*args, **kwargs))
                return lambda obj: fn(obj, *bound.args, **bound.kwargs)

            return factory

        @rule
        def name__eq(name: str, value: Text) -> bool:
            return name == value

        assert name__eq("  Tea ")("tea") is True
        assert name__eq(value="milk")("tea") is False


class TestExceptions:
    def test_both_are_type_errors(self) -> None:
        assert issubclass(InvalidProcessorError, TypeError)
        assert issubclass(ProcessArgumentError, TypeError)
