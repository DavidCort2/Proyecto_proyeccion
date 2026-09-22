"""Metas independientes por nivel; horas por jornada y planta compartida por especialidad."""
from dataclasses import asdict

import pandas as pd

from core.config import PlanningRules
from core.excel_parser import classify_area, normalize_text
from core.planner import (
    fichas_from_target, growth_requirements, largest_remainder_allocation,
    plant_resource_summary, staffing_summary, suggested_ficha_distribution,
    technical_staffing_plan, transversal_staffing_plan,
)
from core.workflow import records

PROFILE_COLUMNS = ["Especialidad", "Nivel", "Jornada"]
MANUAL_COLUMNS = PROFILE_COLUMNS + ["Fichas que pasan", "Fichas que terminan"]


def validate_profiles(manual: pd.DataFrame, instructors: pd.DataFrame) -> pd.DataFrame:
    if not set(MANUAL_COLUMNS).issubset(manual.columns):
        raise ValueError("Indique especialidad, nivel, jornada, fichas que pasan y fichas que terminan.")
    result = manual[MANUAL_COLUMNS].copy()
    names = {normalize_text(name): name for name in instructors["Especialidad"]}
    names.update({normalize_text(row["Especialidad"]): row["Especialidad"] for row in instructors.attrs.get("specialties", [])})
    result["Especialidad"] = result["Especialidad"].fillna("").astype(str).str.strip()
    if result["Especialidad"].eq("").any():
        raise ValueError("Todas las filas deben tener una especialidad.")
    result["Especialidad"] = result["Especialidad"].map(lambda name: names.get(normalize_text(name), name))
    if result["Especialidad"].map(classify_area).ne("Técnica").any():
        raise ValueError("Use especialidades técnicas; bilingüismo e integralidad se calculan por separado.")
    result["Nivel"] = result["Nivel"].map(lambda value: {"TECNICO": "Técnico", "TECNOLOGO": "Tecnólogo"}.get(normalize_text(value)))
    result["Jornada"] = result["Jornada"].map(lambda value: {"DIURNA": "Diurna", "MIXTA": "Mixta", "DIURNA O&P": "Diurna O&P"}.get(normalize_text(value)))
    if result[["Nivel", "Jornada"]].isna().any().any():
        raise ValueError("Seleccione Técnico o Tecnólogo y Diurna, Mixta o Diurna O&P en todas las filas.")
    if result.duplicated(PROFILE_COLUMNS).any():
        raise ValueError("Use una sola fila por especialidad, nivel y jornada.")
    for column in MANUAL_COLUMNS[-2:]:
        values = pd.to_numeric(result[column], errors="coerce")
        if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f"{column}: ingrese enteros no negativos en todas las filas.")
        result[column] = values.astype(int)
    if (result["Fichas que terminan"] > result["Fichas que pasan"]).any():
        raise ValueError("Las fichas que terminan no pueden superar las que pasan en esa fila.")
    return result.reset_index(drop=True)


def project_by_level(manual: pd.DataFrame, instructors: pd.DataFrame, targets: dict, rules: PlanningRules):
    result = validate_profiles(manual, instructors)
    result["Fichas nuevas"] = 0
    level_rows, minimum_rows = [], []
    for level in ["Técnico", "Tecnólogo"]:
        target = targets[level]
        expected = fichas_from_target(target, rules.learners_per_ficha)
        subset = result.loc[result["Nivel"] == level]
        if subset.empty and expected:
            raise ValueError(f"Agregue al menos una fila de {level} para distribuir su meta.")
        # El crecimiento se redondea por especialidad y nivel, nunca dos veces por jornada.
        by_specialty = subset.groupby("Especialidad", as_index=False)[MANUAL_COLUMNS[-2:]].sum()
        projected = suggested_ficha_distribution(by_specialty, expected)
        minimum = growth_requirements(by_specialty)
        minimum_rows.extend({**row, "Nivel": level} for row in minimum["rows"])
        for row in projected.to_dict("records"):
            group = subset.loc[subset["Especialidad"] == row["Especialidad"]]
            remaining = int(row["Fichas nuevas"] - group["Fichas que terminan"].sum())
            allocation = largest_remainder_allocation(remaining, group.index, group["Fichas que pasan"])
            for index in group.index:
                result.loc[index, "Fichas nuevas"] = int(result.loc[index, "Fichas que terminan"]) + allocation[index]
        total_new = int(projected["Fichas nuevas"].sum())
        level_rows.append({
            "Nivel": level, "Meta de aprendices": int(target), "Fichas según meta": expected,
            "Fichas nuevas": total_new, "Fichas sobre la meta": total_new - expected,
            "Cupos proyectados": total_new * rules.learners_per_ficha,
        })
    return result, pd.DataFrame(level_rows), minimum_rows


def hours_by_profile(distribution: pd.DataFrame, rules: PlanningRules) -> pd.DataFrame:
    result = distribution.copy()
    mixed = result["Jornada"].eq("Mixta")
    result["Fichas activas"] = result["Fichas que pasan"] + result["Fichas nuevas"]
    result["Fichas al cierre"] = result["Fichas activas"] - result["Fichas que terminan"]
    for column, day, night in [
        ("Horas por ficha (h/sem)", rules.weekly_hours_per_ficha, rules.mixed_weekly_hours_per_ficha),
        ("Técnicas por ficha (h/sem)", rules.weekly_technical_hours, rules.mixed_weekly_technical_hours),
        ("Bilingüismo por ficha (h/sem)", rules.weekly_bilingual_hours, rules.mixed_weekly_bilingual_hours),
        ("Integralidad por ficha (h/sem)", rules.weekly_integrality_hours, rules.mixed_weekly_integrality_hours),
    ]:
        result[column] = pd.Series(day, index=result.index).where(~mixed, night)
    result["Horas totales (h/sem)"] = result["Fichas activas"] * result["Horas por ficha (h/sem)"]
    result["Horas nuevas (h/sem)"] = result["Fichas nuevas"] * result["Horas por ficha (h/sem)"]
    for name in ["Técnicas", "Bilingüismo", "Integralidad"]:
        result[f"{name} (h/sem)"] = result["Fichas activas"] * result[f"{name} por ficha (h/sem)"]
    return result


def _execute_unscheduled_plan(instructors, manual, rules, targets, planning_year, source_name, source_digest):
    errors = rules.validate()
    if errors:
        raise ValueError(" ".join(errors))
    if instructors.empty or not 2000 <= planning_year <= 2200:
        raise ValueError("Revise el reporte de instructores y la vigencia a planear.")
    distribution, levels, minimums = project_by_level(manual, instructors, targets, rules)
    hours = hours_by_profile(distribution, rules)
    totals = distribution.groupby("Especialidad", as_index=False)[["Fichas nuevas", "Fichas que pasan", "Fichas que terminan"]].sum()
    demands = hours.groupby("Especialidad")["Técnicas (h/sem)"].sum().to_dict()
    technical = technical_staffing_plan(instructors, totals, rules, demand_by_specialty=demands)
    active = int(hours["Fichas activas"].sum())
    transversal = transversal_staffing_plan(instructors, active, rules, demand_by_area={
        "Bilingüismo": float(hours["Bilingüismo (h/sem)"].sum()),
        "Integralidad": float(hours["Integralidad (h/sem)"].sum()),
    })
    new = int(distribution["Fichas nuevas"].sum())
    target_total = sum(targets.values())
    capacity = int(instructors["Es planta"].sum()) * rules.weekly_plant_direct_hours
    center = {
        "meta_aprendices": target_total, "fichas_segun_meta": int(levels["Fichas según meta"].sum()),
        "fichas_adicionales_sobre_meta": int(levels["Fichas sobre la meta"].sum()),
        "aprendices_proyectados": new * rules.learners_per_ficha,
        "fichas_nuevas": new, "fichas_que_pasan": int(distribution["Fichas que pasan"].sum()),
        "fichas_que_terminan": int(distribution["Fichas que terminan"].sum()),
        "fichas_activas": active, "fichas_al_cierre": int(hours["Fichas al cierre"].sum()),
        "demanda_total_horas_semana": float(hours["Horas totales (h/sem)"].sum()),
        "demanda_nuevas_horas_semana": float(hours["Horas nuevas (h/sem)"].sum()),
        "demanda_tecnica_horas_semana": float(hours["Técnicas (h/sem)"].sum()),
        "demanda_bilinguismo_horas_semana": float(hours["Bilingüismo (h/sem)"].sum()),
        "demanda_integralidad_horas_semana": float(hours["Integralidad (h/sem)"].sum()),
        "capacidad_planta_horas_semana": capacity,
        "saldo_planta_horas_semana": capacity - float(hours["Horas totales (h/sem)"].sum()),
        "cupos_teoricos": new * rules.learners_per_ficha,
        "holgura_cupos": new * rules.learners_per_ficha - target_total,
    }
    return {
        "planning_year": planning_year, "source_name": source_name, "source_digest": source_digest,
        "targets_by_level": targets, "target_learners": target_total,
        "continuing_fichas": center["fichas_que_pasan"], "rules": asdict(rules),
        "distribution": records(distribution), "distribution_basis": "level_schedule_v1",
        "levels": records(levels), "hours": records(hours), "center": center,
        "growth_rule": {"percent": 5, "basis": "per_specialty_and_level", "rows": minimums,
                        "new_fichas": sum(row["Mínimo de fichas nuevas"] for row in minimums),
                        "replacement_fichas": sum(row["Fichas que terminan"] for row in minimums),
                        "growth_fichas": sum(row["Crecimiento mínimo (5 %)"] for row in minimums)},
        "technical": records(technical), "transversal": records(transversal),
        "summary": staffing_summary(technical, transversal, rules),
        "resources": records(plant_resource_summary(instructors, rules)),
    }


def execute_level_plan(instructors, manual, rules, targets, planning_year, source_name, source_digest,
                       *, quarter_endings=None, ficha_import=None, transversal_continuity=None,
                       transversal_modules=None, continuing_transversal_hours=None, curriculum_catalog=None):
    from core.calendar_planner import apply_calendar, suggested_endings, validate_endings
    from core.transversal_capacity import apply_transversal_capacity

    manual = validate_profiles(manual, instructors)
    if manual.empty:
        raise ValueError("Agregue al menos una especialidad, nivel y jornada para planear.")
    endings = validate_endings(manual, suggested_endings(manual, ficha_import) if quarter_endings is None else quarter_endings)
    effective = manual.copy()
    # Las fichas que finalizan en T4 se reemplazan en T1 de la siguiente vigencia.
    effective["Fichas que terminan"] = endings[["Terminan T1", "Terminan T2", "Terminan T3"]].sum(axis=1)
    execution = _execute_unscheduled_plan(instructors, effective, rules, targets, planning_year, source_name, source_digest)
    distribution = pd.DataFrame(execution["distribution"])
    distribution["Fichas que terminan"] = manual["Fichas que terminan"]
    execution = apply_calendar(execution, instructors, distribution, endings, rules, modules=transversal_modules,
                               continuing_hours=continuing_transversal_hours, ficha_import=ficha_import,
                               curriculum_catalog=curriculum_catalog)
    if curriculum_catalog is not None:
        # En el flujo curricular se proyecta la dotación completa después de
        # planta. Los contratos del reporte no son capacidad para la vigencia.
        execution["staffing_basis"] = "plant_only_curricula_v1"
        return execution
    return apply_transversal_capacity(execution, instructors, rules, transversal_continuity)
