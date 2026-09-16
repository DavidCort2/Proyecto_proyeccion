from __future__ import annotations

from pathlib import Path
import math
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
    raw = pd.read_excel(source, sheet_name=0, header=None, dtype=object, engine="openpyxl")
    if raw.shape[1] < 4:
        raise ValueError("El archivo debe contener al menos cuatro columnas.")

    current_specialty: str | None = None
    records: list[dict[str, object]] = []
    specialties: dict[str, str] = {}
    header = [normalize_text(column) for column in EXPECTED_COLUMNS]
    header_rows = [index for index, row in raw.iloc[:, :4].iterrows()
                   if [normalize_text(value) for value in row] == header]
    if not header_rows:
        raise ValueError("No se encontraron los encabezados Nombre, Documento, Tipo Contrato y Total Horas en la primera hoja.")

    for index, row in raw.iloc[header_rows[0] + 1:, :4].iterrows():
        name, document, contract_type, total_hours = row.tolist()
        if [normalize_text(value) for value in row] == header:
            continue
        first_has_value = pd.notna(name) and str(name).strip() != ""
        other_empty = all(pd.isna(v) or str(v).strip() == "" for v in [document, contract_type, total_hours])

        if first_has_value and other_empty:
            key = normalize_text(name)
            current_specialty = specialties.setdefault(key, re.sub(r"\s+", " ", str(name)).strip())
            continue

        if all(pd.isna(value) or str(value).strip() == "" for value in row):
            continue
        if not first_has_value or pd.isna(contract_type) or str(contract_type).strip() == "":
            raise ValueError(f"Fila {index + 1}: falta el nombre o el tipo de contrato del instructor.")
        if current_specialty is None:
            raise ValueError(f"Fila {index + 1}: el instructor no tiene una especialidad indicada antes de su registro.")
        try:
            hours = float(total_hours) if pd.notna(total_hours) else 0.0
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Fila {index + 1}: Total Horas debe ser un número.") from exc
        if not math.isfinite(hours) or hours < 0:
            raise ValueError(f"Fila {index + 1}: Total Horas debe ser un número no negativo.")

        records.append(
            {
                "Especialidad": current_specialty or "SIN ESPECIALIDAD",
                "Área": classify_area(current_specialty or ""),
                "Nombre": str(name).strip(),
                "Documento": "" if pd.isna(document) else re.sub(r"^(\d+)\.0$", r"\1", str(document).strip()),
                "Tipo Contrato": str(contract_type).strip(),
                "Horas programadas actuales": hours,
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        raise ValueError("No fue posible identificar instructores en el archivo.")

    df["Es planta"] = df["Tipo Contrato"].str.strip().str.casefold().eq("planta")
    documents = df.loc[df["Documento"].ne(""), "Documento"]
    if documents.duplicated().any():
        raise ValueError("Hay documentos de instructores repetidos. Revise el reporte para evitar duplicar la capacidad de planta.")
    df.attrs["specialties"] = [{"Especialidad": name, "Área": classify_area(name)} for name in specialties.values()]
    return df
