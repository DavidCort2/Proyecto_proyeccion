from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from .config import PlanningRules


def fichas_from_target(target_learners: int, learners_per_ficha: int) -> int:
    if target_learners < 0:
        raise ValueError("La meta de aprendices no puede ser negativa.")
    if learners_per_ficha <= 0:
        raise ValueError("Los aprendices por ficha deben ser mayores que cero.")
    return math.ceil(target_learners / learners_per_ficha) if target_learners else 0


def calculate_center_plan(
    target_learners: int,
    continuing_fichas: int,
    plant_instructors_scenario: int,
    rules: PlanningRules,
) -> dict[str, float | int]:
    """Resumen general de la planeación antes de distribuir fichas por especialidad."""
    if continuing_fichas < 0 or plant_instructors_scenario < 0:
        raise ValueError("Las fichas que pasan y los instructores no pueden ser negativos.")

    new_fichas = fichas_from_target(target_learners, rules.learners_per_ficha)
    active_fichas = new_fichas + continuing_fichas
    total_weekly_demand = active_fichas * rules.weekly_hours_per_ficha
    technical_demand = active_fichas * rules.weekly_technical_hours
    bilingual_demand = active_fichas * rules.weekly_bilingual_hours
    integrality_demand = active_fichas * rules.weekly_integrality_hours
    plant_capacity = plant_instructors_scenario * rules.weekly_plant_direct_hours

    return {
        "meta_aprendices": int(target_learners),
        "fichas_nuevas": int(new_fichas),
        "fichas_que_pasan": int(continuing_fichas),
        "fichas_activas": int(active_fichas),
        "demanda_total_horas_semana": float(total_weekly_demand),
        "demanda_tecnica_horas_semana": float(technical_demand),
        "demanda_bilinguismo_horas_semana": float(bilingual_demand),
        "demanda_integralidad_horas_semana": float(integrality_demand),
        "capacidad_planta_horas_semana": float(plant_capacity),
        "saldo_planta_horas_semana": float(plant_capacity - total_weekly_demand),
        "cupos_teoricos": int(new_fichas * rules.learners_per_ficha),
        "holgura_cupos": int(new_fichas * rules.learners_per_ficha - target_learners),
    }


def largest_remainder_allocation(
    total: int,
    labels: Iterable[str],
    weights: Iterable[float],
) -> dict[str, int]:
    labels = list(labels)
    weights = [max(0.0, float(w)) for w in weights]
    if total < 0:
        raise ValueError("El total no puede ser negativo.")
    if not labels:
        return {}
    if len(labels) != len(weights):
        raise ValueError("Labels y weights deben tener el mismo tamaño.")
    if total == 0:
        return {label: 0 for label in labels}

    weight_sum = sum(weights)
    if weight_sum == 0:
        weights = [1.0] * len(labels)
        weight_sum = float(len(labels))

    raw = [total * w / weight_sum for w in weights]
    base = [math.floor(x) for x in raw]
    remaining = total - sum(base)
    order = sorted(range(len(labels)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[:remaining]:
        base[i] += 1
    return dict(zip(labels, base))


def plant_resource_summary(df: pd.DataFrame, rules: PlanningRules) -> pd.DataFrame:
    plant = df.loc[df["Es planta"]].copy()
    if plant.empty:
        return pd.DataFrame(
            columns=[
                "Área",
                "Especialidad",
                "Instructores planta",
                "Capacidad semanal (h)",
                "Horas programadas actuales",
                "Brecha actual vs capacidad",
            ]
        )

    grouped = (
        plant.groupby(["Área", "Especialidad"], as_index=False)
        .agg(
            **{
                "Instructores planta": ("Nombre", "count"),
                "Horas programadas actuales": ("Horas programadas actuales", "sum"),
            }
        )
    )
    grouped["Capacidad semanal (h)"] = (
        grouped["Instructores planta"] * rules.weekly_plant_direct_hours
    )
    grouped["Brecha actual vs capacidad"] = (
        grouped["Capacidad semanal (h)"] - grouped["Horas programadas actuales"]
    )
    return grouped[
        [
            "Área",
            "Especialidad",
            "Instructores planta",
            "Capacidad semanal (h)",
            "Horas programadas actuales",
            "Brecha actual vs capacidad",
        ]
    ].sort_values(["Área", "Especialidad"], ignore_index=True)


def technical_specialty_catalog(df: pd.DataFrame) -> pd.DataFrame:
    """Catálogo técnico detectado, incluyendo especialidades sin planta actual."""
    technical = df.loc[df["Área"] == "Técnica"].copy()
    if technical.empty:
        return pd.DataFrame(
            columns=["Especialidad", "Instructores planta", "Contratistas actuales"]
        )

    rows: list[dict[str, object]] = []
    for specialty, group in technical.groupby("Especialidad", sort=True):
        rows.append(
            {
                "Especialidad": specialty,
                "Instructores planta": int(group["Es planta"].sum()),
                "Contratistas actuales": int((~group["Es planta"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def suggested_ficha_distribution(
    df: pd.DataFrame,
    new_fichas: int,
    continuing_fichas: int,
) -> pd.DataFrame:
    """
    Sugiere por separado fichas nuevas y fichas que pasan.

    La propuesta usa la cantidad de planta técnica como peso inicial. La tabla
    resultante es editable porque la oferta real debe reemplazar esta sugerencia.
    """
    catalog = technical_specialty_catalog(df)
    if catalog.empty:
        return pd.DataFrame(columns=["Especialidad", "Fichas nuevas", "Fichas que pasan"])

    labels = catalog["Especialidad"].tolist()
    weights = catalog["Instructores planta"].tolist()
    new_allocation = largest_remainder_allocation(new_fichas, labels, weights)
    continuing_allocation = largest_remainder_allocation(continuing_fichas, labels, weights)

    return pd.DataFrame(
        {
            "Especialidad": labels,
            "Fichas nuevas": [new_allocation[label] for label in labels],
            "Fichas que pasan": [continuing_allocation[label] for label in labels],
        }
    )


def _clean_distribution(distribution: pd.DataFrame) -> pd.DataFrame:
    required = {"Especialidad", "Fichas nuevas", "Fichas que pasan"}
    missing = required.difference(distribution.columns)
    if missing:
        raise ValueError(f"Faltan columnas en la distribución: {', '.join(sorted(missing))}")

    result = distribution.copy()
    result["Especialidad"] = result["Especialidad"].fillna("").astype(str).str.strip()
    result = result.loc[result["Especialidad"] != ""].copy()
    for column in ["Fichas nuevas", "Fichas que pasan"]:
        result[column] = (
            pd.to_numeric(result[column], errors="coerce")
            .fillna(0)
            .clip(lower=0)
            .round(0)
            .astype(int)
        )

    # Si el usuario agrega dos veces la misma especialidad, se consolidan sus fichas.
    result = (
        result.groupby("Especialidad", as_index=False)[["Fichas nuevas", "Fichas que pasan"]]
        .sum()
        .sort_values("Especialidad", ignore_index=True)
    )
    return result


def technical_staffing_plan(
    df: pd.DataFrame,
    distribution: pd.DataFrame,
    rules: PlanningRules,
) -> pd.DataFrame:
    """Calcula déficit y contratistas requeridos por especialidad técnica."""
    result = _clean_distribution(distribution)
    catalog = technical_specialty_catalog(df)
    plant_lookup = (
        catalog.set_index("Especialidad")["Instructores planta"].to_dict()
        if not catalog.empty
        else {}
    )

    result["Instructores planta"] = result["Especialidad"].map(plant_lookup).fillna(0).astype(int)
    result["Fichas activas"] = result["Fichas nuevas"] + result["Fichas que pasan"]
    result["Demanda técnica (h/sem)"] = result["Fichas activas"] * rules.weekly_technical_hours
    result["Capacidad planta (h/sem)"] = result["Instructores planta"] * rules.weekly_plant_direct_hours
    result["Déficit antes de contratar (h/sem)"] = (
        result["Demanda técnica (h/sem)"] - result["Capacidad planta (h/sem)"]
    ).clip(lower=0)
    result["Horas disponibles planta (h/sem)"] = (
        result["Capacidad planta (h/sem)"] - result["Demanda técnica (h/sem)"]
    ).clip(lower=0)
    result["Contratistas requeridos"] = result["Déficit antes de contratar (h/sem)"].apply(
        lambda deficit: math.ceil(float(deficit) / rules.weekly_contractor_hours)
        if deficit > 0
        else 0
    )
    result["Capacidad contrato proyectada (h/sem)"] = (
        result["Contratistas requeridos"] * rules.weekly_contractor_hours
    )
    result["Holgura después de contratar (h/sem)"] = (
        result["Capacidad planta (h/sem)"]
        + result["Capacidad contrato proyectada (h/sem)"]
        - result["Demanda técnica (h/sem)"]
    ).clip(lower=0)

    return result[
        [
            "Especialidad",
            "Fichas nuevas",
            "Fichas que pasan",
            "Fichas activas",
            "Instructores planta",
            "Demanda técnica (h/sem)",
            "Capacidad planta (h/sem)",
            "Déficit antes de contratar (h/sem)",
            "Horas disponibles planta (h/sem)",
            "Contratistas requeridos",
            "Capacidad contrato proyectada (h/sem)",
            "Holgura después de contratar (h/sem)",
        ]
    ]


def transversal_staffing_plan(
    df: pd.DataFrame,
    active_fichas: int,
    rules: PlanningRules,
) -> pd.DataFrame:
    """Calcula contratación requerida para Bilingüismo e Integralidad."""
    plant = df.loc[df["Es planta"]].copy()
    counts = plant.groupby("Área").size().to_dict()
    demand_hours = {
        "Bilingüismo": active_fichas * rules.weekly_bilingual_hours,
        "Integralidad": active_fichas * rules.weekly_integrality_hours,
    }

    rows: list[dict[str, float | int | str]] = []
    for area in ["Bilingüismo", "Integralidad"]:
        plant_heads = int(counts.get(area, 0))
        plant_capacity = plant_heads * rules.weekly_plant_direct_hours
        demand = float(demand_hours[area])
        deficit = max(0.0, demand - plant_capacity)
        contractors = math.ceil(deficit / rules.weekly_contractor_hours) if deficit > 0 else 0
        contract_capacity = contractors * rules.weekly_contractor_hours
        rows.append(
            {
                "Área": area,
                "Fichas atendidas": int(active_fichas),
                "Instructores planta": plant_heads,
                "Demanda (h/sem)": demand,
                "Capacidad planta (h/sem)": plant_capacity,
                "Déficit antes de contratar (h/sem)": deficit,
                "Horas disponibles planta (h/sem)": max(0.0, plant_capacity - demand),
                "Contratistas requeridos": contractors,
                "Capacidad contrato proyectada (h/sem)": contract_capacity,
                "Holgura después de contratar (h/sem)": max(
                    0.0, plant_capacity + contract_capacity - demand
                ),
            }
        )
    return pd.DataFrame(rows)


def staffing_summary(
    technical_plan: pd.DataFrame,
    transversal_plan: pd.DataFrame,
    rules: PlanningRules,
) -> dict[str, float | int]:
    technical_contractors = int(technical_plan["Contratistas requeridos"].sum()) if not technical_plan.empty else 0
    transversal_contractors = int(transversal_plan["Contratistas requeridos"].sum()) if not transversal_plan.empty else 0
    total_contractors = technical_contractors + transversal_contractors

    technical_deficit = (
        float(technical_plan["Déficit antes de contratar (h/sem)"].sum())
        if not technical_plan.empty
        else 0.0
    )
    transversal_deficit = (
        float(transversal_plan["Déficit antes de contratar (h/sem)"].sum())
        if not transversal_plan.empty
        else 0.0
    )
    total_deficit = technical_deficit + transversal_deficit

    return {
        "contratistas_tecnicos": technical_contractors,
        "contratistas_transversales": transversal_contractors,
        "contratistas_totales": total_contractors,
        "deficit_tecnico_horas_semana": technical_deficit,
        "deficit_transversal_horas_semana": transversal_deficit,
        "deficit_total_horas_semana": total_deficit,
        "capacidad_contrato_proyectada_horas_semana": total_contractors
        * rules.weekly_contractor_hours,
    }
