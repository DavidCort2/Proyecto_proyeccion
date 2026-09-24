"""Fichas para cubrir la meta una sola vez, sin mínimos adicionales por programa."""
from collections import Counter, defaultdict
from dataclasses import asdict
import math
from numbers import Real

import pandas as pd

from core.curriculum import curriculum_key, name_key
from core.planner import fichas_from_target, largest_remainder_allocation, plant_resource_summary
from core.workflow import records


TARGET_BASIS = "total_learners_including_carryover"
OFFER_COLUMNS = [f"Oferta T{q}" for q in range(1, 5)]
OFFER_BASIS = (
    "La cantidad de fichas de cada programa en el reporte, sumando sus jornadas, se usa como referencia de popularidad; "
    "no representa solicitudes ni matrícula real. Dentro de cada nivel, los programas con menos fichas tienen prioridad "
    "en las primeras ofertas y los de mayor presencia cubren los cupos posteriores. "
    "Se conservan las fichas nuevas anuales de cada programa y jornada y los porcentajes de oferta configurados, "
    "redondeados a fichas completas. Por eso un programa puede aparecer en varias ofertas. "
    "En caso de igual presencia, se reparten los cupos proporcionalmente a las fichas nuevas pendientes de esos programas. "
    "Cada ingreso inicia en el trimestre 1 de su malla; desde allí se calculan sus horas y la contratación."
)


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
    if imported.get("input_mode") == "virtual_manual":
        manual_weights = {_offer_profile(row): row["Peso de oferta"] for row in imported["profile_weights"]}
        if len(manual_weights) != len(result) or set(manual_weights) != {_offer_profile(row) for row in result.to_dict("records")}:
            raise ValueError("Los pesos de oferta deben corresponder a los programas virtuales seleccionados.")
        weights = {index: manual_weights[_offer_profile(row)] for index, row in result.iterrows()}
        if any(isinstance(w, bool) or not isinstance(w, Real) or not math.isfinite(w) or w <= 0 or w % 1 for w in weights.values()):
            raise ValueError("Los pesos de oferta deben ser enteros positivos.")
    else:
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


def _offer_profile(row):
    return (*curriculum_key(row["Especialidad"], row["Jornada"]), name_key(row["Nivel"]))


def curricular_offer_schedule(distribution, rules, allocation):
    """Prioriza menor presencia sin cambiar las cuotas anuales ni los cupos por oferta."""
    census = {_offer_profile(row): int(row["Fichas del reporte"]) for row in allocation}
    profiles = {index: _offer_profile(row) for index, row in distribution.iterrows()}
    if (len(census) != len(allocation) or len(set(profiles.values())) != len(distribution)
            or set(census) != set(profiles.values()) or any(count <= 0 for count in census.values())):
        raise ValueError("Las ofertas necesitan la cantidad de fichas del reporte de cada programa, nivel y jornada.")
    schedule = {index: [0] * 4 for index in distribution.index}
    for _, group in distribution.groupby("Nivel", sort=False):
        remaining = {index: int(group.loc[index, "Fichas nuevas"]) for index in group.index}
        program_profiles = defaultdict(list)
        for index in group.index:
            program_profiles[profiles[index][0]].append(index)
        # Orden estable solo para desempatar residuos enteros, nunca para inferir popularidad.
        program_profiles = {program: sorted(indices, key=lambda i: profiles[i])
                            for program, indices in sorted(program_profiles.items())}
        presence = {program: sum(census[profiles[i]] for i in indices)
                    for program, indices in program_profiles.items()}
        offers = largest_remainder_allocation(sum(remaining.values()), range(4), rules.intake_weights)
        for q, total in offers.items():
            slots = total
            for count in sorted(set(presence.values())):
                programs = [program for program in program_profiles if presence[program] == count]
                pending = [sum(remaining[i] for i in program_profiles[program]) for program in programs]
                take = min(slots, sum(pending))
                if not take:
                    continue
                assigned = largest_remainder_allocation(take, programs, pending)
                for program, new in assigned.items():
                    indices = program_profiles[program]
                    shifts = largest_remainder_allocation(new, indices, [remaining[i] for i in indices])
                    for index, value in shifts.items():
                        schedule[index][q] += value
                        remaining[index] -= value
                slots -= take
                if not slots:
                    break
            if slots:
                raise ValueError("No hay suficientes fichas nuevas para completar los cupos de la oferta.")
        if any(remaining.values()):
            raise ValueError("La distribución por ofertas no coincide con las fichas nuevas de la meta.")
    return schedule


def curricular_offer_tables(calendar, allocation):
    """Resume el mismo calendario usado para calcular horas; no genera otra proyección."""
    counts = defaultdict(lambda: [0] * 4)
    for row in calendar.to_dict("records"):
        counts[_offer_profile(row)][int(row["Trimestre"]) - 1] += int(row["Fichas nuevas"])
    rows = []
    for row in allocation:
        offers = counts[_offer_profile(row)]
        if sum(offers) != row["Fichas nuevas asignadas"]:
            raise ValueError("El calendario de ofertas no coincide con la asignación anual del programa.")
        rows.append({"Programa": row["Especialidad"], "Nivel": row["Nivel"], "Jornada": row["Jornada"],
                     "Fichas del reporte": row["Fichas del reporte"],
                     **dict(zip(OFFER_COLUMNS, offers)), "Total anual": sum(offers)})
    profiles = pd.DataFrame(rows, columns=["Programa", "Nivel", "Jornada", "Fichas del reporte", *OFFER_COLUMNS, "Total anual"])
    programs = profiles.groupby(["Programa", "Nivel"], as_index=False)[["Fichas del reporte", *OFFER_COLUMNS, "Total anual"]].sum()
    programs = programs.sort_values(["Nivel", "Fichas del reporte", "Programa"])
    profiles = profiles.sort_values(["Nivel", "Programa", "Jornada"])
    return records(programs), records(profiles)
