"""Continuaciones por ficha a partir del trimestre cursado y su duración."""
from __future__ import annotations

import math

import pandas as pd

from core.excel_parser import normalize_text


def is_op_schedule(schedule: str) -> bool:
    value = normalize_text(schedule).replace(" ", "")
    return value.startswith(("O&P", "P&O", "DIURNAO&P"))


def duration_in_quarters(level: str, schedule: str, schedule_overrides: dict[str, int] | None = None) -> int:
    level, schedule = normalize_text(level), normalize_text(schedule)
    if level in {"TECNICO", "TECNOLOGO"} and is_op_schedule(schedule):
        return 10
    if level == "TECNICO":
        return 3
    if level == "TECNOLOGO" and (schedule in {"DIURNA", "DIURNO"} or schedule.startswith("DIURNA-")):
        return 7
    if level == "TECNOLOGO" and schedule == "MIXTA":
        return 9
    if level == "TECNOLOGO" and schedule in (schedule_overrides or {}):
        duration = schedule_overrides[schedule]
        if duration in (7, 9):
            return duration
    raise ValueError(f"No hay una duración definida para nivel '{level}' y jornada '{schedule}'.")


def project_ficha_carryover(
    fichas: pd.DataFrame, report_year: int, report_quarter: int, planning_year: int,
    schedule_overrides: dict[str, int] | None = None,
    *,
    group_by_profile: bool = False,
    curriculum_durations: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """El trimestre reportado está en curso; la ficha termina al final de su último trimestre."""
    if not 1 <= report_quarter <= 4:
        raise ValueError("El trimestre calendario del reporte debe estar entre 1 y 4.")
    if planning_year <= report_year:
        raise ValueError("La vigencia a planear debe ser posterior al año del reporte de fichas.")
    required = {"Ficha", "Especialidad", "Nivel", "Jornada", "Trimestre actual"}
    if not required.issubset(fichas.columns):
        raise ValueError("El reporte de fichas debe identificar ficha, especialidad, nivel, jornada y trimestre actual.")
    if fichas.empty:
        raise ValueError("El reporte no contiene fichas.")
    if fichas["Ficha"].duplicated().any():
        raise ValueError("Hay códigos de ficha repetidos; revise el reporte para no duplicar continuaciones.")

    detail = fichas.copy()
    durations, finish_periods = [], []
    report_period = report_year * 4 + report_quarter - 1
    for row in detail.to_dict("records"):
        try:
            from core.curriculum import curriculum_key
            duration = (curriculum_durations or {}).get(curriculum_key(row["Especialidad"], row["Jornada"])) if curriculum_durations is not None else None
            if duration is None:
                duration = duration_in_quarters(row["Nivel"], row["Jornada"], schedule_overrides)
            current = float(row["Trimestre actual"])
            if not math.isfinite(current) or current < 1 or current % 1:
                raise ValueError("El trimestre actual debe ser un entero positivo.")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Ficha {row['Ficha']}: {exc}") from exc
        durations.append(duration)
        finish_periods.append(report_period + duration - int(current))
    detail["Duración (trimestres)"] = durations
    detail["Año fin estimado"] = [period // 4 for period in finish_periods]
    detail["Trimestre fin estimado"] = [period % 4 + 1 for period in finish_periods]
    detail["Pasa a la vigencia"] = [period >= planning_year * 4 for period in finish_periods]
    detail["Termina en la vigencia"] = [planning_year * 4 <= period < (planning_year + 1) * 4 for period in finish_periods]
    detail["Estado"] = [
        "Pasa y termina durante la vigencia" if ends else
        "Pasa y continúa después de la vigencia" if passes else
        "Termina antes de la vigencia"
        for passes, ends in zip(detail["Pasa a la vigencia"], detail["Termina en la vigencia"])
    ]
    group_columns = ["Especialidad"]
    if group_by_profile:
        detail["Nivel"] = detail["Nivel"].map(lambda value: {"TECNICO": "Técnico", "TECNOLOGO": "Tecnólogo"}[normalize_text(value)])
        schedules = []
        for schedule in detail["Jornada"]:
            normalized = normalize_text(schedule)
            if is_op_schedule(normalized):
                schedules.append("Diurna O&P")
            elif normalized == "MIXTA":
                schedules.append("Mixta")
            elif normalized in {"DIURNA", "DIURNO"} or normalized.startswith("DIURNA-"):
                schedules.append("Diurna")
            elif normalized in (schedule_overrides or {}):
                schedules.append("Mixta" if schedule_overrides[normalized] == 9 else "Diurna")
            else:
                raise ValueError(f"Defina si la jornada '{schedule}' es Diurna o Mixta para calcular sus horas.")
        detail["Jornada de planeación"] = schedules
        group_columns += ["Nivel", "Jornada de planeación"]
    summary = detail.groupby(group_columns, as_index=False).agg(**{
        "Fichas que pasan": ("Pasa a la vigencia", "sum"),
        "Fichas que terminan": ("Termina en la vigencia", "sum"),
    })
    summary = summary.rename(columns={"Jornada de planeación": "Jornada"})
    summary[["Fichas que pasan", "Fichas que terminan"]] = summary[["Fichas que pasan", "Fichas que terminan"]].astype(int)
    return detail, summary


def merge_ficha_specialties(summary: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Une coincidencias exactas normalizadas; conserva programas sin planta."""
    def key(name):
        return normalize_text(name).rstrip(" .")

    names = {key(name): name for name in catalog["Especialidad"]}
    mapped = summary.copy()
    mapped["Especialidad"] = mapped["Especialidad"].map(lambda name: names.get(key(name), name))
    if {"Nivel", "Jornada"}.issubset(mapped.columns):
        return mapped.groupby(["Especialidad", "Nivel", "Jornada"], as_index=False)[["Fichas que pasan", "Fichas que terminan"]].sum()
    mapped = mapped.groupby("Especialidad", as_index=False)[["Fichas que pasan", "Fichas que terminan"]].sum()
    missing = catalog.loc[~catalog["Especialidad"].isin(mapped["Especialidad"]), ["Especialidad"]].copy()
    missing["Fichas que pasan"] = 0
    missing["Fichas que terminan"] = 0
    return pd.concat([mapped, missing], ignore_index=True).sort_values("Especialidad", ignore_index=True)
