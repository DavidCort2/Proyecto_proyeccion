"""SQLite conserva una única carga y su última ejecución, de forma atómica."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS specialties (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    area TEXT NOT NULL,
    UNIQUE (name, area)
);
CREATE TABLE IF NOT EXISTS instructors (
    id INTEGER PRIMARY KEY,
    specialty_id INTEGER NOT NULL REFERENCES specialties(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    document TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    scheduled_hours REAL NOT NULL CHECK (scheduled_hours >= 0),
    is_plant INTEGER NOT NULL CHECK (is_plant IN (0, 1))
);
CREATE TABLE IF NOT EXISTS execution (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    saved_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE VIEW IF NOT EXISTS plant_instructors AS
SELECT i.name AS nombre, i.document AS documento,
       s.name AS especialidad, s.area AS area,
       i.scheduled_hours AS horas_programadas
FROM instructors i JOIN specialties s ON s.id = i.specialty_id
WHERE i.is_plant = 1;
"""


def _connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def save_planning(path: str | Path, instructors: pd.DataFrame, execution: dict) -> dict:
    """Reemplaza toda la carga; un fallo revierte también los borrados."""
    if instructors.empty:
        raise ValueError("No se puede guardar un reporte vacío.")
    payload = json.dumps(execution, ensure_ascii=False, allow_nan=False)
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as connection:
        connection.executescript(SCHEMA)
        with connection:
            connection.execute("DELETE FROM execution")
            connection.execute("DELETE FROM instructors")
            connection.execute("DELETE FROM specialties")
            catalog = {(row["Especialidad"], row["Área"]) for row in instructors.to_dict("records")}
            catalog.update((row["Especialidad"], row["Área"]) for row in instructors.attrs.get("specialties", []))
            catalog.update((row["Especialidad"], "Técnica") for row in execution["distribution"])
            connection.executemany("INSERT INTO specialties (name, area) VALUES (?, ?)", sorted(catalog))
            lookup = {(name, area): sid for sid, name, area in connection.execute("SELECT id, name, area FROM specialties")}
            connection.executemany(
                """INSERT INTO instructors
                   (specialty_id, name, document, contract_type, scheduled_hours, is_plant)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (lookup[(row["Especialidad"], row["Área"])], row["Nombre"], str(row["Documento"]),
                     row["Tipo Contrato"], float(row["Horas programadas actuales"]), int(row["Es planta"]))
                    for row in instructors.to_dict("records")
                ],
            )
            connection.execute("INSERT INTO execution (id, saved_at, payload) VALUES (1, ?, ?)", (saved_at, payload))
    return {**execution, "saved_at": saved_at}


def load_planning(path: str | Path) -> tuple[pd.DataFrame, dict] | None:
    if not Path(path).exists():
        return None
    with closing(_connect(path)) as connection:
        if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='execution'").fetchone():
            return None
        # Una sola instantánea incluso si otra sesión ejecuta un reemplazo.
        connection.execute("BEGIN")
        execution = connection.execute("SELECT saved_at, payload FROM execution WHERE id = 1").fetchone()
        if execution is None:
            return None
        instructors = pd.read_sql_query(
            """SELECT s.name AS 'Especialidad', s.area AS 'Área', i.name AS 'Nombre',
                      i.document AS 'Documento', i.contract_type AS 'Tipo Contrato',
                      i.scheduled_hours AS 'Horas programadas actuales', i.is_plant AS 'Es planta'
               FROM instructors i JOIN specialties s ON s.id = i.specialty_id ORDER BY i.id""",
            connection,
        )
        instructors["Es planta"] = instructors["Es planta"].astype(bool)
        instructors.attrs["specialties"] = [
            {"Especialidad": name, "Área": area}
            for name, area in connection.execute("SELECT name, area FROM specialties ORDER BY name")
        ]
    return instructors, {**json.loads(execution[1]), "saved_at": execution[0]}
