from pathlib import Path

from core.excel_parser import parse_instructors_excel


def test_parse_supplied_report():
    path = Path(__file__).resolve().parents[1] / "data" / "reporteInstructores_2026_4.xlsx"
    df = parse_instructors_excel(path)
    assert len(df) == 71
    assert int(df["Es planta"].sum()) == 19
    assert "Bilingüismo" in set(df["Área"])
    assert "Integralidad" in set(df["Área"])
    assert "Técnica" in set(df["Área"])
