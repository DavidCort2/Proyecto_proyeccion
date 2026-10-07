"""Asignación de fichas completas y capacidad virtual por intervalos lectivos."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import math
import json
from pathlib import Path

from core.curriculum import name_key
from core.virtual_interval_allocation import allocate_interval

DAY = timedelta(days=1)


def workdays(start, end):
    """Días lunes-viernes del intervalo [start, end), sin calendario de festivos."""
    weeks, remaining = divmod(max(0, (end - start).days), 7)
    return weeks * 5 + sum((start.weekday() + n) % 7 < 5 for n in range(remaining))


def build_staffing(timeline, boundaries, plant, rules, year):
    policy = json.loads((Path(__file__).resolve().parents[1] / "config" / "virtual_staffing.json").read_text(encoding="utf-8"))
    support_key = ("Transversal", name_key(policy["technical_support_profile"]))
    labels = {row["key"]: row["Perfil"] for row in timeline}
    people = defaultdict(list)
    for person in plant:
        key = person["Tipo"], name_key(person["Perfil"])
        labels[key] = person["Perfil"]
        people[key].append({"Instructor": "Planta · " + person["Cédula"], "Nombre": person["Nombre completo"],
                            "Cédula": person["Cédula"], "Vinculación": "Planta"})
    for rows in people.values():
        rows.sort(key=lambda row: row["Cédula"])
    periods, staffing, technical_support, instructor_intervals = [], [], [], []
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
                    # Una atención transversal identifica ficha + competencia.
                    # Compartir perfil no elimina la carga de otra competencia.
                    unit_id = (ficha_id, row["Competencias"] if row["Tipo"] == "Transversal" else "")
                    task = tasks[row["key"]].setdefault(unit_id, {
                        "Ficha proyectada": ficha_id, "Programa": group["program"], "Cohorte": group["label"],
                        "Origen": group["kind"], "Fecha fin lectiva": (group["end"] - DAY).isoformat(), "Fases": set(), "Competencias": set()})
                    task["Fases"].add(row["Fase"])
                    task["Competencias"].update(row["Competencias"].split(", "))
        roster, allocated, contractors = allocate_interval(tasks, labels, people, rules, previous, support_key)
        plant_units, support_units, support_plant_units = defaultdict(set), defaultdict(set), defaultdict(set)
        previous = {}
        # Una sola capacidad mensual por persona, aunque imparta técnica y transversal.
        for identifier, person in roster.items():
            home = person["home_key"]
            assigned = allocated[identifier]
            if days:
                instructor_intervals.append({
                    "Instructor": identifier, "Nombre": person["Nombre"], "Cédula": person["Cédula"],
                    "Vinculación": person["Vinculación"], "Tipo": home[0], "Perfil": labels[home],
                    "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                    "Capacidad (h/sem)": person["capacity"], "Formación (h/sem)": person["used"],
                    "Disponible (h/sem)": max(0.0, person["capacity"] - person["used"])})
            previous[identifier] = set(assigned)
            supporting = [(key, unit) for key, unit in assigned if key != home]
            instructor = instructor_months.setdefault((start.month, identifier), {
                "Mes": start.month, **{k: person[k] for k in ("Instructor", "Nombre", "Cédula", "Vinculación")},
                "Tipo": home[0], "Perfil": labels[home], "Capacidad semanal": person["capacity"],
                "Máximo fichas completas de su perfil": math.floor(person["capacity"] / rules.weekly_hours_for(home[0])),
                "Pico fichas asignadas": 0, "Pico atenciones asignadas": 0,
                "Capacidad en horas": 0.0, "Horas asignadas": 0.0,
                "Horas técnicas asignadas": 0.0, "Horas transversales asignadas": 0.0})
            instructor["Capacidad en horas"] += days * person["capacity"] / 5
            instructor["Pico fichas asignadas"] = max(instructor["Pico fichas asignadas"], len({unit[0] for _, unit in assigned}))
            instructor["Pico atenciones asignadas"] = max(instructor["Pico atenciones asignadas"], len(assigned))
            for key, unit in assigned:
                task = tasks[key][unit]
                rate = rules.weekly_hours_for(key[0])
                hours = rate * days / 5
                is_support = key != home
                if person["Vinculación"] == "Planta":
                    plant_units[key].add(unit)
                if is_support:
                    support_units[key].add(unit)
                    if person["Vinculación"] == "Planta":
                        support_plant_units[key].add(unit)
                instructor["Horas asignadas"] += hours
                instructor["Horas técnicas asignadas" if key[0] == "Técnico" else "Horas transversales asignadas"] += hours
                ficha_id = task["Ficha proyectada"]
                ficha = ficha_months.setdefault((start.month, ficha_id), {
                    "Mes": start.month, **{k: v for k, v in task.items() if k not in {"Fases", "Competencias"}}, "Fases": set(),
                    "Horas técnicas": 0.0, "Horas transversales": 0.0})
                ficha["Fases"].update(task["Fases"])
                ficha["Horas técnicas" if key[0] == "Técnico" else "Horas transversales"] += hours
                assignment = assignments.setdefault((start.month, identifier, ficha_id, key), {
                    "Mes": start.month, "Instructor": identifier, "Nombre": person["Nombre"],
                    "Tipo": key[0], "Perfil": labels[key], "Tipo del instructor": home[0], "Perfil del instructor": labels[home],
                    "Vinculación": person["Vinculación"], "Apoyo técnico": is_support,
                    "Ficha proyectada": ficha_id, "Programa": task["Programa"], "Competencias": set(), "Horas asignadas": 0.0})
                assignment["Competencias"].update(task["Competencias"])
                assignment["Horas asignadas"] += hours
            if supporting:
                support_weekly = sum(rules.weekly_hours_for(key[0]) for key, _ in supporting)
                technical_support.append({"Instructor": identifier, "Nombre": person["Nombre"], "Vinculación": person["Vinculación"],
                    "Perfil técnico": labels[home], "Perfil apoyado": labels[support_key], "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                    "Atenciones transversales": len(supporting), "Horas técnicas (h/sem)": person["used"] - support_weekly,
                    "Apoyo transversal (h/sem)": support_weekly, "Capacidad (h/sem)": person["capacity"],
                    "Horas disponibles (h/sem)": person["capacity"] - person["used"], "Horas de apoyo en el intervalo": support_weekly * days / 5})

        totals = Counter()
        active_fichas = set()
        for key in sorted(labels):
            rate = rules.weekly_hours_for(key[0])
            hours_per_ficha = rate * days / 5
            demand = tasks[key]
            units_by_ficha = defaultdict(set)
            for unit, task in demand.items():
                units_by_ficha[task["Ficha proyectada"]].add(unit)
            active_fichas.update(units_by_ficha)
            count = len(demand)
            covered = len(plant_units[key])
            support = len(support_units[key])
            support_plant = len(support_plant_units[key])
            total_hours, covered_hours = count * hours_per_ficha, covered * hours_per_ficha
            staffing.append({"Tipo": key[0], "Perfil": labels[key], "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                             "Fichas activas": len(units_by_ficha),
                             "Fichas cubiertas por planta": sum(units <= plant_units[key] for units in units_by_ficha.values()),
                             "Atenciones activas": count, "Atenciones cubiertas por planta": covered,
                             "Atenciones cubiertas por apoyo técnico": support,
                             "Horas requeridas (h/sem)": count * rate, "Horas semanales por ficha": rate,
                             "Máximo fichas por planta": math.floor(rules.weekly_plant_direct_hours / rate),
                             "Máximo fichas por contratista": math.floor(rules.weekly_contractor_hours / rate),
                             "Capacidad planta (h/sem)": len(people[key]) * rules.weekly_plant_direct_hours,
                             "Apoyo técnico (h/sem)": support * rate,
                             "Apoyo técnico de planta (h/sem)": support_plant * rate,
                             "Apoyo técnico contratado (h/sem)": (support - support_plant) * rate,
                             "Horas requeridas": total_hours, "Horas cubiertas por planta": covered_hours,
                             "Horas a contratar": total_hours - covered_hours,
                             "Horas de contratistas propios del perfil": (count - covered - support + support_plant) * hours_per_ficha,
                             "Contratistas requeridos": len(contractors[key])})
            totals[key[0]] += len(contractors[key])
            totals["hours"] += total_hours
            totals["plant_hours"] += covered_hours
            totals["support_hours"] += support * hours_per_ficha
            for person in contractors[key]:
                spans[key, person["Cupo"]].append((start, end))
        periods.append({"Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(), "Mes": start.month,
                        "Trimestre": (start.month - 1) // 3 + 1, "Fichas activas": len(active_fichas),
                        "Contratistas técnicos": totals["Técnico"], "Contratistas transversales": totals["Transversal"],
                        "Contratistas requeridos": totals["Técnico"] + totals["Transversal"],
                        "Horas requeridas": totals["hours"], "Horas cubiertas por planta": totals["plant_hours"],
                        "Horas a contratar": totals["hours"] - totals["plant_hours"],
                        "Horas cubiertas por apoyo técnico": totals["support_hours"]})
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
                              "Capacidad (h/sem)": rules.weekly_contractor_hours,
                              "Máximo fichas simultáneas": math.floor(rules.weekly_contractor_hours / rules.weekly_hours_for(key[0])),
                              "Fin limitado por vigencia": end == date(year + 1, 1, 1)})
    peak = max(periods, key=lambda row: row["Contratistas requeridos"])

    def aggregate(field, value):
        rows = [row for row in periods if row[field] == value]
        high = max(rows, key=lambda row: row["Contratistas requeridos"])
        return {field: value, "Horas requeridas": math.fsum(row["Horas requeridas"] for row in rows),
                "Horas cubiertas por planta": math.fsum(row["Horas cubiertas por planta"] for row in rows),
                "Horas a contratar": math.fsum(row["Horas a contratar"] for row in rows),
                "Horas cubiertas por apoyo técnico": math.fsum(row["Horas cubiertas por apoyo técnico"] for row in rows),
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
        if row["Horas asignadas"] > row["Capacidad en horas"] + 1e-8:
            raise ValueError("La asignación mensual supera la capacidad del instructor.")
        row["Horas disponibles"] = max(0.0, row["Capacidad en horas"] - row["Horas asignadas"])
    for row in assignments.values():
        row["Competencias"] = ", ".join(sorted(row["Competencias"]))
    return {"periods": periods, "staffing": staffing, "contracts": contracts, "monthly": monthly, "quarterly": quarterly,
            "monthly_fichas": list(ficha_months.values()), "monthly_instructors": list(instructor_months.values()),
            "monthly_assignments": list(assignments.values()), "technical_support": technical_support,
            "instructor_intervals": instructor_intervals,
            "summary": {"pico_contratistas_total": peak["Contratistas requeridos"], "tecnicos_en_pico": peak["Contratistas técnicos"],
                        "transversales_en_pico": peak["Contratistas transversales"], "inicio_pico": peak["Inicio"], "fin_pico": peak["Fin"],
                        "trimestre_pico": peak["Trimestre"]}}
