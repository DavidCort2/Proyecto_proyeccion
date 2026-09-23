"""Fichas para cubrir la meta una sola vez, sin mínimos adicionales por programa."""
from collections import Counter

import pandas as pd

from core.curriculum import curriculum_key, name_key
from core.planner import fichas_from_target, largest_remainder_allocation


TARGET_BASIS = "total_learners_including_carryover"


def project_curricular_intakes(manual, imported, targets, rules):
    result = manual.copy()
    result["Fichas nuevas"] = 0
    census = Counter()
    for row in imported["detail"]:
        census[(*curriculum_key(row["Especialidad"], row["Jornada de planeación"]), name_key(row["Nivel"]))] += 1
    weights = {index: census[(*curriculum_key(row["Especialidad"], row["Jornada"]), name_key(row["Nivel"]))]
               for index, row in result.iterrows()}
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
