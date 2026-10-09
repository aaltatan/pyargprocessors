"""End to end: a URL comes in, a JSON answer goes out.

`urllib.parse.parse_qs` gives a *list of strings* for every key, so each
parameter first says whether it wants the only value (`first`) or all of them.
"""

import json
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from pyargprocessors import Process, ProcessArgumentError, each, process

BOOKS = (
    {"title": "Fluent Python", "price": Decimal("45.00"), "tags": {"python"}},
    {"title": "Python for Data", "price": Decimal("39.50"), "tags": {"python", "data"}},
    {"title": "Web Basics", "price": Decimal("19.00"), "tags": {"web"}},
    {"title": "Die Straße", "price": Decimal("12.00"), "tags": {"fiction"}},
    {"title": "تعلم بايثون", "price": Decimal("25.00"), "tags": {"python", "عربي"}},
)


def first(values: list[str]) -> str:
    if len(values) != 1:
        msg = f"expected one value, got {len(values)}"
        raise ValueError(msg)
    return values[0]


def positive(number: int) -> int:
    if number < 1:
        msg = "must be 1 or more"
        raise ValueError(msg)
    return number


def parse_sort(text: str) -> tuple[str, bool]:
    """Read "price" or "-price" into a field and a descending flag."""
    field = text.removeprefix("-")
    if field not in {"title", "price"}:
        msg = f"cannot sort by {field!r}"
        raise ValueError(msg)
    return field, text.startswith("-")


type Query = Annotated[str, Process(first), Process(str.strip), Process(str.casefold)]
type Count = Annotated[int, Process(first), Process(int), Process(positive)]
type Tags = Annotated[frozenset[str], Process(each(str.casefold)), Process(frozenset)]
type Sort = Annotated[tuple[str, bool], Process(first), Process(parse_sort)]


@process
def list_books(
    q: Query = "",
    *,
    page: Count = 1,
    per_page: Count = 10,
    tag: Tags = frozenset(),
    sort: Sort = ("title", False),
) -> dict[str, Any]:
    field, descending = sort
    found = [book for book in BOOKS if q in book["title"].casefold() and tag <= book["tags"]]
    found.sort(key=lambda book: book[field], reverse=descending)
    start = (page - 1) * per_page
    return {
        "total": len(found),
        "titles": [book["title"] for book in found[start : start + per_page]],
    }


def get(url: str) -> tuple[int, dict[str, Any]]:
    """Serve a GET request: decode the query string, call the handler, encode the answer."""
    query = parse_qs(urlsplit(url).query, keep_blank_values=True)

    try:
        status, body = 200, list_books(**query)  # type: ignore[arg-type]
    except ProcessArgumentError as error:
        status = 422
        body = {"parameter": error.argument, "sent": error.value, "problem": str(error.cause)}
    except TypeError as error:
        status, body = 400, {"problem": str(error)}

    return status, json.loads(json.dumps(body, ensure_ascii=False))


class TestGoodRequests:
    def test_no_query_string_uses_every_default(self) -> None:
        assert get("https://shop.example/books") == (
            200,
            {
                "total": 5,
                "titles": [
                    "Die Straße",
                    "Fluent Python",
                    "Python for Data",
                    "Web Basics",
                    "تعلم بايثون",
                ],
            },
        )

    def test_percent_encoding_and_plus_signs_are_decoded_before_processing(self) -> None:
        status, body = get("https://shop.example/books?q=%20PYTHON+")

        assert status == 200
        assert body["titles"] == ["Fluent Python", "Python for Data"]

    def test_a_repeated_key_is_a_set_of_values(self) -> None:
        _, body = get("/books?tag=Python&tag=DATA")

        assert body["titles"] == ["Python for Data"]

    def test_paging(self) -> None:
        _, body = get("/books?per_page=2&page=2")

        assert body == {"total": 5, "titles": ["Python for Data", "Web Basics"]}

    def test_a_page_past_the_end_is_empty(self) -> None:
        assert get("/books?page=99")[1] == {"total": 5, "titles": []}

    def test_sorting(self) -> None:
        _, body = get("/books?sort=-price&per_page=2")

        assert body["titles"] == ["Fluent Python", "Python for Data"]

    def test_a_blank_search_matches_everything(self) -> None:
        assert get("/books?q=")[1]["total"] == 5

    def test_the_fragment_is_not_part_of_the_query(self) -> None:
        assert get("/books?q=web#reviews")[1]["titles"] == ["Web Basics"]

    def test_a_search_in_arabic(self) -> None:
        _, body = get(f"/books?q={quote('بايثون')}&tag={quote('عربي')}")

        assert body["titles"] == ["تعلم بايثون"]

    def test_casefold_matches_what_lower_would_miss(self) -> None:
        assert get("/books?q=STRASSE")[1]["titles"] == ["Die Straße"]

    def test_digits_of_other_scripts_are_numbers_too(self) -> None:
        _, body = get(f"/books?per_page=1&page={quote('٢')}")

        assert body["titles"] == ["Fluent Python"]


class TestBadRequests:
    def test_a_repeated_single_value(self) -> None:
        assert get("/books?page=1&page=2") == (
            422,
            {"parameter": "page", "sent": ["1", "2"], "problem": "expected one value, got 2"},
        )

    @pytest.mark.parametrize(
        ("query", "parameter", "problem"),
        [
            ("page=0", "page", "must be 1 or more"),
            ("page=-1", "page", "must be 1 or more"),
            ("page=one", "page", "invalid literal for int() with base 10: 'one'"),
            ("page=", "page", "invalid literal for int() with base 10: ''"),
            ("page=1.5", "page", "invalid literal for int() with base 10: '1.5'"),
            ("per_page=0", "per_page", "must be 1 or more"),
            ("sort=stars", "sort", "cannot sort by 'stars'"),
            ("sort=--price", "sort", "cannot sort by '-price'"),
        ],
    )
    def test_a_bad_value_names_its_parameter(
        self, query: str, parameter: str, problem: str
    ) -> None:
        status, body = get(f"/books?{query}")

        assert status == 422
        assert (body["parameter"], body["problem"]) == (parameter, problem)

    def test_an_unknown_parameter(self) -> None:
        assert get("/books?colour=red") == (
            400,
            {"problem": "got an unexpected keyword argument 'colour'"},
        )

    def test_only_the_first_bad_parameter_is_reported(self) -> None:
        assert get("/books?sort=stars&page=0")[1]["parameter"] == "page"
