from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import pandas as pd


EXPECTED_COLUMNS = ["Nombre", "Documento", "Tipo Contrato", "Total Horas"]


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


def classify_area(specialty: str) -> str:
    normalized = normalize_text(specialty)
    if "BILING" in normalized:
        return "Bilingüismo"
    if "INTEGRAL" in normalized:
        return "Integralidad"
    return "Técnica"


def parse_instructors_excel(source: str | Path | object) -> pd.DataFrame:
    """
    Convierte el reporte seccionado de instructores a una tabla normalizada.

    El formato esperado contiene filas de especialidad con solo la primera celda
    diligenciada, seguidas por filas de instructores con nombre, documento,
    tipo de contrato y total de horas.
    """
    raw = pd.read_excel(source, sheet_name=0, header=None, engine="openpyxl")
    if raw.shape[1] < 4:
        raise ValueError("El archivo debe contener al menos cuatro columnas.")

    current_specialty: str | None = None
    records: list[dict[str, object]] = []

    for _, row in raw.iloc[2:, :4].iterrows():
        name, document, contract_type, total_hours = row.tolist()
        first_has_value = pd.notna(name) and str(name).strip() != ""
        other_empty = all(pd.isna(v) or str(v).strip() == "" for v in [document, contract_type, total_hours])

        if first_has_value and other_empty:
            current_specialty = str(name).strip()
            continue

        if not first_has_value or pd.isna(contract_type) or str(contract_type).strip() == "":
            continue

        records.append(
            {
                "Especialidad": current_specialty or "SIN ESPECIALIDAD",
                "Área": classify_area(current_specialty or ""),
                "Nombre": str(name).strip(),
                "Documento": "" if pd.isna(document) else str(document).strip().replace(".0", ""),
                "Tipo Contrato": str(contract_type).strip(),
                "Horas programadas actuales": float(total_hours) if pd.notna(total_hours) else 0.0,
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise ValueError("No fue posible identificar instructores en el archivo.")

    df["Es planta"] = df["Tipo Contrato"].str.strip().str.casefold().eq("planta")
    return df
