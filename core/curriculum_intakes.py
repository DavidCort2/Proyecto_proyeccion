"""Fichas para cubrir la meta una sola vez, sin mínimos adicionales por programa."""
from collections import Counter
from dataclasses import asdict
import math
from numbers import Real

import pandas as pd

from core.curriculum import curriculum_key, name_key
from core.planner import fichas_from_target, largest_remainder_allocation, plant_resource_summary
from core.workflow import records


TARGET_BASIS = "total_learners_including_carryover"


def initialize_curricular_plan(instructors, manual, imported, targets, rules, year, source_name, source_digest):
    """Prepara fichas y recursos; las horas se calculan después desde las mallas."""
    distribution, levels, audit = project_curricular_intakes(manual, imported, targets, rules)
    continuing = int(distribution["Fichas que pasan"].sum())
    return {
        "planning_year": year, "source_name": source_name, "source_digest": source_digest,
        "targets_by_level": targets, "target_learners": sum(targets.values()),
        "continuing_fichas": continuing, "rules": asdict(rules),
        "distribution": records(distribution), "levels": records(levels),
        "center": {"meta_aprendices": sum(targets.values()),
                   "fichas_segun_meta": int(levels["Fichas según meta"].sum()),
                   "fichas_que_pasan": continuing,
                   "capacidad_planta_horas_semana": int(instructors["Es planta"].sum()) * rules.weekly_plant_direct_hours},
        "resources": records(plant_resource_summary(instructors, rules)),
        "target_basis": TARGET_BASIS, "intake_allocation": audit,
        "intake_basis": (
            "La meta incluye aprendices de las fichas que pasan y de las nuevas, contados una sola vez. "
            "Las nuevas cubren el saldo dividido entre aprendices por ficha, redondeado por nivel. "
            "Los cupos se distribuyen según la participación de cada programa y jornada en el reporte. "
            "La meta ingresada ya contiene el crecimiento deseado; no se añade otro 5 % ni reposiciones fuera de ella. "
            "Los aprendices que pasan se estiman con el tamaño configurado de ficha porque el reporte no incluye matrícula real."
        ),
    }


def project_curricular_intakes(manual, imported, targets, rules):
    if set(targets) != {"Técnico", "Tecnólogo"} or any(
        not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(value) or value < 0 or value % 1
        for value in targets.values()
    ):
        raise ValueError("Indique metas de aprendices enteras y no negativas para Técnico y Tecnólogo.")
    result = manual.copy()
    result["Fichas nuevas"] = 0
    census = Counter()
    for row in imported["detail"]:
        census[(*curriculum_key(row["Especialidad"], row["Jornada de planeación"]), name_key(row["Nivel"]))] += 1
    weights = {index: census[(*curriculum_key(row["Especialidad"], row["Jornada"]), name_key(row["Nivel"]))]
               for index, row in result.iterrows()}
    if any(weight <= 0 for weight in weights.values()) or sum(weights.values()) != len(imported["detail"]):
        raise ValueError("La distribución de programas debe corresponder a las fichas del reporte; no se pueden asignar proporciones predeterminadas.")
    levels, audit = [], []
    for level in ("Técnico", "Tecnólogo"):
        subset = result.loc[result["Nivel"] == level]
        target = int(targets[level])
        total_fichas = fichas_from_target(target, rules.learners_per_ficha)
        continuing = int(subset["Fichas que pasan"].sum())
        continuing_learners = continuing * rules.learners_per_ficha
        pending = max(0, target - continuing_learners)
        new = fichas_from_target(pending, rules.learners_per_ficha)
        if subset.empty and new:
            raise ValueError(f"Se necesita un programa de {level} en el reporte para distribuir la meta.")
        programs = list(subset["Especialidad"].drop_duplicates())
        program_weights = [sum(weights[i] for i in subset.index if subset.loc[i, "Especialidad"] == program) for program in programs]
        program_allocation = largest_remainder_allocation(new, programs, program_weights)
        for program, count in program_allocation.items():
            group = subset.loc[subset["Especialidad"] == program]
            shifts = largest_remainder_allocation(count, group.index, [weights[i] for i in group.index])
            for index, assigned in shifts.items():
                result.loc[index, "Fichas nuevas"] = assigned
                audit.append({"Especialidad": program, "Nivel": level, "Jornada": result.loc[index, "Jornada"],
                              "Fichas del reporte": weights[index], "Fichas que pasan": int(result.loc[index, "Fichas que pasan"]),
                              "Fichas nuevas asignadas": assigned})
        levels.append({"Nivel": level, "Meta de aprendices": target, "Fichas según meta": total_fichas,
                       "Fichas que pasan": continuing, "Aprendices que pasan (estimados)": continuing_learners,
                       "Aprendices pendientes de ingresar": pending, "Fichas nuevas necesarias": new,
                       "Fichas nuevas": new, "Fichas sobre la meta": max(0, continuing + new - total_fichas),
                       "Cupos nuevos": new * rules.learners_per_ficha,
                       "Cupos proyectados": (continuing + new) * rules.learners_per_ficha})
    return result, pd.DataFrame(levels), audit


def curricular_offer_schedule(distribution, rules):
    """Conserva simultáneamente el total anual por perfil y por oferta de cada nivel."""
    schedule = {index: [0] * 4 for index in distribution.index}
    for _, group in distribution.groupby("Nivel", sort=False):
        remaining = {index: int(group.loc[index, "Fichas nuevas"]) for index in group.index}
        offers = largest_remainder_allocation(sum(remaining.values()), range(4), rules.intake_weights)
        for q, total in offers.items():
            assigned = largest_remainder_allocation(total, group.index, [remaining[i] for i in group.index])
            for index, count in assigned.items():
                schedule[index][q] = count
                remaining[index] -= count
        if any(remaining.values()):
            raise ValueError("La distribución por ofertas no coincide con las fichas nuevas de la meta.")
    return schedule
