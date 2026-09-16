from pathlib import Path

import pytest


@pytest.fixture
def report_path():
    root = Path(__file__).resolve().parents[1]
    path = root / "reporteInstructores_2026_4.xlsx"
    return path if path.exists() else root / "data" / path.name
