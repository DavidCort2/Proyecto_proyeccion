from pathlib import Path

import pytest


@pytest.fixture
def report_path():
    return Path(__file__).resolve().parent / "fixtures" / "reporteInstructores.xlsx"
