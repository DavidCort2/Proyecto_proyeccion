"""Distribución manual presencial, aplicada antes de calcular horas y contratación."""
from collections import Counter
import math
from numbers import Real

from core.curriculum import curriculum_key, name_key
from core.curriculum_intakes import OFFER_COLUMNS
from core.planner import largest_remainder_allocation
from core.program_transitions import active_program, is_retired, program_key


MANUAL_BASIS = (
    "Los ingresos por programa y oferta provienen de la tabla editada por el usuario. "
    "Sus cantidades pueden cambiar el total anual y tienen prioridad sobre los porcentajes y el reparto automático. "
    "Las continuaciones se conservan y cuentan una sola vez para la meta. Se informa la diferencia entre los cupos "
    "programados y la meta de cada nivel. Las jornadas conservan su proporción del reporte combinado; "
    "cada nueva ficha inicia en el trimestre 1 de su propia malla en la oferta elegida."
)


def apply_manual_offers(execution, imported, manual_offers):
    if imported.get("input_mode") == "virtual_manual":
        raise ValueError("La edición de ofertas presenciales no se aplica a virtual.")
    if not isinstance(manual_offers, dict) or manual_offers.get("planning_year") != execution["planning_year"]:
        raise ValueError("La distribución manual pertenece a otra vigencia. Restaure el reparto automático para esta vigencia.")
    entries = manual_offers.get("programs")
    if not isinstance(entries, list):
        raise ValueError("Revise las filas de la distribución manual de ofertas.")
    decisions = execution["intake_decisions"]
    expected = {(program_key(row["Programa"]), name_key(row["Nivel"])): row for row in decisions}
    supplied = {}
    for row in entries:
        if not isinstance(row, dict) or not {"Programa", "Nivel", *OFFER_COLUMNS}.issubset(row):
            raise ValueError("Cada fila debe indicar programa, nivel y las cuatro ofertas.")
        key = program_key(row["Programa"]), name_key(row["Nivel"])
        if key in supplied or key not in expected:
            raise ValueError("La tabla manual contiene programas repetidos o que ya no corresponden al reporte. Restaure el reparto automático.")
        counts = []
        for column in OFFER_COLUMNS:
            value = row[column]
            if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
                    or value < 0 or value % 1):
                raise ValueError(f"{row['Programa']} · {column}: ingrese una cantidad entera no negativa, sin celdas vacías.")
            counts.append(int(value))
        supplied[key] = counts
    if supplied.keys() != expected.keys():
        raise ValueError("La distribución manual debe incluir todos los programas del reporte actual. Restaure el reparto automático.")

    transitions = imported.get("program_transitions", [])
    rows = execution["distribution"]
    audit = {(curriculum_key(row["Especialidad"], row["Jornada"]), name_key(row["Nivel"])): row
             for row in execution["intake_allocation"]}
    groups = {key: [i for i, row in enumerate(rows)
                   if (program_key(active_program(row["Especialidad"], transitions)), name_key(row["Nivel"])) == key]
              for key in expected}
    automatic = execution["presencial_offer_schedule"]
    schedule = [list(counts) for counts in automatic]
    normalized = []
    for key, decision in expected.items():
        indices, counts = groups[key], supplied[key]
        before = [sum(automatic[i][q] for i in indices) for q in range(4)]
        # No cambia jornadas ni horas de las filas que el usuario deja iguales.
        if counts != before:
            eligible = sorted((i for i in indices if not is_retired(rows[i]["Especialidad"], transitions)),
                              key=lambda i: curriculum_key(rows[i]["Especialidad"], rows[i]["Jornada"]))
            if sum(counts) and not eligible:
                raise ValueError(f"Cargue la malla vigente de {decision['Programa']} para proyectar nuevos ingresos.")
            if sum(counts) == sum(before):
                remaining = {i: sum(automatic[i]) for i in eligible}
            else:
                weights = [sum(audit[(curriculum_key(rows[j]["Especialidad"], rows[j]["Jornada"]), name_key(rows[j]["Nivel"]))]
                                   ["Fichas del reporte"] for j in indices if rows[j]["Jornada"] == rows[i]["Jornada"])
                           for i in eligible]
                if sum(counts) and not sum(weights):
                    if len(eligible) != 1:
                        raise ValueError(f"Revise las jornadas disponibles de {decision['Programa']}.")
                    weights = [decision["Fichas del reporte"]]
                remaining = largest_remainder_allocation(sum(counts), eligible, weights)
            for i in indices:
                schedule[i] = [0] * 4
            for q, count in enumerate(counts):
                assigned = largest_remainder_allocation(count, eligible, [remaining[i] for i in eligible])
                for i, amount in assigned.items():
                    schedule[i][q] = amount
                    remaining[i] -= amount
        finishes = Counter(int(row["Trimestre fin estimado"]) for row in imported["detail"]
            if row["Pasa a la vigencia"] and row["Termina en la vigencia"]
            and (program_key(active_program(row["Especialidad"], transitions)), name_key(row["Nivel"])) == key)
        pending = replaced = 0
        for q, count in enumerate(counts):
            pending += finishes[q]
            covered = min(pending, count)
            replaced += covered
            pending -= covered
        decision.update({"Criterio automático": decision["Criterio"], "Criterio": "Distribución manual",
                         "Reemplazos reservados": replaced, "Nuevas asignadas": sum(counts)})
        normalized.append({"Programa": decision["Programa"], "Nivel": decision["Nivel"], **dict(zip(OFFER_COLUMNS, counts))})
    for i, row in enumerate(rows):
        row["Fichas nuevas"] = sum(schedule[i])
        audit[(curriculum_key(row["Especialidad"], row["Jornada"]), name_key(row["Nivel"]))]["Fichas nuevas asignadas"] = row["Fichas nuevas"]
    execution.update(manual_offers={"planning_year": execution["planning_year"], "programs": normalized},
                     presencial_offer_schedule=schedule, intake_model="presencial_manual_offers_v1", intake_basis=MANUAL_BASIS)
    return execution
