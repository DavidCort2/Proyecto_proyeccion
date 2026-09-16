from pathlib import Path
from io import BytesIO

import pandas as pd
import pytest

from core.excel_parser import parse_instructors_excel


def test_parse_supplied_report(report_path):
    df = parse_instructors_excel(report_path)
    assert len(df) == 71
    assert int(df["Es planta"].sum()) == 19
    assert "Bilingüismo" in set(df["Área"])
    assert "Integralidad" in set(df["Área"])
    assert "Técnica" in set(df["Área"])


def report_bytes(rows):
    stream = BytesIO()
    pd.DataFrame(rows).to_excel(stream, index=False, header=False)
    stream.seek(0)
    return stream


def test_headers_can_move_and_empty_specialties_are_preserved():
    df = parse_instructors_excel(report_bytes([
        ["Título"], ["Otra nota"],
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["ESPECIALIDAD VACÍA"], ["SOFTWARE"],
        ["Ana Pérez", "001234", " Planta ", 32],
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["Luis López", "004567", "Contratista", 40],
    ]))
    assert df["Nombre"].tolist() == ["Ana Pérez", "Luis López"]
    assert df["Documento"].tolist() == ["001234", "004567"]
    assert df["Es planta"].tolist() == [True, False]
    assert len(df.attrs["specialties"]) == 2


def test_duplicate_instructors_are_rejected():
    with pytest.raises(ValueError, match="repetidos"):
        parse_instructors_excel(report_bytes([
            ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
            ["SOFTWARE"], ["Ana", "123", "Planta", 32], ["Ana", "123", "Planta", 32],
        ]))


def test_malformed_report_is_rejected():
    with pytest.raises(ValueError, match="encabezados"):
        parse_instructors_excel(report_bytes([["Otra", "clase", "de", "reporte"]]))
