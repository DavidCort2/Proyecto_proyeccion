"""Asignación de fichas completas y capacidad virtual por intervalos lectivos."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import math

from core.curriculum import name_key

DAY = timedelta(days=1)


def workdays(start, end):
    """Días lunes-viernes del intervalo [start, end), sin calendario de festivos."""
    weeks, remaining = divmod(max(0, (end - start).days), 7)
    return weeks * 5 + sum((start.weekday() + n) % 7 < 5 for n in range(remaining))


def build_staffing(timeline, boundaries, plant, rules, year):
    labels = {row["key"]: row["Perfil"] for row in timeline}
    people = defaultdict(list)
    for person in plant:
        key = person["Tipo"], name_key(person["Perfil"])
        labels[key] = person["Perfil"]
        people[key].append({"Instructor": "Planta · " + person["Cédula"], "Nombre": person["Nombre completo"],
                            "Cédula": person["Cédula"], "Vinculación": "Planta"})
    for rows in people.values():
        rows.sort(key=lambda row: row["Cédula"])
    plant_slots = math.floor(rules.weekly_plant_direct_hours / rules.weekly_hours_per_ficha)
    contract_slots = math.floor(rules.weekly_contractor_hours / rules.weekly_hours_per_ficha)
    periods, staffing = [], []
    spans = defaultdict(list)
    ficha_months, instructor_months, assignments = {}, {}, {}
    previous = {}
    ordered = sorted(boundaries)
    for start, end in zip(ordered, ordered[1:]):
        days = workdays(start, end)
        tasks = defaultdict(dict)
        for row in timeline:
            if row["from"] <= start < row["until"] and days:
                group = row["group"]
                for number in range(1, group["count"] + 1):
                    ficha_id = f"{group['program']} | {group['label']} | {number}"
                    task = tasks[row["key"]].setdefault(ficha_id, {
                        "Ficha proyectada": ficha_id, "Programa": group["program"], "Cohorte": group["label"],
                        "Origen": group["kind"], "Fecha fin lectiva": (group["end"] - DAY).isoformat(), "Fases": set()})
                    task["Fases"].add(row["Fase"])
        totals = Counter()
        active_fichas = set()
        for key in sorted(labels):
            demand = tasks[key]
            active_fichas.update(demand)
            count = len(demand)
            covered = min(count, len(people[key]) * plant_slots)
            remaining = count - covered
            contractors = math.ceil(remaining / contract_slots)
            weekly = count * rules.weekly_hours_per_ficha
            total_hours = count * rules.daily_hours_per_ficha * days
            covered_hours = covered * rules.daily_hours_per_ficha * days
            staffing.append({"Tipo": key[0], "Perfil": labels[key], "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                             "Fichas activas": count, "Fichas cubiertas por planta": covered,
                             "Horas requeridas (h/sem)": weekly,
                             "Capacidad planta (h/sem)": len(people[key]) * rules.weekly_plant_direct_hours,
                             "Horas requeridas": total_hours, "Horas cubiertas por planta": covered_hours,
                             "Horas a contratar": total_hours - covered_hours, "Contratistas requeridos": contractors})
            totals[key[0]] += contractors
            totals["hours"] += total_hours
            totals["plant_hours"] += covered_hours
            contractors_rows = [{"Instructor": f"Contrato · {key[0]} · {labels[key]} · {slot}", "Nombre": "Por contratar",
                                 "Cédula": "", "Vinculación": "Contratista", "Cupo": slot}
                                for slot in range(1, contractors + 1)]
            for person in contractors_rows:
                spans[key, person["Cupo"]].append((start, end))
            unassigned = set(demand)
            # Conserva las fichas de cada persona cuando siguen activas; planta tiene prioridad.
            for person in [*people[key], *contractors_rows]:
                identifier = person["Instructor"]
                is_plant = person["Vinculación"] == "Planta"
                slots = plant_slots if is_plant else contract_slots
                assigned = sorted(previous.get(identifier, set()) & unassigned)[:slots]
                assigned.extend(sorted(unassigned - set(assigned))[:slots - len(assigned)])
                unassigned.difference_update(assigned)
                previous[identifier] = set(assigned)
                row_key = start.month, identifier
                instructor = instructor_months.setdefault(row_key, {
                    "Mes": start.month, **{k: v for k, v in person.items() if k != "Cupo"}, "Tipo": key[0], "Perfil": labels[key],
                    "Capacidad semanal": rules.weekly_plant_direct_hours if is_plant else rules.weekly_contractor_hours,
                    "Máximo fichas simultáneas": slots, "Pico fichas asignadas": 0,
                    "Capacidad en horas": 0.0, "Horas asignadas": 0.0})
                instructor["Capacidad en horas"] += days * instructor["Capacidad semanal"] / 5
                instructor["Pico fichas asignadas"] = max(instructor["Pico fichas asignadas"], len(assigned))
                instructor["Horas asignadas"] += len(assigned) * rules.daily_hours_per_ficha * days
                for ficha_id in assigned:
                    task = demand[ficha_id]
                    ficha = ficha_months.setdefault((start.month, ficha_id), {
                        "Mes": start.month, **{k: v for k, v in task.items() if k != "Fases"}, "Fases": set(),
                        "Horas técnicas": 0.0, "Horas transversales": 0.0})
                    ficha["Fases"].update(task["Fases"])
                    ficha["Horas técnicas" if key[0] == "Técnico" else "Horas transversales"] += rules.daily_hours_per_ficha * days
                    assignment = assignments.setdefault((start.month, identifier, ficha_id), {
                        "Mes": start.month, "Instructor": identifier, "Nombre": person["Nombre"], "Tipo": key[0], "Perfil": labels[key],
                        "Ficha proyectada": ficha_id, "Programa": task["Programa"], "Horas asignadas": 0.0})
                    assignment["Horas asignadas"] += rules.daily_hours_per_ficha * days
            if unassigned:
                raise ValueError("La capacidad calculada no cubre todas las fichas del intervalo.")
        periods.append({"Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(), "Mes": start.month,
                        "Trimestre": (start.month - 1) // 3 + 1, "Fichas activas": len(active_fichas),
                        "Contratistas técnicos": totals["Técnico"], "Contratistas transversales": totals["Transversal"],
                        "Contratistas requeridos": totals["Técnico"] + totals["Transversal"],
                        "Horas requeridas": totals["hours"], "Horas cubiertas por planta": totals["plant_hours"],
                        "Horas a contratar": totals["hours"] - totals["plant_hours"]})
    contracts = []
    for (key, slot), intervals in sorted(spans.items()):
        merged = []
        for start, end in intervals:
            if merged and workdays(merged[-1][1], start) == 0:
                merged[-1] = merged[-1][0], end
            else:
                merged.append((start, end))
        for start, end in merged:
            contracts.append({"Instructor": f"Contrato · {key[0]} · {labels[key]} · {slot}", "Tipo": key[0], "Perfil": labels[key],
                              "Cupo": slot, "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                              "Capacidad (h/sem)": rules.weekly_contractor_hours, "Máximo fichas simultáneas": contract_slots,
                              "Fin limitado por vigencia": end == date(year + 1, 1, 1)})
    peak = max(periods, key=lambda row: row["Contratistas requeridos"])

    def aggregate(field, value):
        rows = [row for row in periods if row[field] == value]
        high = max(rows, key=lambda row: row["Contratistas requeridos"])
        return {field: value, "Horas requeridas": math.fsum(row["Horas requeridas"] for row in rows),
                "Horas cubiertas por planta": math.fsum(row["Horas cubiertas por planta"] for row in rows),
                "Horas a contratar": math.fsum(row["Horas a contratar"] for row in rows),
                "Pico simultáneo de contratistas": high["Contratistas requeridos"],
                "Técnicos en el pico": high["Contratistas técnicos"], "Transversales en el pico": high["Contratistas transversales"],
                "Pico de fichas activas": max(row["Fichas activas"] for row in rows)}

    monthly = [aggregate("Mes", month) for month in range(1, 13)]
    quarterly = [aggregate("Trimestre", quarter) for quarter in range(1, 5)]
    for row in quarterly:
        row["Cupos excedentes si se mantiene el pico anual"] = peak["Contratistas requeridos"] - row["Pico simultáneo de contratistas"]
    for row in ficha_months.values():
        row["Fases"] = " · ".join(sorted(row["Fases"]))
        row["Horas requeridas"] = row["Horas técnicas"] + row["Horas transversales"]
    for row in instructor_months.values():
        row["Horas disponibles"] = row["Capacidad en horas"] - row["Horas asignadas"]
    return {"periods": periods, "staffing": staffing, "contracts": contracts, "monthly": monthly, "quarterly": quarterly,
            "monthly_fichas": list(ficha_months.values()), "monthly_instructors": list(instructor_months.values()),
            "monthly_assignments": list(assignments.values()),
            "summary": {"pico_contratistas_total": peak["Contratistas requeridos"], "tecnicos_en_pico": peak["Contratistas técnicos"],
                        "transversales_en_pico": peak["Contratistas transversales"], "inicio_pico": peak["Inicio"], "fin_pico": peak["Fin"],
                        "trimestre_pico": peak["Trimestre"]}}
