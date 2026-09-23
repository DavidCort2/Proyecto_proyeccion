"""Demanda exacta por resultado, edad de formación, jornada y oferta de ingreso."""
from collections import defaultdict
import pandas as pd

from core.curriculum import curriculum_key, curriculum_lookup, duration_lookup, name_key
from core.ficha_projection import merge_ficha_specialties, project_ficha_carryover
from core.level_planner import MANUAL_COLUMNS, execute_level_plan
from core.planner import technical_specialty_catalog
from core.workflow import records


def prepare_ficha_import(frame, instructors, catalog, planning_year, source_name, source_digest,
                         report_year, report_quarter):
    detail, summary = project_ficha_carryover(
        frame, report_year, report_quarter, planning_year, group_by_profile=True,
        curriculum_durations=duration_lookup(catalog))
    curricula = curriculum_lookup(catalog)
    detail["Archivo malla"] = [curricula[curriculum_key(row["Especialidad"], row["Jornada"])]["source_name"]
                               for row in detail.to_dict("records")]
    summary = merge_ficha_specialties(summary, technical_specialty_catalog(instructors))
    return {"schema_version": 5, "source_name": source_name, "source_digest": source_digest,
            "report_year": report_year, "report_quarter": report_quarter, "planning_year": planning_year,
            "schedule_overrides": {}, "rows": records(frame), "detail": records(detail), "summary": records(summary)}


def curriculum_coverage(profiles, catalog):
    available = curriculum_lookup(catalog)
    rows = []
    for row in profiles.to_dict("records"):
        item = available.get(curriculum_key(row["Especialidad"], row["Jornada"]))
        rows.append({"Programa": row["Especialidad"], "Nivel": row["Nivel"], "Jornada": row["Jornada"],
                     "Estado": "Lista" if item else "Falta malla", "Trimestres": item["duration"] if item else None})
    return pd.DataFrame(rows)


def apply_curriculum_hours(calendar, catalog, imported, year, rules):
    curricula = curriculum_lookup(catalog)
    competencies = {item["key"]: item for item in catalog["competencies"]}
    ages = defaultdict(list)
    if imported:
        report_period = imported["report_year"] * 4 + imported["report_quarter"] - 1
        for row in imported["detail"]:
            if row["Pasa a la vigencia"]:
                key = (*curriculum_key(row["Especialidad"], row["Jornada de planeación"]), name_key(row["Nivel"]))
                ages[key].append((row["Ficha"], int(row["Trimestre actual"]) + year * 4 - report_period))
    missing = curriculum_coverage(calendar.loc[calendar["Fichas activas"] > 0].drop_duplicates(["Especialidad", "Nivel", "Jornada"]), catalog)
    if not missing.empty and (missing["Estado"] != "Lista").any():
        labels = [f"{row['Programa']} · {row['Jornada']}" for row in missing.to_dict("records") if row["Estado"] != "Lista"]
        raise ValueError("Faltan mallas curriculares: " + "; ".join(labels) + ". Cárguelas para calcular todas las horas.")
    result, audit = calendar.copy(), []
    for _, group in result.groupby(["Especialidad", "Nivel", "Jornada"], sort=False):
        first = group.iloc[0]
        key = curriculum_key(first["Especialidad"], first["Jornada"])
        curriculum = curricula.get(key)
        if not curriculum:
            continue  # Perfil sin fichas activas en toda la vigencia.
        starts = {int(row["Trimestre"]): int(row["Fichas nuevas"]) for row in group.to_dict("records")}
        continuing = ages[(*key, name_key(first["Nivel"]))]
        if len(continuing) != int(first["Continuaciones activas"]):
            raise ValueError(f"{first['Especialidad']}: las continuaciones deben coincidir con el reporte para identificar sus horas pendientes.")
        modules = defaultdict(list)
        for outcome in curriculum["outcomes"]:
            modules[outcome["quarter"]].append(outcome)
        for index, period in group.iterrows():
            q = int(period["Trimestre"])
            cohorts = [(f"Oferta T{start}", q - start + 1, count, True)
                       for start, count in starts.items() if count and 1 <= q - start + 1 <= curriculum["duration"]]
            cohorts += [(f"Ficha {ficha}", age + q - 1, 1, False)
                        for ficha, age in continuing if 1 <= age + q - 1 <= curriculum["duration"]]
            if sum(count for _, _, count, new in cohorts if not new) != int(period["Continuaciones activas"]):
                raise ValueError(f"{first['Especialidad']} · T{q}: las terminaciones no coinciden con la duración de la malla.")
            if sum(count for _, _, count, _ in cohorts) != int(period["Fichas activas"]):
                raise ValueError(f"{first['Especialidad']} · T{q}: las cohortes no coinciden con las fichas activas.")
            totals = {"técnicas": 0.0, "bilingüismo": 0.0, "integralidad": 0.0}
            new_hours = 0.0
            for label, age, count, new in cohorts:
                for outcome in modules[age]:
                    competence = competencies.get(outcome["competency_key"])
                    if competence is None:
                        raise ValueError("La malla contiene competencias sin registrar en el catálogo.")
                    area = competence["transversal_area"] if competence["transversal"] else "Técnica"
                    component = {"Técnica": "técnicas", "Bilingüismo": "bilingüismo", "Integralidad": "integralidad"}[area]
                    weekly = count * outcome["weekly_hours"]
                    totals[component] += weekly
                    if new:
                        new_hours += weekly * rules.weeks_per_quarter
                    audit.append({"Programa": first["Especialidad"], "Nivel": first["Nivel"], "Jornada": first["Jornada"],
                                  "Trimestre calendario": q, "Cohorte": label, "Trimestre de formación": age,
                                  "Fichas": count, "Competencia": competence["name"], "Área": area,
                                  "Resultado": outcome["result"], "Horas por ficha (h/sem)": outcome["weekly_hours"],
                                  "Horas requeridas (h/sem)": weekly, "Horas del trimestre": weekly * rules.weeks_per_quarter,
                                  "Archivo malla": curriculum["source_name"], "Hoja": outcome["source_sheet"], "Fila Excel": outcome["source_row"]})
            totals["totales"] = sum(totals.values())
            for component, hours in totals.items():
                result.loc[index, f"Horas {component} (h/sem)"] = hours
                result.loc[index, f"Horas {component} del trimestre"] = hours * rules.weeks_per_quarter
            result.loc[index, "Horas nuevas del trimestre"] = new_hours
    return result, audit


def execute_curriculum_plan(instructors, imported, catalog, rules, targets, year, source_name, source_digest):
    # Recalcula desde los registros originales: no acepta cantidades ni edades manuales guardadas.
    imported = prepare_ficha_import(pd.DataFrame(imported["rows"]), instructors, catalog, year,
                                    imported["source_name"], imported["source_digest"],
                                    imported["report_year"], imported["report_quarter"])
    manual = pd.DataFrame(imported["summary"], columns=MANUAL_COLUMNS)
    execution = execute_level_plan(instructors, manual, rules, targets, year, source_name, source_digest,
                                   ficha_import=imported, curriculum_catalog=catalog)
    execution["ficha_import"] = imported
    execution["planning_mode"] = "curricula_v5"
    execution["duration_basis"] = (
        "La duración de cada programa y jornada es el número de trimestres consecutivos de su malla. "
        "El trimestre del reporte se considera en curso: el fin se obtiene sumando los trimestres pendientes "
        "a ese período calendario. Cada ficha nueva comienza en el trimestre 1 de formación de su oferta. "
        "Las fechas de fin corresponden al último día del trimestre, no a una fecha diaria de certificación. "
        "No se sustituyen mallas ausentes por duraciones de referencia ni por otra jornada."
    )
    execution["contracting_basis"] = "La capacidad disponible incluye únicamente planta. La contratación se proyecta completa por perfil y por período según las horas de las mallas."
    from core.monthly_planner import apply_monthly_plan
    from core.contracting_periods import apply_contracting_periods
    return apply_contracting_periods(apply_monthly_plan(execution, instructors, rules), rules)
