"""End to end: the text of a CSV file comes in, typed rows and a list of problems go out.

`csv.DictReader` gives a dict of strings for every line, `None` for a cell that
is missing, and puts surplus cells under the key `None`.
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from io import StringIO
from typing import Annotated

import pytest

from pyargprocessors import Process, ProcessArgumentError, optional, process


class Department(StrEnum):
    SALES = "sales"
    FINANCE = "finance"
    IT = "it"


def required(text: str) -> str:
    if not text:
        msg = "must not be empty"
        raise ValueError(msg)
    return text


def parse_day(text: str) -> date:
    """Read 2024-03-01 or 01/03/2024."""
    if "/" in text:
        return datetime.strptime(text, "%d/%m/%Y").date()  # noqa: DTZ007
    return date.fromisoformat(text)


def money(text: str) -> Decimal:
    """Read "1,200.50", " 900 " or "$1,000"."""
    amount = Decimal(text.replace(",", "").replace("$", "").strip())
    if amount < 0:
        msg = "must not be negative"
        raise ValueError(msg)
    return amount


def blank_to_none(text: str | None) -> str | None:
    return text.strip() or None if text else None


type Cell = Annotated[str, Process(str.strip)]


@dataclass(frozen=True, slots=True)
class Employee:
    name: Annotated[Cell, Process(required)]
    hired: Annotated[Cell, Process(parse_day)]
    salary: Annotated[Decimal, Process(money)]
    department: Annotated[Cell, Process(str.lower), Process(Department)]
    manager: Annotated[str | None, Process(blank_to_none), Process(optional(str.title))] = None


make_employee = process(Employee)


def import_employees(text: str) -> tuple[list[Employee], list[str]]:
    """Read every line it can, and say what is wrong with the others."""
    reader = csv.DictReader(StringIO(text.removeprefix("\ufeff")))
    employees: list[Employee] = []
    problems: list[str] = []

    for row in reader:
        if None in row:
            problems.append(f"line {reader.line_num}: too many cells")
            continue

        try:
            employees.append(make_employee(**row))
        except ProcessArgumentError as error:
            problems.append(f"line {reader.line_num}: {error.argument}: {error.cause}")

    return employees, problems


HEADER = "name,hired,salary,department,manager\n"

FILE = (
    "\ufeff" + HEADER + '  Ada Lovelace ,2024-03-01,"1,200.50",Finance,\n'
    "Linus,01/09/2023, 900 ,IT,ada lovelace\n"
    "أمين,2025-01-15,$750,sales,  \n"
)


class TestCleanFile:
    def test_every_cell_gets_its_type(self) -> None:
        employees, problems = import_employees(FILE)

        assert problems == []
        assert employees == [
            Employee("Ada Lovelace", date(2024, 3, 1), Decimal("1200.50"), Department.FINANCE),
            Employee("Linus", date(2023, 9, 1), Decimal(900), Department.IT, "Ada Lovelace"),
            Employee("أمين", date(2025, 1, 15), Decimal(750), Department.SALES),
        ]

    def test_money_adds_up_exactly(self) -> None:
        employees, _ = import_employees(FILE)

        assert sum(employee.salary for employee in employees) == Decimal("2850.50")

    def test_a_file_with_only_a_header(self) -> None:
        assert import_employees(HEADER) == ([], [])

    def test_an_empty_file(self) -> None:
        assert import_employees("") == ([], [])

    def test_a_missing_optional_column_uses_the_default(self) -> None:
        employees, problems = import_employees(
            "name,hired,salary,department\nAda,2024-03-01,1,it\n"
        )

        assert problems == []
        assert employees[0].manager is None

    def test_columns_in_another_order(self) -> None:
        employees, _ = import_employees("salary,department,hired,name\n5,IT,2024-03-01,Ada\n")

        assert employees == [Employee("Ada", date(2024, 3, 1), Decimal(5), Department.IT)]

    def test_quoted_cells_with_commas_and_new_lines(self) -> None:
        employees, _ = import_employees(HEADER + '"Ada\nLovelace",2024-03-01,"1,000",it,\n')

        assert employees[0].name == "Ada\nLovelace"
        assert employees[0].salary == Decimal(1000)


class TestDirtyFile:
    @pytest.mark.parametrize(
        ("line", "problem"),
        [
            (" ,2024-03-01,1,it,", "name: must not be empty"),
            ("Ada,2024-13-01,1,it,", "hired: month must be in 1..12"),
            ("Ada,31/02/2024,1,it,", "hired: day is out of range for month"),
            ("Ada,2024-03-01,-5,it,", "salary: must not be negative"),
            ("Ada,2024-03-01,1,hr,", "department: 'hr' is not a valid Department"),
        ],
    )
    def test_a_bad_cell_names_its_line_and_column(self, line: str, problem: str) -> None:
        assert import_employees(HEADER + line + "\n") == ([], [f"line 2: {problem}"])

    def test_a_cell_that_is_not_a_number(self) -> None:
        _, problems = import_employees(HEADER + "Ada,2024-03-01,a lot,it,\n")

        assert problems[0].startswith("line 2: salary: ")

    def test_the_cause_is_the_original_exception(self) -> None:
        with pytest.raises(ProcessArgumentError) as info:
            make_employee(name="Ada", hired="2024-03-01", salary="a lot", department="it")

        assert isinstance(info.value.cause, InvalidOperation)
        assert info.value.cause is info.value.__cause__

    def test_good_lines_are_kept_around_a_bad_one(self) -> None:
        text = HEADER + "Ada,2024-03-01,1,it,\nBob,yesterday,2,it,\nCy,2024-03-03,3,it,\n"
        employees, problems = import_employees(text)

        assert [employee.name for employee in employees] == ["Ada", "Cy"]
        assert problems == ["line 3: hired: Invalid isoformat string: 'yesterday'"]

    def test_a_short_line_has_missing_cells(self) -> None:
        _, problems = import_employees(HEADER + "Ada,2024-03-01\n")

        assert len(problems) == 1
        assert problems[0].startswith("line 2: salary: ")

    def test_a_long_line(self) -> None:
        assert import_employees(HEADER + "Ada,2024-03-01,1,it,,surplus\n") == (
            [],
            ["line 2: too many cells"],
        )

    def test_a_multi_line_cell_moves_the_line_number(self) -> None:
        text = HEADER + '"Ada\nLovelace",2024-03-01,1,it,\nBob,2024-03-01,x,it,\n'

        assert import_employees(text)[1][0].startswith("line 4: salary: ")
