"""Reparte el saldo de la meta presencial sin aumentar programas de menor presencia."""
from collections import Counter

from core.curriculum import curriculum_key
from core.planner import largest_remainder_allocation
from core.program_transitions import active_program, is_popular, is_retired, program_key


MODEL = "presencial_replacements_popularity_v1"
BASIS = (
    "Por cada nivel, las fichas que pasan se descuentan una sola vez: nuevas = "
    "redondear hacia arriba [máximo(meta − fichas que pasan × aprendices por ficha, 0) / aprendices por ficha]. "
    "Los programas de menor presencia reciben únicamente reemplazos de continuaciones que terminan durante "
    "la vigencia, desde la oferta siguiente a su terminación. Las salidas de T4 se reponen en la siguiente vigencia. "
    "Los reemplazos consumen ese mismo saldo; nunca se suman por fuera de la meta. "
    "El resto va a los programas con mayor presencia en cada nivel y a los declarados populares, incluidos "
    "los programas nuevos con demanda indicada. Se suman todas las jornadas y las versiones de un programa. "
    "Las ofertas siguen los porcentajes configurados, dando prioridad a las fechas de reemplazo. "
    "La presencia en el reporte es una referencia de popularidad, no una medición de solicitudes de matrícula."
)


def rebalance_presencial_offers(execution, imported, rules):
    """Conserva el presupuesto neto de 1.9.1 y modifica solo su reparto presencial."""
    if imported.get("input_mode") == "virtual_manual":
        raise ValueError("El reparto presencial no se aplica a la entrada virtual.")
    rows = execution["distribution"]
    transitions = imported.get("program_transitions", [])

    def profile(row):
        return curriculum_key(row["Especialidad"], row["Jornada"]), row["Nivel"]

    audit = {profile(row): row for row in execution["intake_allocation"]}
    census = {i: int(audit[profile(row)]["Fichas del reporte"]) for i, row in enumerate(rows)}
    family = {i: program_key(active_program(row["Especialidad"], transitions)) for i, row in enumerate(rows)}
    names = {family[i]: active_program(row["Especialidad"], transitions) for i, row in enumerate(rows)}
    starts = {i: [0] * 4 for i in range(len(rows))}
    replacements = {i: [0] * 4 for i in range(len(rows))}
    decisions = []

    for level in execution["levels"]:
        indices = [i for i, row in enumerate(rows) if row["Nivel"] == level["Nivel"]]
        groups = {key: [i for i in indices if family[i] == key] for key in sorted({family[i] for i in indices})}
        presence = {key: sum(census[i] for i in group) for key, group in groups.items()}
        largest = max(presence.values(), default=0)
        popular = {key for key in groups if presence[key] == largest or is_popular(names[key], transitions)}
        eligible = {key: sorted((i for i in group if not is_retired(rows[i]["Especialidad"], transitions)),
                                key=lambda i: curriculum_key(rows[i]["Especialidad"], rows[i]["Jornada"]))
                    for key, group in groups.items()}
        budget = int(level["Fichas nuevas necesarias"])
        original_budget = budget
        finishes = Counter()
        events = Counter()
        for item in imported["detail"]:
            if (item["Nivel"] != level["Nivel"] or not item["Pasa a la vigencia"]
                    or not item["Termina en la vigencia"]):
                continue
            key = program_key(active_program(item["Especialidad"], transitions))
            quarter = int(item["Trimestre fin estimado"])
            finishes[key, quarter] += 1
            if key not in popular and quarter < 4:
                # Índices 0–3: terminar en T1 libera el ingreso en el índice 1 (T2).
                events[key, item["Jornada de planeación"], quarter] += 1

        def spread(key, count, candidates=None):
            group = eligible[key] if candidates is None else candidates
            if count and not group:
                raise ValueError(f"Cargue la malla de {names[key]} para proyectar sus nuevos ingresos; el programa anterior ya no se oferta.")
            weights = [sum(census[j] for j in groups[key] if rows[j]["Jornada"] == rows[i]["Jornada"])
                       for i in group]
            if count and not sum(weights):
                if len(group) != 1:
                    raise ValueError(f"Revise las jornadas de la malla vigente de {names[key]}; no coinciden con el reporte.")
                weights = [presence[key]]
            return largest_remainder_allocation(count, group, weights)

        # Solo se reserva lo que cabe en el saldo neto, empezando por las salidas tempranas.
        for q in range(1, 4):
            required = {key: sum(count for (name, shift, release), count in events.items()
                                 if name == key and release == q) for key in groups if key not in popular}
            count = min(budget, sum(required.values()))
            assigned = largest_remainder_allocation(count, list(required), list(required.values()))
            for key, take in assigned.items():
                shifts = sorted({shift for name, shift, release in events if name == key and release == q})
                by_shift = largest_remainder_allocation(take, shifts, [events[key, shift, q] for shift in shifts])
                for shift, amount in by_shift.items():
                    candidates = [i for i in eligible[key] if rows[i]["Jornada"] == shift]
                    for i, number in spread(key, amount, candidates or None).items():
                        starts[i][q] += number
                        replacements[i][q] += number
            budget -= count

        popular_keys = sorted(popular)
        annual = largest_remainder_allocation(budget, popular_keys, [presence[key] for key in popular_keys])
        remaining_profiles = {key: spread(key, count) for key, count in annual.items()}
        expected = largest_remainder_allocation(original_budget, range(4), rules.intake_weights)
        # Las reservas tardías pueden superar el porcentaje de su oferta. El saldo
        # se reparte entre los cupos restantes; nunca se anticipa un reemplazo.
        offer_weights = [max(0, expected[q] - sum(replacements[i][q] for i in indices)) for q in range(4)]
        offers = largest_remainder_allocation(budget, range(4), offer_weights)
        for q, count in offers.items():
            assigned = largest_remainder_allocation(count, popular_keys, [annual[key] for key in popular_keys])
            for key, take in assigned.items():
                remaining = remaining_profiles[key]
                by_shift = largest_remainder_allocation(take, list(remaining), list(remaining.values()))
                for i, amount in by_shift.items():
                    starts[i][q] += amount
                    remaining[i] -= amount
                annual[key] -= take
        if sum(sum(starts[i]) for i in indices) != original_budget:
            raise ValueError("La distribución presencial no coincide con el saldo de fichas nuevas de la meta.")
        for key, group in groups.items():
            decisions.append({"Programa": names[key], "Nivel": level["Nivel"], "Fichas del reporte": presence[key],
                "Fichas que pasan": sum(int(rows[i]["Fichas que pasan"]) for i in group),
                "Terminan en la vigencia": sum(finishes[key, q] for q in range(1, 5)),
                "Terminan en T4 (reemplazo siguiente vigencia)": finishes[key, 4],
                "Reemplazos reservados": sum(sum(replacements[i]) for i in group),
                "Nuevas asignadas": sum(sum(starts[i]) for i in group),
                "Criterio": ("Popular · indicado por el usuario" if is_popular(names[key], transitions)
                             else "Popular · mayor presencia en su nivel" if key in popular else "Solo reemplazos")})
    for i, row in enumerate(rows):
        row["Fichas nuevas"] = sum(starts[i])
        audit[profile(row)]["Fichas nuevas asignadas"] = row["Fichas nuevas"]
    execution.update(intake_model=MODEL, intake_basis=BASIS,
                     presencial_offer_schedule=[starts[i] for i in range(len(rows))], intake_decisions=decisions)
    return execution
