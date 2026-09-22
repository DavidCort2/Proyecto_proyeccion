"""Demanda mensual por ficha y reparto de capacidad compartida por perfil."""
from collections import defaultdict
import math

from core.curriculum import curriculum_key
from core.planner import contractors_for_hours

MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
COMPONENTS = {"Técnica": "Técnicas", "Bilingüismo": "Bilingüismo", "Integralidad": "Integralidad"}
MONTHLY_BASIS = (
    "Las semanas efectivas de cada trimestre se distribuyen por igual entre sus tres meses. "
    "Los ingresos se consideran al inicio del trimestre y las salidas al final. "
    "La asignación es una propuesta de carga por perfil, no un horario de clases."
)


def _pool(area, specialty):
    return area, curriculum_key(specialty, "Diurna")[0] if area == "Técnica" else area


def monthly_fichas(execution, rules):
    """Una fila por ficha/mes; las nuevas usan identificadores de proyección."""
    cohorts = {}
    for row in execution["curriculum_hours"]:
        key = tuple(row[c] for c in ("Programa", "Nivel", "Jornada", "Cohorte", "Trimestre calendario"))
        if key not in cohorts:
            cohorts[key] = {"sample": row, "hours": dict.fromkeys(COMPONENTS, 0.0)}
        cohorts[key]["hours"][row["Área"]] += row["Horas por ficha (h/sem)"]
    result = []
    weeks = rules.weeks_per_quarter / 3.0
    for entry in cohorts.values():
        row, hours = entry["sample"], entry["hours"]
        quarter = row["Trimestre calendario"]
        new = row["Cohorte"].startswith("Oferta T")
        for number in range(1, row["Fichas"] + 1):
            ficha = (f"Nueva {execution['planning_year']} | {row['Programa']} | {row['Nivel']} | {row['Jornada']} | {row['Cohorte']} | {number}"
                     if new else row["Cohorte"].removeprefix("Ficha "))
            for month in range(quarter * 3 - 2, quarter * 3 + 1):
                item = {"Programa": row["Programa"], "Nivel": row["Nivel"], "Jornada": row["Jornada"],
                        "Ficha": ficha, "Tipo ficha": "Nueva proyectada" if new else "Continuación",
                        "Cohorte": row["Cohorte"], "Trimestre de formación": row["Trimestre de formación"],
                        "Trimestre": quarter, "Mes número": month, "Mes": MONTHS[month - 1], "Semanas efectivas": weeks}
                for area, label in COMPONENTS.items():
                    item[f"{label} (h/sem)"] = hours[area]
                    item[f"{label} (h/mes)"] = hours[area] * weeks
                item["Horas requeridas (h/sem)"] = sum(hours.values())
                item["Horas requeridas (h/mes)"] = sum(hours.values()) * weeks
                result.append(item)
    return sorted(result, key=lambda row: (row["Mes número"], row["Programa"], row["Ficha"]))


def apply_monthly_plan(execution, instructors, rules):
    fichas = monthly_fichas(execution, rules)
    weeks = rules.weeks_per_quarter / 3.0
    staff, labels, demands = defaultdict(list), {}, defaultdict(list)
    documents = set()
    for person in instructors.to_dict("records"):
        if not person["Es planta"]:
            continue
        document = str(person["Documento"]).strip()
        if document and document in documents:
            raise ValueError("Hay documentos de instructores repetidos; no se puede contar su capacidad dos veces.")
        documents.add(document)
        key = _pool(person["Área"], person["Especialidad"])
        labels.setdefault(key, person["Especialidad"] if person["Área"] == "Técnica" else person["Área"])
        staff[key].append({"id": f"Planta {document or person['Nombre']}", "name": person["Nombre"], "document": document,
                           "type": "Planta", "weekly": rules.weekly_plant_direct_hours})
    for row in execution["distribution"]:
        key = _pool("Técnica", row["Especialidad"])
        labels.setdefault(key, row["Especialidad"])
    for area in ("Bilingüismo", "Integralidad"):
        labels.setdefault(_pool(area, area), area)
    for row in fichas:
        for area, label in COMPONENTS.items():
            hours = row[f"{label} (h/mes)"]
            if hours > 0:
                key = _pool(area, row["Programa"])
                labels.setdefault(key, row["Programa"] if area == "Técnica" else area)
                demands[(row["Mes número"], key)].append((row, hours))

    staffing, individual, assignments, summary = [], [], [], []
    for month in range(1, 13):
        month_staffing = []
        for key, profile in sorted(labels.items()):
            area = key[0]
            people = sorted(staff[key], key=lambda p: (p["type"] != "Planta", p["document"], p["id"]))
            plant = sum(p["type"] == "Planta" for p in people)
            work = demands[(month, key)]
            required = math.fsum(hours for _, hours in work)
            plant_capacity = plant * rules.weekly_plant_direct_hours * weeks
            contractor_capacity = rules.weekly_contractor_hours * weeks
            deficit = max(0.0, required - plant_capacity)
            contractors = contractors_for_hours(deficit, contractor_capacity)
            item = {"Mes número": month, "Mes": MONTHS[month - 1], "Trimestre": (month - 1) // 3 + 1,
                    "Área": area, "Perfil": profile, "Fichas atendidas": len(work),
                    "Horas requeridas (h/sem)": required / weeks, "Horas requeridas (h/mes)": required,
                    "Instructores planta": plant,
                    "Capacidad por planta (h/mes)": rules.weekly_plant_direct_hours * weeks,
                    "Capacidad por contratista (h/mes)": contractor_capacity,
                    "Capacidad planta (h/mes)": plant_capacity,
                    "Horas a contratar (h/mes)": deficit, "Horas libres de planta (h/mes)": max(0.0, plant_capacity - required),
                    "Contratistas requeridos": contractors,
                    "Dedicación contractual equivalente": deficit / contractor_capacity}
            staffing.append(item)
            month_staffing.append(item)
            people += [{"id": f"Contrato | {area} | {profile} | {number}", "name": f"Contratista proyectado {number}",
                        "document": "", "type": "Contratista proyectado", "weekly": rules.weekly_contractor_hours}
                       for number in range(1, contractors + 1)]
            # Se reparte la capacidad, no un instructor completo por cada ficha.
            position = 0
            used = [0.0] * len(people)
            attended = [set() for _ in people]
            for row, required_hours in work:
                remaining = required_hours
                while remaining > 1e-8:
                    if position >= len(people):
                        raise ValueError(f"La asignación de {profile} en {MONTHS[month - 1]} no cubre todas las horas.")
                    person = people[position]
                    free = person["weekly"] * weeks - used[position]
                    hours = min(remaining, free)
                    if hours > 1e-8:
                        used[position] += hours
                        attended[position].add(row["Ficha"])
                        assignments.append({"Mes número": month, "Mes": MONTHS[month - 1], "Área": area, "Perfil": profile,
                                            "Instructor ID": person["id"], "Instructor": person["name"], "Documento": person["document"],
                                            "Tipo": person["type"], "Ficha": row["Ficha"], "Programa": row["Programa"],
                                            "Jornada": row["Jornada"], "Horas asignadas (h/mes)": hours,
                                            "Horas asignadas (h/sem)": hours / weeks})
                    remaining -= hours
                    if free - hours < 1e-8:
                        position += 1
            for position, person in enumerate(people):
                capacity = person["weekly"] * weeks
                individual.append({"Mes número": month, "Mes": MONTHS[month - 1], "Área": area, "Perfil": profile,
                                   "Instructor ID": person["id"], "Instructor": person["name"], "Documento": person["document"], "Tipo": person["type"],
                                   "Capacidad (h/sem)": person["weekly"], "Capacidad (h/mes)": capacity,
                                   "Horas asignadas (h/mes)": used[position], "Horas libres (h/mes)": max(0.0, capacity - used[position]),
                                   "Fichas atendidas": len(attended[position])})
        active = [row for row in fichas if row["Mes número"] == month]
        summary.append({"Mes número": month, "Mes": MONTHS[month - 1], "Trimestre": (month - 1) // 3 + 1,
                        "Fichas activas": len(active), "Horas requeridas": math.fsum(row["Horas requeridas (h/mes)"] for row in active),
                        "Horas técnicas": math.fsum(row["Técnicas (h/mes)"] for row in active),
                        "Bilingüismo": math.fsum(row["Bilingüismo (h/mes)"] for row in active),
                        "Integralidad": math.fsum(row["Integralidad (h/mes)"] for row in active),
                        "Contratistas técnicos": sum(row["Contratistas requeridos"] for row in month_staffing if row["Área"] == "Técnica"),
                        "Contratistas transversales": sum(row["Contratistas requeridos"] for row in month_staffing if row["Área"] != "Técnica"),
                        "Contratistas requeridos": sum(row["Contratistas requeridos"] for row in month_staffing),
                        "Horas a contratar": math.fsum(row["Horas a contratar (h/mes)"] for row in month_staffing)})
    if not math.isclose(math.fsum(row["Horas requeridas"] for row in summary), execution["center"]["demanda_total_horas_anuales"], abs_tol=1e-6):
        raise ValueError("Las horas mensuales no coinciden con la demanda anual; revise las cohortes.")
    for quarter in execution["quarterly"]:
        months = [row for row in summary if row["Trimestre"] == quarter["Trimestre"]]
        if (not math.isclose(math.fsum(row["Horas requeridas"] for row in months), quarter["Horas requeridas"], abs_tol=1e-6)
                or any(row["Contratistas requeridos"] != quarter["contratistas_totales"]
                       or row["Fichas activas"] != quarter["Fichas activas"] for row in months)):
            raise ValueError(f"Las fichas, horas o contratistas mensuales no coinciden con T{quarter['Trimestre']}.")
    execution.update(monthly=summary, monthly_fichas=fichas, monthly_staffing=staffing,
                     monthly_instructors=individual, monthly_assignments=assignments, monthly_basis=MONTHLY_BASIS)
    return execution
