"""Validación y ejecución de una planeación completa, independiente de la UI."""
from __future__ import annotations

from dataclasses import asdict
import json
import math

import pandas as pd

from core.config import PlanningRules
from core.excel_parser import classify_area, normalize_text
from core.planner import (
    calculate_center_plan,
    fichas_from_target,
    growth_requirements,
    suggested_ficha_distribution,
    plant_resource_summary,
    staffing_summary,
    technical_staffing_plan,
    transversal_staffing_plan,
)

DISTRIBUTION_COLUMNS = ["Especialidad", "Fichas que pasan", "Fichas que terminan", "Fichas nuevas"]
MANUAL_COLUMNS = DISTRIBUTION_COLUMNS[:-1]


def validate_distribution(
    distribution: pd.DataFrame, instructors: pd.DataFrame,
    expected_new: int | None = None, expected_continuing: int | None = None,
) -> pd.DataFrame:
    if not {"Especialidad", "Fichas nuevas", "Fichas que pasan"}.issubset(distribution.columns):
        raise ValueError("La distribución debe incluir especialidad, fichas nuevas y fichas que pasan.")
    # Las ejecuciones anteriores no registraban cuántas continuaciones terminaban.
    distribution = distribution.copy()
    if "Fichas que terminan" not in distribution:
        distribution["Fichas que terminan"] = 0
    result = distribution[DISTRIBUTION_COLUMNS].copy()
    names = {normalize_text(name): name for name in instructors["Especialidad"]}
    names.update({normalize_text(row["Especialidad"]): row["Especialidad"] for row in instructors.attrs.get("specialties", [])})
    result["Especialidad"] = result["Especialidad"].fillna("").astype(str).str.strip()
    if result["Especialidad"].eq("").any():
        raise ValueError("Todas las filas de la distribución deben tener una especialidad.")
    result["Especialidad"] = result["Especialidad"].map(lambda name: names.get(normalize_text(name), name))
    if result["Especialidad"].map(normalize_text).duplicated().any():
        raise ValueError("Hay especialidades repetidas en la distribución. Use una fila por especialidad.")
    if result["Especialidad"].map(classify_area).ne("Técnica").any():
        raise ValueError("La distribución es técnica; bilingüismo e integralidad se calculan por separado.")
    for column in DISTRIBUTION_COLUMNS[1:]:
        values = pd.to_numeric(result[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f"{column}: ingrese números enteros mayores o iguales a cero en todas las filas.")
        result[column] = values.astype(int)
    if (result["Fichas que terminan"] > result["Fichas que pasan"]).any():
        raise ValueError("Las fichas que terminan no pueden superar las fichas que pasan de su especialidad.")
    if expected_new is not None and result["Fichas nuevas"].sum() != expected_new:
        raise ValueError(
            f"La distribución debe sumar {expected_new} fichas nuevas. "
            "Ajuste las fichas nuevas de la tabla o genere una nueva propuesta."
        )
    if expected_continuing is not None and result["Fichas que pasan"].sum() != expected_continuing:
        raise ValueError(f"Las fichas que pasan deben sumar {expected_continuing}.")
    return result.reset_index(drop=True)


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def project_distribution(
    manual: pd.DataFrame, instructors: pd.DataFrame, target_learners: int,
    learners_per_ficha: int,
) -> pd.DataFrame:
    """La misma proyección se usa en la vista previa y al ejecutar; no confía en nuevas previas."""
    validated = validate_distribution(manual.assign(**{"Fichas nuevas": 0}), instructors)
    target_fichas = fichas_from_target(target_learners, learners_per_ficha)
    return suggested_ficha_distribution(validated, target_fichas)[DISTRIBUTION_COLUMNS]


def execute_plan(
    instructors: pd.DataFrame, distribution: pd.DataFrame, rules: PlanningRules,
    target_learners: int, planning_year: int,
    source_name: str, source_digest: str,
) -> dict:
    errors = rules.validate()
    if errors:
        raise ValueError(" ".join(errors))
    if instructors.empty:
        raise ValueError("Cargue un reporte con instructores antes de ejecutar.")
    if not 2000 <= planning_year <= 2200:
        raise ValueError("La vigencia debe estar entre 2000 y 2200.")
    distribution = project_distribution(distribution, instructors, target_learners, rules.learners_per_ficha)
    continuing_fichas = int(distribution["Fichas que pasan"].sum())
    center = calculate_center_plan(
        target_learners, continuing_fichas, int(instructors["Es planta"].sum()), rules,
        projected_new_fichas=int(distribution["Fichas nuevas"].sum()),
    )
    center["fichas_que_terminan"] = int(distribution["Fichas que terminan"].sum())
    center["fichas_al_cierre"] = center["fichas_activas"] - center["fichas_que_terminan"]
    technical = technical_staffing_plan(instructors, distribution, rules)
    transversal = transversal_staffing_plan(instructors, center["fichas_activas"], rules)
    return {
        "planning_year": planning_year,
        "source_name": source_name,
        "source_digest": source_digest,
        "target_learners": target_learners,
        "continuing_fichas": continuing_fichas,
        "rules": asdict(rules),
        "distribution": records(distribution),
        "distribution_basis": "automatic_growth_v1",
        "growth_rule": growth_requirements(distribution),
        "center": center,
        "technical": records(technical),
        "transversal": records(transversal),
        "summary": staffing_summary(technical, transversal, rules),
        "resources": records(plant_resource_summary(instructors, rules)),
    }
