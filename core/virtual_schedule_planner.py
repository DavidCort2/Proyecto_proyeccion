"""Planeación por fechas del cronograma y carga docente manual por actividad."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
import math

import pandas as pd

from core.curriculum import name_key
from core.planner import contractors_for_hours, fichas_from_target, largest_remainder_allocation
from core.virtual_planning import INSTRUCTOR_COLUMNS, whole_number
from core.virtual_schedule import finite_hours, lective_activities, read_date

DAY = timedelta(days=1)


@dataclass(frozen=True)
class VirtualRules:
    learners_per_ficha: int = 25
    weekly_plant_direct_hours: float = 32.0
    weekly_contractor_hours: float = 40.0
    intake_weights: tuple = (50, 25, 15, 10)

    def validate(self):
        errors = []
        try:
            whole_number(self.learners_per_ficha, "Aprendices por ficha", 1)
        except ValueError as exc:
            errors.append(str(exc))
        for label, value in [("Horas de planta", self.weekly_plant_direct_hours), ("Horas de contratista", self.weekly_contractor_hours)]:
            try:
                if finite_hours(value, label) == 0:
                    raise ValueError(f"{label}: debe ser mayor que cero.")
            except ValueError as exc:
                errors.append(str(exc))
        try:
            weights = [finite_hours(value, "Porcentaje de oferta") for value in self.intake_weights]
            if len(weights) != 4 or not math.isclose(sum(weights), 100, abs_tol=1e-9):
                raise ValueError("Las cuatro ofertas deben sumar 100 %.")
        except ValueError as exc:
            errors.append(str(exc))
        return errors


def staff_options(catalog):
    technical = sorted({item["program"] for item in catalog["schedules"]})
    transversal = sorted({row["competency"] for item in catalog["schedules"] for row in lective_activities(item)
                          if row["teaching_type"] == "Transversal"})
    return {"Técnico": technical, "Transversal": transversal}


def virtual_schedule_templates(catalog, previous):
    saved = previous.get("virtual_inputs", {})
    prior = {name_key(row["Programa"]): row for row in saved.get("programs", [])}
    programs = [{"Programa": item["program"], "Incluir": prior.get(item["program_key"], {}).get("Incluir", True),
                 "Nivel": prior.get(item["program_key"], {}).get("Nivel"),
                 "Peso de oferta": prior.get(item["program_key"], {}).get("Peso de oferta", 1)} for item in catalog["schedules"]]
    cohorts = saved.get("cohorts", [])
    # No convierte la antigua edad trimestral en una fecha inventada.
    cohorts = [{"Programa": row["Programa"], "Fichas que pasan": row["Fichas que pasan"],
                "Fecha inicio formación": read_date(row["Fecha inicio formación"], "Inicio") if row.get("Fecha inicio formación") else None}
               for row in cohorts]
    plant = saved.get("plant", [])
    plant = [row for row in plant if "Tipo" in row]
    return programs, cohorts, plant


def _plant(catalog, rows):
    options = staff_options(catalog)
    known = {(kind, name_key(profile)): profile for kind, profiles in options.items() for profile in profiles}
    counts, canonical, people = {}, [], []
    for row in rows:
        key = row.get("Tipo"), name_key(row.get("Perfil"))
        if key not in known:
            raise ValueError("Planta: seleccione Técnico con su programa o Transversal con una competencia clasificada en los cronogramas.")
        if key in counts:
            raise ValueError("No repita el mismo tipo y perfil de planta; sume sus instructores en una sola fila.")
        count = whole_number(row.get("Instructores de planta"), "Instructores de planta")
        counts[key] = count
        canonical.append({"Tipo": key[0], "Perfil": known[key], "Instructores de planta": count})
        for number in range(1, count + 1):
            people.append({"Especialidad": known[key], "Área": "Técnica" if key[0] == "Técnico" else "Transversal",
                           "Nombre": f"Cupo de planta | {key[0]} | {known[key]} | {number}", "Documento": "", "Tipo Contrato": "Planta",
                           "Horas programadas actuales": 0.0, "Es planta": True})
    staff = pd.DataFrame(people, columns=INSTRUCTOR_COLUMNS).astype({"Es planta": bool, "Horas programadas actuales": float})
    staff.attrs["specialties"] = [{"Especialidad": p, "Área": "Técnica"} for p in options["Técnico"]]
    return counts, canonical, staff


def execute_virtual_schedule_plan(catalog, programs, cohorts, plant, rules, targets, year, offers):
    errors = rules.validate()
    if errors:
        raise ValueError(" ".join(errors))
    year = whole_number(year, "Vigencia", 2000)
    if year > 2200:
        raise ValueError("La vigencia debe estar entre 2000 y 2200.")
    if set(targets) != {"Técnico", "Tecnólogo"}:
        raise ValueError("Indique las metas de Técnico y Tecnólogo.")
    targets = {level: whole_number(value, "Meta de " + level) for level, value in targets.items()}
    available = {item["program_key"]: item for item in catalog["schedules"]}
    selected, canonical_programs, seen = {}, [], set()
    for row in programs:
        key = name_key(row.get("Programa"))
        if key not in available or key in seen:
            raise ValueError("Seleccione programas con cronograma guardado, sin duplicados.")
        seen.add(key)
        if type(row.get("Incluir")) is not bool:
            raise ValueError("Indique qué programas incluir.")
        entry = {"Programa": available[key]["program"], "Incluir": row["Incluir"], "Nivel": row.get("Nivel"),
                 "Peso de oferta": whole_number(row.get("Peso de oferta"), "Peso de oferta", 1)}
        canonical_programs.append(entry)
        if row["Incluir"]:
            if entry["Nivel"] not in targets:
                raise ValueError(f"Seleccione Técnico o Tecnólogo para {entry['Programa']}.")
            selected[key] = entry
    if not selected:
        raise ValueError("Incluya al menos un programa con cronograma.")
    for key in selected:
        activities = lective_activities(available[key])
        pending = [row for row in activities if row["teaching_type"] not in {"Técnico", "Transversal"} or row["instructor_hours"] is None]
        if pending:
            raise ValueError(f"{available[key]['program']}: faltan tipo u horas de instructor en {len(pending)} actividades lectivas. Complételos y guárdelos en Cronogramas y competencias.")
        for row in activities:
            finite_hours(row["instructor_hours"], row["activity_code"])
    counts, canonical_plant, staff = _plant(catalog, plant)
    first, limit = date(year, 1, 1), date(year + 1, 1, 1)
    carryover, canonical_cohorts, groups, detail = Counter(), [], [], []

    def add_group(key, count, start, label, kind):
        item = available[key]
        reference = read_date(item["reference_start"], "Inicio cronograma")
        finish = start + (read_date(item["reference_end"], "Fin cronograma") - reference)
        groups.append({"key": key, "count": count, "start": start, "end": finish, "label": label, "kind": kind})
        phases = sorted({row["phase"] for row in item["activities"]
                         if start + (read_date(row["start"], "Inicio") - reference) <= first <= start + (read_date(row["end"], "Fin") - reference)})
        detail.append({"Programa": item["program"], "Cohorte": label, "Tipo": kind, "Fichas": count,
                       "Fecha inicio formación": start.isoformat(), "Fecha fin prevista": finish.isoformat(),
                       "Fases al iniciar la vigencia": ", ".join(phases) or ("Aún no inicia" if start > first else "Sin actividad programada")})
        return finish

    for index, row in enumerate(cohorts, 1):
        key = name_key(row.get("Programa"))
        if key not in selected:
            raise ValueError("Las fichas que pasan deben pertenecer a un programa incluido.")
        count = whole_number(row.get("Fichas que pasan"), "Fichas que pasan", 1)
        start = read_date(row.get("Fecha inicio formación"), "Fecha inicio formación de las fichas que pasan")
        if start > first:
            raise ValueError("Una ficha que pasa debe haber iniciado a más tardar al comenzar la vigencia.")
        finish = add_group(key, count, start, f"Continuación {index}", "Continuación")
        if finish < first:
            raise ValueError(f"{available[key]['program']}: estas fichas terminaron antes de la vigencia según el cronograma.")
        carryover[key] += count
        canonical_cohorts.append({"Programa": available[key]["program"], "Fichas que pasan": count, "Fecha inicio formación": start.isoformat()})
    if len(offers) != 4:
        raise ValueError("Configure las cuatro ofertas anuales.")
    dates = [read_date(value, f"Inicio de oferta {i + 1}") if value else None for i, value in enumerate(offers)]
    known_dates = [value for value in dates if value]
    if any(value.year != year for value in known_dates) or any(a >= b for a, b in zip(known_dates, known_dates[1:])):
        raise ValueError("Las fechas de las ofertas deben pertenecer a la vigencia y estar en orden creciente.")
    quotas, slots, levels = {}, {}, []
    for level in targets:
        keys = sorted(key for key in selected if selected[key]["Nivel"] == level)
        continuing = sum(carryover[key] for key in keys)
        new = fichas_from_target(max(0, targets[level] - continuing * rules.learners_per_ficha), rules.learners_per_ficha)
        if new and not keys:
            raise ValueError(f"Incluya al menos un programa de {level} para cubrir su meta.")
        assigned = largest_remainder_allocation(new, keys, [selected[key]["Peso de oferta"] for key in keys])
        quotas.update(assigned)
        pending = assigned.copy()
        offer_counts = largest_remainder_allocation(new, range(4), rules.intake_weights)
        for offer, total in offer_counts.items():
            by_program = largest_remainder_allocation(total, keys, [pending[key] for key in keys])
            for key, count in by_program.items():
                slots[key, offer] = count
                pending[key] -= count
                if count:
                    if dates[offer] is None:
                        raise ValueError(f"Indique la fecha de inicio de la oferta {offer + 1}.")
                    add_group(key, count, dates[offer], f"Oferta {offer + 1} · {available[key]['program']}", "Nueva")
        levels.append({"Nivel": level, "Meta de aprendices": targets[level], "Fichas que pasan": continuing,
                       "Fichas nuevas": new, "Cupos proyectados": (continuing + new) * rules.learners_per_ficha})
    timeline, boundaries = [], {first, limit}
    for month in range(2, 13):
        boundaries.add(date(year, month, 1))
    labels = {(kind, name_key(profile)): profile for kind, profiles in staff_options(catalog).items() for profile in profiles}
    for group in groups:
        item = available[group["key"]]
        offset = group["start"] - read_date(item["reference_start"], "Inicio")
        for activity in lective_activities(item):
            start = read_date(activity["start"], "Inicio") + offset
            end = read_date(activity["end"], "Fin") + offset + DAY
            clipped_start, clipped_end = max(start, first), min(end, limit)
            if clipped_start >= clipped_end:
                continue
            profile = item["program"] if activity["teaching_type"] == "Técnico" else activity["competency"]
            key = (activity["teaching_type"], name_key(profile))
            labels[key] = profile
            daily = activity["instructor_hours"] * group["count"] / (end - start).days
            timeline.append({"key": key, "from": clipped_start, "until": clipped_end, "daily": daily,
                             "Programa": item["program"], "Cohorte": group["label"], "Fichas": group["count"],
                             "Fase": activity["phase"], "Competencia": activity["competency"], "Actividad": activity["activity"],
                             "Tipo": key[0], "Perfil": profile, "Inicio": clipped_start.isoformat(), "Fin": (clipped_end - DAY).isoformat(),
                             "Horas instructor por ficha (actividad completa)": activity["instructor_hours"],
                             "Horas instructor en vigencia": daily * (clipped_end - clipped_start).days,
                             "Archivo": item["source_name"], "Hoja": activity["source_sheet"], "Fila": activity["source_row"]})
            boundaries.update([clipped_start, clipped_end])
    periods, resources, contract_days, per_month = [], [], defaultdict(list), defaultdict(list)
    ordered = sorted(boundaries)
    for start, end in zip(ordered, ordered[1:]):
        active = [row for row in timeline if row["from"] <= start < row["until"]]
        demand = defaultdict(float)
        for row in active:
            demand[row["key"]] += row["daily"] * 7
        totals = Counter()
        for key in sorted(labels):
            weekly = demand[key]
            capacity = counts.get(key, 0) * rules.weekly_plant_direct_hours
            deficit = max(0.0, weekly - capacity)
            contractors = contractors_for_hours(deficit, rules.weekly_contractor_hours)
            item = {"Tipo": key[0], "Perfil": labels[key], "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                    "Horas requeridas (h/sem)": weekly, "Capacidad planta (h/sem)": capacity,
                    "Contratistas requeridos": contractors, "Horas a contratar": deficit * (end - start).days / 7,
                    "Horas requeridas": weekly * (end - start).days / 7}
            resources.append(item)
            totals[key[0]] += contractors
            contract_days[key].append((start, end, contractors))
        required = sum(row["daily"] for row in active) * (end - start).days
        period = {"Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(), "Mes": start.month,
                  "Contratistas técnicos": totals["Técnico"], "Contratistas transversales": totals["Transversal"],
                  "Contratistas requeridos": sum(totals.values()), "Horas requeridas": required}
        periods.append(period)
        per_month[start.month].append(period)
    contracts = []
    for key, spans in sorted(contract_days.items()):
        for slot in range(1, max((row[2] for row in spans), default=0) + 1):
            beginning = None
            for start, end, required in [*spans, (limit, limit, 0)]:
                if required >= slot and beginning is None:
                    beginning = start
                elif required < slot and beginning is not None:
                    contracts.append({"Tipo": key[0], "Perfil": labels[key], "Cupo": slot,
                                      "Inicio": beginning.isoformat(), "Fin": (start - DAY).isoformat(),
                                      "Capacidad (h/sem)": rules.weekly_contractor_hours})
                    beginning = None
    peak = max(periods, key=lambda row: (row["Contratistas requeridos"], row["Horas requeridas"]))
    monthly = [{"Mes": month, "Horas requeridas": math.fsum(row["Horas requeridas"] for row in rows),
                "Pico simultáneo de contratistas": max(row["Contratistas requeridos"] for row in rows)} for month, rows in sorted(per_month.items())]
    inputs = {"programs": canonical_programs, "cohorts": canonical_cohorts, "plant": canonical_plant,
              "offers": [value.isoformat() if value else None for value in dates]}
    execution = {"planning_mode": "virtual_schedule_v2", "workload_scope": "lectiva", "input_mode": "virtual_manual", "training_type": "Titulada", "modality": "Virtual",
                 "planning_year": year, "targets_by_level": targets, "target_learners": sum(targets.values()), "rules": asdict(rules),
                 "source_name": "Cronogramas Excel y carga docente manual", "source_digest": sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                 "virtual_inputs": inputs, "schedule_catalog": catalog, "levels": levels,
                 "distribution": [{"Especialidad": selected[key]["Programa"], "Nivel": selected[key]["Nivel"],
                                   "Fichas que pasan": carryover[key], "Fichas nuevas": quotas.get(key, 0)} for key in sorted(selected)],
                 "offers_by_program": [{"Programa": selected[key]["Programa"], "Nivel": selected[key]["Nivel"],
                                         **{f"Oferta {offer + 1}": slots.get((key, offer), 0) for offer in range(4)},
                                         "Total anual": quotas.get(key, 0)} for key in sorted(selected)],
                 "cohort_dates": detail, "periods": periods, "monthly": monthly, "staffing": resources, "contracts": contracts,
                 "activity_hours": [{k: v for k, v in row.items() if k not in {"key", "from", "until", "daily"}} for row in timeline],
                 "center": {"fichas_que_pasan": sum(carryover.values()), "fichas_nuevas": sum(quotas.values()),
                            "demanda_total_horas_anuales": math.fsum(row["Horas requeridas"] for row in monthly)},
                 "summary": {"pico_contratistas_total": peak["Contratistas requeridos"], "tecnicos_en_pico": peak["Contratistas técnicos"],
                             "transversales_en_pico": peak["Contratistas transversales"], "inicio_pico": peak["Inicio"], "fin_pico": peak["Fin"]},
                 "calculation_basis": (
                     "La duración, las fases y los intervalos proceden del cronograma. Se trasladan conservando sus distancias en días "
                     "desde la fecha de inicio de cada cohorte. Las horas de instructor se ingresan por actividad y por ficha; "
                     "se distribuyen uniformemente dentro de su intervalo como promedio de planeación, no como horario diario de trabajo. "
                     "Se calcula la capacidad por perfil en cada cambio de actividad, sin diluir picos en promedios mensuales. "
                     "Los técnicos cubren su programa y los transversales su competencia entre programas. "
                     "Solo se calcula carga docente lectiva. La etapa productiva y su seguimiento quedan excluidos de horas, "
                     "cobertura de planta y contratación, incluso si tienen horas manuales guardadas. "
                     "Las fechas generales de formación y el conteo de fichas para las metas se conservan. "
                     "Las horas estimadas del Excel son una referencia y no se convierten automáticamente en horas docentes. "
                     "Las cuatro ofertas son ingresos independientes de las fases y pueden comenzar en las fechas configuradas."
                 )}
    return staff, execution
