"""Planeación virtual a partir de fases relativas y atención diaria por ficha."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
import math
import re

import pandas as pd

from core.curriculum import name_key
from core.planner import fichas_from_target, largest_remainder_allocation
from core.virtual_planning import INSTRUCTOR_COLUMNS, whole_number
from core.virtual_schedule import duration_boundary, duration_sum, finite_hours, lective_activities, read_date, require_program_template
from core.virtual_staffing import build_staffing, workdays

DAY = timedelta(days=1)


@dataclass(frozen=True)
class VirtualRules:
    learners_per_ficha: int = 25
    weekly_plant_direct_hours: float = 32.0
    weekly_contractor_hours: float = 40.0
    intake_weights: tuple = (50, 25, 15, 10)
    daily_hours_per_ficha: float = 2.0

    @property
    def weekly_hours_per_ficha(self):
        return self.daily_hours_per_ficha * 5

    def validate(self):
        errors = []
        try:
            whole_number(self.learners_per_ficha, "Aprendices por ficha", 1)
            if finite_hours(self.daily_hours_per_ficha, "Horas diarias por ficha") <= 0:
                raise ValueError("Las horas diarias por ficha deben ser mayores que cero.")
            for label, value in [("Horas de planta", self.weekly_plant_direct_hours), ("Horas de contratista", self.weekly_contractor_hours)]:
                if finite_hours(value, label) < self.weekly_hours_per_ficha:
                    raise ValueError(f"{label}: deben permitir atender al menos una ficha completa ({self.weekly_hours_per_ficha:g} h/sem).")
            weights = [finite_hours(value, "Porcentaje de oferta") for value in self.intake_weights]
            if len(weights) != 4 or not math.isclose(sum(weights), 100, abs_tol=1e-9):
                raise ValueError("Las cuatro ofertas deben sumar 100 %.")
        except (ValueError, TypeError) as exc:
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
    cohorts = [{"Programa": row["Programa"], "Fichas que pasan": row["Fichas que pasan"],
                "Fecha fin lectiva": read_date(row["Fecha fin lectiva"], "Fin lectiva") if row.get("Fecha fin lectiva") else None}
               for row in saved.get("cohorts", [])]
    plant = []
    for row in saved.get("plant", []):
        if "Tipo" not in row:
            continue
        if "Nombre completo" in row:
            plant.append(row)
        else:
            # Los antiguos cupos no identificaban personas: requieren diligenciarse.
            plant.extend({"Nombre completo": "", "Cédula": "", "Tipo": row["Tipo"], "Perfil": row["Perfil"]}
                         for _ in range(whole_number(row.get("Instructores de planta", 0), "Planta")))
    return programs, cohorts, plant


def _plant(catalog, rows):
    options = staff_options(catalog)
    known = {(kind, name_key(profile)): profile for kind, profiles in options.items() for profile in profiles}
    counts, canonical, people, documents = Counter(), [], [], set()
    for row in rows:
        key = row.get("Tipo"), name_key(row.get("Perfil"))
        if key not in known:
            raise ValueError("Planta: seleccione Técnico con su programa o Transversal con una competencia clasificada en los cronogramas.")
        name = row.get("Nombre completo")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Planta: ingrese el nombre completo de cada instructor.")
        name = " ".join(name.split())
        document = row.get("Cédula")
        if not isinstance(document, (str, int)) or isinstance(document, bool):
            raise ValueError("Planta: ingrese la cédula como texto de dígitos, sin decimales.")
        document = re.sub(r"[\s.\-]", "", str(document))
        if not re.fullmatch(r"[0-9]+", document):
            raise ValueError("Planta: ingrese una cédula válida para cada instructor.")
        if document in documents:
            raise ValueError(f"Planta: la cédula {document} está repetida; una persona no puede aportar capacidad dos veces.")
        documents.add(document)
        counts[key] += 1
        canonical.append({"Nombre completo": name, "Cédula": document, "Tipo": key[0], "Perfil": known[key]})
        people.append({"Especialidad": known[key], "Área": "Técnica" if key[0] == "Técnico" else "Transversal",
                       "Nombre": name, "Documento": document, "Tipo Contrato": "Planta",
                       "Horas programadas actuales": 0.0, "Es planta": True})
    staff = pd.DataFrame(people, columns=INSTRUCTOR_COLUMNS).astype({"Es planta": bool, "Horas programadas actuales": float})
    staff.attrs["specialties"] = [{"Especialidad": p, "Área": "Técnica"} for p in options["Técnico"]]
    return counts, canonical, staff


def execute_virtual_schedule_plan(catalog, programs, cohorts, plant, rules, targets, year):
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
            require_program_template(available[key])
            selected[key] = entry
    if not selected:
        raise ValueError("Incluya al menos un programa con cronograma.")
    for key in selected:
        if any(row["teaching_type"] not in {"Técnico", "Transversal"} for row in lective_activities(available[key])):
            raise ValueError(f"{available[key]['program']}: clasifique todas las competencias lectivas.")
    _, canonical_plant, staff = _plant(catalog, plant)
    first, limit = date(year, 1, 1), date(year + 1, 1, 1)
    carryover, canonical_cohorts, groups, detail = Counter(), [], [], []

    def add_group(key, count, anchor, label, kind):
        item = available[key]
        duration, unit = item["lective_duration"], item["duration_unit"]
        shift = duration if kind == "Continuación" else 0
        boundary = lambda offset: duration_boundary(anchor, duration_sum(offset, -shift), unit)
        start, end = boundary(0), boundary(duration)
        group = {"key": key, "program": item["program"], "count": count, "start": start, "end": end,
                 "label": label, "kind": kind, "boundary": boundary}
        groups.append(group)
        phases = sorted({row["phase"] for row in lective_activities(item)
                         if boundary(row["start_offset"]) <= first < boundary(duration_sum(row["start_offset"], row["duration"]))})
        detail.append({"Programa": item["program"], "Cohorte": label, "Tipo": kind, "Fichas": count,
                       "Fecha inicio lectiva estimada": start.isoformat(), "Fecha fin lectiva": (end - DAY).isoformat(),
                       "Duración lectiva": duration, "Unidad": unit,
                       "Fases al iniciar la vigencia": ", ".join(phases) or ("Aún no inicia" if start > first else "Sin actividad programada")})
        return start, end

    for index, row in enumerate(cohorts, 1):
        key = name_key(row.get("Programa"))
        if key not in selected:
            raise ValueError("Las fichas que pasan deben pertenecer a un programa incluido.")
        count = whole_number(row.get("Fichas que pasan"), "Fichas que pasan", 1)
        finish = read_date(row.get("Fecha fin lectiva"), "Fecha fin lectiva de las fichas que pasan")
        if finish < first:
            raise ValueError(f"{available[key]['program']}: estas fichas terminaron antes de la vigencia.")
        start, end = add_group(key, count, finish + DAY, f"Continuación {index}", "Continuación")
        if start > first:
            raise ValueError("La fecha fin lectiva y la duración indican que estas fichas aún no han iniciado al comenzar la vigencia.")
        carryover[key] += count
        canonical_cohorts.append({"Programa": available[key]["program"], "Fichas que pasan": count, "Fecha fin lectiva": finish.isoformat()})
    dates = [date(year, month, 1) for month in (1, 4, 7, 10)]
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
                    add_group(key, count, dates[offer], f"Oferta {offer + 1} · {available[key]['program']}", "Nueva")
        levels.append({"Nivel": level, "Meta de aprendices": targets[level], "Fichas que pasan": continuing,
                       "Fichas nuevas": new, "Cupos proyectados": (continuing + new) * rules.learners_per_ficha})
    timeline = []
    boundaries = {date(year, month, 1) for month in range(1, 13)} | {limit}
    for group in groups:
        item = available[group["key"]]
        by_profile = defaultdict(list)
        for activity in lective_activities(item):
            profile = item["program"] if activity["teaching_type"] == "Técnico" else activity["competency"]
            by_profile[activity["block_id"], activity["teaching_type"], profile].append(activity)
        for (_, kind, profile), activities in by_profile.items():
            activity = activities[0]
            start = max(first, group["boundary"](activity["start_offset"]))
            end = min(limit, group["boundary"](duration_sum(activity["start_offset"], activity["duration"])))
            if start >= end:
                continue
            timeline.append({"key": (kind, name_key(profile)), "from": start, "until": end, "group": group,
                             "Programa": item["program"], "Cohorte": group["label"], "Fichas": group["count"],
                             "Fase": activity["phase"], "Competencias": ", ".join(sorted({a["competency"] for a in activities})),
                             "Tipo": kind, "Perfil": profile, "Inicio": start.isoformat(), "Fin": (end - DAY).isoformat(),
                             "Horas semanales por ficha": rules.weekly_hours_per_ficha,
                             "Horas instructor en vigencia": group["count"] * rules.daily_hours_per_ficha * workdays(start, end),
                             "Archivo": item["source_name"]})
            boundaries.update([start, end])
    results = build_staffing(timeline, boundaries, canonical_plant, rules, year)
    for row in results["quarterly"]:
        row["Fichas nuevas"] = sum(count for (key, offer), count in slots.items() if offer + 1 == row["Trimestre"])
    inputs = {"programs": canonical_programs, "cohorts": canonical_cohorts, "plant": canonical_plant,
              "offers": [value.isoformat() for value in dates]}
    execution = {"planning_mode": "virtual_schedule_v3", "workload_scope": "lectiva", "input_mode": "virtual_manual",
                 "training_type": "Titulada", "modality": "Virtual", "planning_year": year,
                 "targets_by_level": targets, "target_learners": sum(targets.values()), "rules": asdict(rules),
                 "source_name": "Cronogramas Excel, fases y atención diaria por ficha",
                 "source_digest": sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                 "virtual_inputs": inputs, "schedule_catalog": catalog, "levels": levels,
                 "distribution": [{"Especialidad": selected[key]["Programa"], "Nivel": selected[key]["Nivel"],
                                   "Fichas que pasan": carryover[key], "Fichas nuevas": quotas.get(key, 0)} for key in sorted(selected)],
                 "offers_by_program": [{"Programa": selected[key]["Programa"], "Nivel": selected[key]["Nivel"],
                                         **{f"Oferta {offer + 1}": slots.get((key, offer), 0) for offer in range(4)},
                                         "Total anual": quotas.get(key, 0)} for key in sorted(selected)],
                 "cohort_dates": detail, **results,
                 "activity_hours": [{k: v for k, v in row.items() if k not in {"key", "from", "until", "group"}} for row in timeline],
                 "center": {"fichas_que_pasan": sum(carryover.values()), "fichas_nuevas": sum(quotas.values()),
                            "demanda_total_horas_anuales": math.fsum(row["Horas requeridas"] for row in results["monthly"])},
                 "calculation_basis": (
                     "Se usan las duraciones relativas de cada bloque del Excel, no las fechas de la ficha de origen. "
                     "La fecha ingresada para continuaciones es el último día lectivo; las fases se reconstruyen hacia atrás desde el día siguiente. "
                     "Los meses completos siguen aniversarios de calendario y sus fracciones se prorratean en días, redondeando el límite hacia arriba. "
                     "Las ofertas se proyectan al inicio de cada trimestre (enero, abril, julio y octubre): son fechas indicativas, no un calendario oficial. "
                     "La meta incluye las fichas que pasan; el saldo dividido por aprendices por ficha, redondeado hacia arriba, determina las nuevas. "
                     f"Cada ficha requiere {rules.daily_hours_per_ficha:g} horas diarias de lunes a viernes ({rules.weekly_hours_per_ficha:g} semanales) "
                     "para el conjunto de competencias técnicas activas y la misma carga por cada competencia transversal activa. "
                     "Las actividades repetidas de una competencia no multiplican su carga. No se descuentan festivos porque no se cargó un calendario de festivos. "
                     "Se asignan fichas completas a cada instructor: la capacidad semanal dividida por la carga semanal por ficha, redondeada hacia abajo. "
                     "La planta cubre primero su perfil; los contratistas cubren las fichas restantes. Las horas libres se muestran y no se suman entre personas "
                     "para inventar cupos completos adicionales. Un técnico atiende su programa; un transversal comparte su competencia entre programas. "
                     "Los picos se calculan en cada cambio de fase y las fechas de contrato indican los intervalos de necesidad dentro de la vigencia. "
                     "La etapa productiva y antiguas horas manuales por actividad no intervienen en el cálculo."
                 )}
    return staff, execution
