"""Lector del reporte seccionado 'Fichas programadas'."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from core.excel_parser import normalize_text


def parse_fichas_excel(source: str | Path | object) -> pd.DataFrame:
    raw = pd.read_excel(source, sheet_name=0, header=None, dtype=object, engine="openpyxl")
    expected = ["NUMERO FICHA", "TIPO FORMACION", "JORNADA", "TRIMESTRE"]
    if raw.shape[1] < 5:
        raise ValueError("El reporte debe contener N°, Número Ficha, Tipo Formación, Jornada y Trimestre.")
    headers = [index for index, row in raw.iterrows() if [normalize_text(v) for v in row.iloc[1:5]] == expected]
    if not headers:
        raise ValueError("No se encontraron los encabezados del reporte de fichas en la primera hoja.")
    specialty = None
    records = []
    for index, row in raw.iloc[headers[0] + 1:, :5].iterrows():
        values = row.tolist()
        if all(pd.isna(v) or not str(v).strip() for v in values):
            continue
        if [normalize_text(v) for v in values[1:]] == expected:
            continue
        if pd.notna(values[0]) and all(pd.isna(v) or not str(v).strip() for v in values[1:]):
            specialty = re.sub(r"\s+", " ", str(values[0])).strip().rstrip(" .")
            continue
        if not specialty or any(pd.isna(v) or not str(v).strip() for v in values[1:]):
            raise ValueError(f"Fila {index + 1}: faltan especialidad, ficha, nivel, jornada o trimestre.")
        records.append({
            "Ficha": re.sub(r"^(\d+)\.0$", r"\1", str(values[1]).strip()),
            "Especialidad": specialty,
            "Nivel": str(values[2]).strip(),
            "Jornada": str(values[3]).strip(),
            "Trimestre actual": values[4],
        })
    if not records:
        raise ValueError("No se encontraron fichas en el reporte.")
    result = pd.DataFrame(records)
    if result["Ficha"].duplicated().any():
        raise ValueError("Hay códigos de ficha repetidos en el reporte.")
    title = " ".join(str(v) for v in raw.iloc[:headers[0]].to_numpy().flatten() if pd.notna(v))
    period = re.search(r"(20\d{2})\s*[-–]?\s*TRIMESTRE\s*([1-4])\b", normalize_text(title))
    if period:
        result.attrs.update(report_year=int(period[1]), report_quarter=int(period[2]))
    return result
