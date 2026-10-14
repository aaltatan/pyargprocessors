import pytest

from examples import api, cli, events, form, rules, settings, validation


def test_form_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    form.main()

    assert capsys.readouterr().out.splitlines() == [
        "Pro Headphones (Sonic) $349.00 4.9*",
        "Studio Headphones (Sonic) $149.00 4.7*",
        "['Desk Lamp']",
        "['sonic', 'boom']",
        "Decimal('19.90')",
        (
            "ProcessArgumentError on 'limit': Argument 'limit' with value 'two' failed to process, "
            "invalid literal for int() with base 10: 'two'"
        ),
    ]


def test_settings_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    settings.main()

    assert capsys.readouterr().out.splitlines() == [
        "postgres://db.internal/shop",
        "8080 True WARNING",
        "('a.example.com', 'b.example.com')",
        "0:00:02.500000 data",
        "8000",
        "APP_PORT: a port is between 1 and 65535, got 99999",
    ]


def test_cli_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    cli.TODOS.clear()
    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "#1 Buy milk (priority high, due Sat 10 Oct, home, shop)",
        "#2 Call the bank (priority normal, due Mon 12 Oct)",
        "#3 Water the plants (priority normal)",
        "done: Buy milk, Water the plants",
        "error: bad value 'someday' for 'due': Invalid isoformat string: 'someday'",
        "error: bad value 'urgent' for 'priority': 'urgent' is not a valid Priority",
        "error: bad value 'x' for 'ids': invalid literal for int() with base 10: 'x'",
        "error: missing a required argument: 'title'",
    ]


def test_api_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    api.main()

    assert capsys.readouterr().out.splitlines() == [
        (
            "201 {'id': '8f14e45f-ceea-467f-a9d1-5c2f1c1f2a10', 'placed': '2026-10-09 14:30', "
            "'items': ['2 x TEA-01', '1 x MUG-07'], 'city': 'Damascus', 'coupon': None, "
            "'total': '21.00'}"
        ),
        (
            "('id', '8f14e45f-ceea-467f-a9d1-5c2f1c1f2a10') ('placed', '2026-10-09 14:30') "
            "('items', ['2 x TEA-01', '1 x MUG-07']) ('city', 'Damascus') ('coupon', 'AUTUMN') "
            "('total', '21.00')"
        ),
        "422 {'field': 'order_id', 'error': 'badly formed hexadecimal UUID string'}",
        (
            "422 {'field': 'lines.quantity', "
            "'error': \"invalid literal for int() with base 10: 'two'\"}"
        ),
        "422 {'field': 'lines', 'error': \"expected a list, tuple, set or dict, got 'tea-01'\"}",
        "400 {'error': \"got an unexpected keyword argument 'gift'\"}",
    ]


def test_validation_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    validation.main()

    assert capsys.readouterr().out.splitlines() == [
        (
            "{'email': 'ada@example.com', 'age': 36, 'plan': 'pro', 'referrer': None, "
            "'newsletter': True, 'topics': ['python', 'typing']}"
        ),
        "{}",
        "{'referrer': None, 'newsletter': False, 'topics': []}",
        "email: enter a valid email address",
        "age: must be between 13 and 120",
        "plan: choose one of: free, pro",
        (
            "{'email': 'this field is required', 'age': 'this field is required', "
            "'plan': 'this field is required'}"
        ),
    ]


def test_rules_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    rules.LOADED.clear()
    rules.main()

    assert capsys.readouterr().out.splitlines() == [
        "['Ada']",
        "['lists/blocked.txt']",
        (
            "{'age__gte': {'years': 'int', 'on': 'date'}, 'country__in': {'countries': 'str'}, "
            "'name__not_in': {'names': 'str'}}"
        ),
        (
            "ProcessArgumentError: Argument 'years' with value 'eighteen' failed to process, "
            "invalid literal for int() with base 10: 'eighteen'"
        ),
        "InvalidProcessorError: 'rule bad' cannot process 'user': it is not passed as an argument",
    ]


def test_events_example_runs(capsys: pytest.CaptureFixture[str]) -> None:
    events.main()

    assert capsys.readouterr().out.splitlines() == [
        "express to Damascus: 2 parcels, 1.55 kg",
        "delivered, signed by Ada Lovelace",
        "delivered, left at the door",
        "Shipped True",
        "Address(name='Ada Lovelace', city='Damascus', postcode='DM 101')",
        "Parcel(reference='A-1', weight=Decimal('1.2'))",
        "2026-10-14 True",
        "parcels.weight: 'heavy' failed (InvalidOperation)",
        "ValueError: promised for 11 Oct, before it was shipped",
    ]
