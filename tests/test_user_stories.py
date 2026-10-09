"""End-to-end user stories built on the examples."""

import asyncio
import json
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal
from inspect import iscoroutinefunction, signature
from pathlib import Path
from typing import Annotated, Any

import pytest

from examples import api, cli, form, rules, settings, validation
from pyargprocessors import (
    InvalidProcessorError,
    Process,
    ProcessArgumentError,
    find_processors,
    process,
    process_value,
)


class TestShopSearchForm:
    """As a shop developer, I hand the raw form to the search function and get typed arguments."""

    def test_the_whole_form_at_once(self) -> None:
        found = form.search(**form.FORM)  # type: ignore[arg-type]

        assert [product.name for product in found] == ["Pro Headphones", "Studio Headphones"]

    def test_only_the_fields_the_user_filled(self) -> None:
        assert [product.name for product in form.search(" LAMP ")] == ["Desk Lamp"]

    def test_an_extra_field_becomes_a_filter(self) -> None:
        found = form.search("headphones", brand=" BOOM ")

        assert [product.name for product in found] == ["Bass Headphones"]

    def test_a_price_range_from_two_text_boxes(self) -> None:
        found = form.search("headphones", low="30", high="100", limit="10")  # type: ignore[arg-type]

        assert [product.name for product in found] == ["Kids Headphones", "Travel Headphones"]

    def test_an_empty_upper_price_means_no_limit(self) -> None:
        found = form.search("pro", high=None)

        assert [product.price for product in found] == [Decimal("349.00")]

    def test_a_file_name_becomes_the_names_in_the_file(self) -> None:
        found = form.search("headphones", high="100", exclude="discontinued.txt", limit="10")  # type: ignore[arg-type]

        assert [product.name for product in found] == ["Budget Headphones"]

    def test_a_missing_file_is_reported_on_its_field(self) -> None:
        with pytest.raises(ProcessArgumentError) as info:
            form.search("headphones", exclude="nowhere.txt")  # type: ignore[arg-type]

        assert info.value.argument == "exclude"
        assert isinstance(info.value.cause, KeyError)

    def test_the_search_never_runs_on_a_bad_form(self) -> None:
        with pytest.raises(ProcessArgumentError, match="Argument 'low' with value 'cheap'"):
            form.search("headphones", low="cheap", limit="also bad")  # type: ignore[arg-type]

    def test_the_form_still_documents_itself(self) -> None:
        assert form.search.__doc__ == "Return the best rated products matching a search form."
        assert list(signature(form.search).parameters)[:3] == ["text", "low", "high"]


class TestApplicationSettings:
    """As an operator, I configure the application with environment variables."""

    def test_every_variable_gets_its_type(self) -> None:
        loaded = settings.load_settings(settings.ENVIRON)

        assert loaded == settings.Settings(
            database_url="postgres://db.internal/shop",
            port=8080,
            debug=True,
            log_level=settings.LogLevel.WARNING,
            allowed_hosts=("a.example.com", "b.example.com"),
            timeout=timedelta(seconds=2.5),
            data_dir=Path("data"),
        )

    def test_the_result_is_a_real_frozen_settings_object(self) -> None:
        loaded = settings.load_settings({"APP_DATABASE_URL": "sqlite://"})

        assert isinstance(loaded, settings.Settings)
        with pytest.raises(FrozenInstanceError):
            loaded.port = 1  # type: ignore[misc]

    def test_unset_variables_keep_their_defaults(self) -> None:
        loaded = settings.load_settings({"APP_DATABASE_URL": "sqlite://"})

        assert (loaded.port, loaded.debug, loaded.allowed_hosts) == (8000, False, ("localhost",))

    def test_variables_of_other_applications_are_ignored(self) -> None:
        loaded = settings.load_settings({"APP_DATABASE_URL": "sqlite://", "OTHER_PORT": "x"})

        assert loaded.port == 8000

    @pytest.mark.parametrize(
        ("variable", "value", "message"),
        [
            ("APP_PORT", "http", "invalid literal for int"),
            ("APP_PORT", "0", "a port is between 1 and 65535, got 0"),
            ("APP_LOG_LEVEL", "loud", "'LOUD' is not a valid LogLevel"),
            ("APP_TIMEOUT", "soon", "could not convert string to float"),
        ],
    )
    def test_a_bad_variable_stops_the_start_up(
        self, variable: str, value: str, message: str
    ) -> None:
        with pytest.raises(ProcessArgumentError, match=message) as info:
            settings.load_settings({**settings.ENVIRON, variable: value})

        assert f"APP_{info.value.argument.upper()}" == variable
        assert info.value.value == value

    def test_a_misspelled_variable_is_not_silently_dropped(self) -> None:
        with pytest.raises(TypeError, match="unexpected keyword argument 'prot'"):
            settings.load_settings({"APP_DATABASE_URL": "sqlite://", "APP_PROT": "8080"})

    def test_a_required_variable_must_be_set(self) -> None:
        with pytest.raises(TypeError, match="missing a required argument: 'database_url'"):
            settings.load_settings({})

    def test_tests_build_settings_from_real_objects_through_the_class(self) -> None:
        direct = settings.Settings(database_url="sqlite://", port=9000)

        assert direct.port == 9000


class TestTodoCommandLine:
    """As the author of a command line tool, I write commands as plain typed functions."""

    @pytest.fixture(autouse=True)
    def _empty_list(self) -> None:
        cli.TODOS.clear()

    def test_words_become_arguments(self) -> None:
        output = cli.run(["add", "  buy milk ", "--due=2026-12-31", "--tags=Home, SHOP,"])

        assert output == "#1 Buy milk (priority normal, due Thu 31 Dec, home, shop)"

    @pytest.mark.parametrize(
        ("word", "day"),
        [
            ("today", cli.TODAY),
            (" Tomorrow ", cli.TODAY + timedelta(days=1)),
            ("+10", cli.TODAY + timedelta(days=10)),
            ("2027-01-01", date(2027, 1, 1)),
        ],
    )
    def test_days_are_typed_the_way_people_say_them(self, word: str, day: date) -> None:
        assert process_value(cli.Day, word) == day

    def test_every_remaining_word_is_processed(self) -> None:
        for title in ("one", "two", "three"):
            cli.run(["add", title])

        assert cli.run(["done", "3", "1"]) == "done: Three, One"
        assert cli.TODOS == {2: "Two"}

    def test_a_bad_word_changes_nothing(self) -> None:
        cli.run(["add", "one"])

        assert cli.run(["done", "1", "x"]).startswith("error: bad value 'x' for 'ids'")
        assert cli.TODOS == {1: "One"}

    def test_an_unknown_option_is_an_ordinary_type_error(self) -> None:
        assert cli.run(["add", "one", "--colour=red"]) == (
            "error: got an unexpected keyword argument 'colour'"
        )

    def test_commands_are_still_callable_from_python(self) -> None:
        assert cli.add(" pay rent ", priority="HIGH") == "#1 Pay rent (priority high)"  # type: ignore[arg-type]
        assert cli.COMMANDS["add"] is cli.add


class TestOrderApi:
    """As an API developer, I let an async handler declare what the JSON body must become."""

    @staticmethod
    def request(**changes: Any) -> tuple[int, dict[str, Any]]:
        return asyncio.run(api.handle(json.dumps({**api.ORDER, **changes})))

    def test_the_handler_is_still_a_coroutine_function(self) -> None:
        assert iscoroutinefunction(api.create_order)

    def test_a_good_body_creates_the_order(self) -> None:
        status, order = self.request()

        assert status == 201
        assert order["total"] == "21.00"
        assert order["items"] == ["2 x TEA-01", "1 x MUG-07"]

    def test_null_and_absent_are_the_same_coupon(self) -> None:
        body = {key: value for key, value in api.ORDER.items() if key != "coupon"}
        _, without = asyncio.run(api.handle(json.dumps(body)))

        assert without["coupon"] is None
        assert self.request(coupon=None)[1]["coupon"] is None
        assert self.request(coupon="autumn")[1]["coupon"] == "AUTUMN"

    def test_numbers_and_strings_are_both_accepted_where_it_is_safe(self) -> None:
        _, order = self.request(lines=[{"sku": "x", "quantity": 3, "price": "0.10"}])

        assert order["total"] == "0.30"

    def test_a_bad_value_deep_in_the_body_is_located(self) -> None:
        lines = [*api.ORDER["lines"], {"sku": "x", "quantity": "1", "price": "free"}]  # type: ignore[misc]
        status, problem = self.request(lines=lines)

        assert status == 422
        assert problem["field"] == "lines.price"

    def test_a_nested_object_with_a_missing_key(self) -> None:
        status, problem = self.request(ship_to={"city": "Homs"})

        assert status == 422
        assert problem == {
            "field": "ship_to",
            "error": "missing a required argument: 'postcode'",
        }

    def test_a_body_with_an_unknown_key_is_a_bad_request(self) -> None:
        assert self.request(gift=True)[0] == 400

    def test_an_empty_order_is_valid_here(self) -> None:
        assert self.request(lines=[])[1]["total"] == "0"


class TestSignUpForm:
    """As a front-end developer, I get every bad field of a form in one answer."""

    def test_a_good_form_has_no_errors(self) -> None:
        values, errors = validation.clean(validation.SignUp, validation.GOOD_FORM)

        assert errors == {}
        assert values["email"] == "ada@example.com"
        assert values["age"] == 36

    def test_every_problem_is_reported_at_once(self) -> None:
        values, errors = validation.clean(validation.SignUp, validation.BAD_FORM)

        assert set(errors) == {"email", "age", "plan"}
        assert set(values) == {"referrer", "newsletter", "topics"}

    def test_a_checker_sees_the_converted_value(self) -> None:
        _, errors = validation.clean(validation.SignUp, {**validation.GOOD_FORM, "age": "121"})

        assert errors == {"age": "must be between 13 and 120"}

    def test_a_converter_failing_first_hides_the_checker(self) -> None:
        _, errors = validation.clean(validation.SignUp, {**validation.GOOD_FORM, "age": "old"})

        assert errors == {"age": "invalid literal for int() with base 10: 'old'"}

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_a_blank_optional_field_is_none(self, blank: str | None) -> None:
        values, _ = validation.clean(validation.SignUp, {**validation.GOOD_FORM, "referrer": blank})

        assert values["referrer"] is None

    def test_an_unticked_checkbox_is_simply_not_sent(self) -> None:
        form_data = {
            key: value for key, value in validation.GOOD_FORM.items() if key != "newsletter"
        }
        values, _ = validation.clean(validation.SignUp, form_data)

        assert values["newsletter"] is False

    def test_fields_the_form_does_not_declare_are_dropped(self) -> None:
        values, _ = validation.clean(validation.SignUp, {**validation.GOOD_FORM, "is_admin": "on"})

        assert "is_admin" not in values


class TestRulesLibrary:
    """As a library author, I let my users mark the arguments of their rules."""

    @pytest.fixture(autouse=True)
    def _nothing_loaded(self) -> None:
        rules.LOADED.clear()

    def test_rules_from_python_and_json_are_the_same(self) -> None:
        from_json = rules.compile_rules(rules.DEFINITION)
        ada, mallory, tim, linus = rules.USERS

        def from_python(user: rules.User) -> bool:
            return rules.age__gte("18")(user) and rules.country__in("uk", "ie")(user)

        assert [from_json(user) for user in rules.USERS] == [True, False, False, False]
        assert [from_python(user) for user in rules.USERS] == [True, True, False, False]
        assert rules.name__not_in("lists/blocked.txt")(mallory) is False
        assert (ada.name, tim.name, linus.name) == ("Ada", "Tim", "Linus")

    def test_arguments_are_processed_when_the_rule_is_built(self) -> None:
        blocked = rules.name__not_in("lists/blocked.txt")
        assert rules.LOADED == ["lists/blocked.txt"]

        for user in rules.USERS:
            blocked(user)
        assert rules.LOADED == ["lists/blocked.txt"]

    def test_a_bad_definition_fails_before_any_user_is_tested(self) -> None:
        with pytest.raises(ProcessArgumentError, match="Argument 'years' with value 'eighteen'"):
            rules.compile_rules([{"rule": "age__gte", "args": ["eighteen"]}])

    def test_the_library_says_what_the_json_must_send(self) -> None:
        assert rules.SENDS["name__not_in"] == {"names": "str"}
        assert rules.SENDS["age__gte"] == {"years": "int", "on": "date"}

    def test_the_object_under_test_cannot_be_marked(self) -> None:
        def bad(user: Annotated[rules.User, Process(str)]) -> bool:
            return bool(user)

        with pytest.raises(InvalidProcessorError, match="'rule bad' cannot process 'user'"):
            rules.rule(bad)

    def test_an_unmarked_rule_costs_nothing(self) -> None:
        @rules.rule
        def is_adult(user: rules.User) -> bool:
            return user.born.year < 2008

        assert find_processors(is_adult) == {}
        assert rules.RULES.pop("is_adult")()(rules.USERS[0]) is True


class TestSharedVocabulary:
    """As a team, we name our processed types once and use them everywhere."""

    def test_an_alias_from_one_module_works_in_another(self) -> None:
        @process
        def refund(amount: form.Money, reason: form.Text = "") -> tuple[Decimal, str]:
            return amount, reason

        assert refund("12.50", "  Damaged ") == (Decimal("12.50"), "damaged")

    def test_an_alias_is_extended_without_repeating_it(self) -> None:
        def slug(text: str) -> str:
            return text.replace(" ", "-")

        type Slug = Annotated[form.Text, Process(slug)]

        assert process_value(Slug, "  Green TEA ") == "green-tea"

    def test_an_alias_works_on_a_single_value(self) -> None:
        assert process_value(settings.Hosts, " a.example.com , b.example.com ") == (
            "a.example.com",
            "b.example.com",
        )

    def test_the_same_alias_reads_a_dictionary_field_by_field(self) -> None:
        row = {"price": "19.90", "brand": " SONIC "}
        types = {"price": form.Money, "brand": form.Text}

        assert {key: process_value(types[key], value, name=key) for key, value in row.items()} == {
            "price": Decimal("19.90"),
            "brand": "sonic",
        }
