from functools import partial
from typing import Annotated

from pyargprocessors import annotated_metadata, resolved_annotations

type Port = Annotated[int, "tcp"]
type Tagged[T] = Annotated[T, "tag"]


class TestResolvedAnnotations:
    def test_strings_are_evaluated(self) -> None:
        def fn(port: "Port", host: str = "") -> None: ...

        assert resolved_annotations(fn) == {"port": Port, "host": str, "return": None}

    def test_unknown_names_are_kept_as_strings(self) -> None:
        def fn(port: "Missing") -> None: ...  # type: ignore[name-defined]  # noqa: F821

        assert resolved_annotations(fn)["port"] == "Missing"

    def test_class_uses_its_init(self) -> None:
        class Server:
            def __init__(self, port: Port) -> None: ...

        assert resolved_annotations(Server)["port"] is Port

    def test_callable_object_uses_its_call(self) -> None:
        class Connect:
            def __call__(self, port: Port) -> None: ...

        assert resolved_annotations(Connect())["port"] is Port

    def test_partial_uses_the_wrapped_function(self) -> None:
        def fn(host: str, port: Port) -> None: ...

        assert resolved_annotations(partial(fn, "localhost"))["port"] is Port


class TestAnnotatedMetadata:
    def test_plain_types_have_none(self) -> None:
        assert annotated_metadata(int) == ()
        assert annotated_metadata(None) == ()

    def test_aliases_are_looked_through(self) -> None:
        assert annotated_metadata(Port) == ("tcp",)
        assert annotated_metadata(Tagged[int]) == ("tag",)

    def test_nested_metadata_runs_inner_first(self) -> None:
        assert annotated_metadata(Annotated[Tagged[Port], "outer"]) == ("tcp", "tag", "outer")
