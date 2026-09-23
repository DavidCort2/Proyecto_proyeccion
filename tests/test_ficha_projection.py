import pandas as pd
import pytest
from io import BytesIO
from pathlib import Path

from core.ficha_projection import merge_ficha_specialties, project_ficha_carryover
from core.fichas_parser import parse_fichas_excel


def ficha(level, schedule, current, code="1"):
    return {"Ficha": code, "Especialidad": "SOFTWARE", "Nivel": level, "Jornada": schedule, "Trimestre actual": current}


@pytest.mark.parametrize("level,schedule,current,passes,ends,finish", [
    ("Tecnólogo", "Diurna", 7, False, False, (2026, 4)),
    ("Tecnólogo", "Diurna", 6, True, True, (2027, 1)),
    ("Tecnólogo", "Mixta", 9, False, False, (2026, 4)),
    ("Tecnólogo", "Mixta", 8, True, True, (2027, 1)),
    ("Técnico", "Diurna", 3, False, False, (2026, 4)),
    ("Técnico", "Mixta", 2, True, True, (2027, 1)),
    ("Tecnólogo", "Mixta", 5, True, True, (2027, 4)),
    ("Tecnólogo", "Mixta", 4, True, False, (2028, 1)),
    ("Técnico", "Diurna", 4, False, False, (2026, 3)),
])
def test_quarter_boundaries(level, schedule, current, passes, ends, finish):
    detail, summary = project_ficha_carryover(pd.DataFrame([ficha(level, schedule, current)]), 2026, 4, 2027)
    assert detail["Pasa a la vigencia"].tolist() == [passes]
    assert detail["Termina en la vigencia"].tolist() == [ends]
    assert (detail.iloc[0]["Año fin estimado"], detail.iloc[0]["Trimestre fin estimado"]) == finish
    assert summary.iloc[0]["Fichas que pasan"] == int(passes)


def test_earlier_report_quarter_advances_to_year_end():
    rows = [ficha("Tecnólogo", "Diurna", 5, "1"), ficha("Tecnólogo", "Diurna", 4, "2")]
    detail, summary = project_ficha_carryover(pd.DataFrame(rows), 2026, 2, 2027)
    assert detail["Pasa a la vigencia"].tolist() == [False, True]
    assert summary["Fichas que pasan"].tolist() == [1]
    assert summary["Fichas que terminan"].tolist() == [1]


@pytest.mark.parametrize("current", [None, -1, 0, 1.5, "abc", float("inf")])
def test_invalid_current_quarter_is_rejected(current):
    with pytest.raises(ValueError, match="Ficha 1"):
        project_ficha_carryover(pd.DataFrame([ficha("Técnico", "Diurna", current)]), 2026, 4, 2027)


def test_unknown_schedule_and_duplicates_are_not_silently_counted():
    with pytest.raises(ValueError, match="duración"):
        project_ficha_carryover(pd.DataFrame([ficha("Tecnólogo", "Virtual", 2)]), 2026, 4, 2027)
    with pytest.raises(ValueError, match="repetidos"):
        project_ficha_carryover(pd.DataFrame([ficha("Técnico", "Diurna", 1)] * 2), 2026, 4, 2027)


@pytest.mark.parametrize("duration,total", [(7, 53), (9, 53)])
def test_supplied_report(duration, total):
    path = Path(__file__).resolve().parents[1] / "data/reporteFichas_2026_4.xlsx"
    fichas = parse_fichas_excel(path)
    assert len(fichas) == 66
    assert fichas.attrs == {"report_year": 2026, "report_quarter": 4}
    detail, summary = project_ficha_carryover(fichas, 2026, 4, 2027, {"P&O-MANANA": duration, "P&O-TARDE": duration})
    assert summary["Fichas que pasan"].sum() == total
    assert summary["Fichas que terminan"].sum() == 37
    # El modelo histórico reconoce mañana/tarde como diurna, sin una duración especial por abreviatura.
    assert detail.loc[detail["Jornada"].str.startswith("P&O"), "Duración (trimestres)"].eq(7).all()
    assert not detail.loc[detail["Nivel"] == "Técnico"].query('`Trimestre actual` >= 3')["Pasa a la vigencia"].any()


def excel_bytes(rows):
    result = BytesIO()
    pd.DataFrame(rows).to_excel(result, header=False, index=False)
    result.seek(0)
    return result


def test_parser_preserves_ficha_codes_and_detects_headers():
    frame = parse_fichas_excel(excel_bytes([
        ["Fichas programadas 2026 - Trimestre 4"], ["Nota"],
        ["N°", "Número Ficha", "Tipo Formación", "Jornada", "Trimestre"],
        ["SOFTWARE ."], [1, "001234", "Técnico", "Diurna-mañana", 2],
        [2, "NUEVA - SW", "Tecnólogo", "Mixta", 1],
    ]))
    assert frame["Ficha"].tolist() == ["001234", "NUEVA - SW"]
    assert frame["Especialidad"].tolist() == ["SOFTWARE", "SOFTWARE"]
    assert frame.attrs["report_quarter"] == 4


def test_merge_specialties_uses_catalog_names_and_keeps_new_programs():
    summary = pd.DataFrame([
        {"Especialidad": "diseno", "Fichas que pasan": 3, "Fichas que terminan": 1},
        {"Especialidad": "NUEVA", "Fichas que pasan": 2, "Fichas que terminan": 2},
    ])
    result = merge_ficha_specialties(summary, pd.DataFrame({"Especialidad": ["DISEÑO", "SIN FICHAS"]})).set_index("Especialidad")
    assert result.loc["DISEÑO", "Fichas que pasan"] == 3
    assert result.loc["SIN FICHAS", "Fichas que pasan"] == 0
    assert result.loc["NUEVA", "Fichas que pasan"] == 2


def test_malformed_report_is_rejected():
    with pytest.raises(ValueError, match="encabezados"):
        parse_fichas_excel(excel_bytes([["Otra", "clase", "de", "reporte", "incorrecto"]]))
