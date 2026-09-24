"""Identidad de oferta y planta, independiente de la versión de la malla."""
import json
from pathlib import Path

import pandas as pd

from core.curriculum import curriculum_key, name_key


POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "presencial_programs.json"
TRANSITION_BASIS = (
    "Los programas reemplazados conservan únicamente sus fichas que pasan y la malla original de cada ficha. "
    "Su participación en el reporte se suma a la del programa vigente para calcular las nuevas, sin duplicar fichas. "
    "Los ingresos se asignan al programa vigente entre sus jornadas con malla disponible, según la participación "
    "de esas jornadas en el reporte combinado. Los dos nombres comparten una sola capacidad de planta y un solo "
    "perfil de contratación. La popularidad indicada expresamente tiene prioridad para las ofertas posteriores; "
    "solo cambia el orden de ingreso, no la cantidad anual asignada ni las horas de la malla."
)


def program_key(program):
    return curriculum_key(program, "Diurna")[0]


def load_presencial_transitions():
    data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    transitions = data["transitions"]
    previous = [program_key(row["previous"]) for row in transitions]
    current = [program_key(row["current"]) for row in transitions]
    if (len(set(previous)) != len(previous) or set(previous) & set(current)
            or any(not old or not new for old, new in zip(previous, current))
            or any(not isinstance(row["popular"], bool) for row in transitions)):
        raise ValueError("Revise los reemplazos y la popularidad de los programas presenciales configurados.")
    return transitions


def active_program(program, transitions):
    if not transitions:
        return program
    key = program_key(program)
    for row in transitions:
        if key in {program_key(row["previous"]), program_key(row["current"])}:
            return row["current"]
    return program


def is_retired(program, transitions):
    return any(program_key(program) == program_key(row["previous"]) for row in transitions)


def is_popular(program, transitions):
    return any(row["popular"] and program_key(program) == program_key(row["current"]) for row in transitions)


def prepare_transition_profiles(summary, detail, instructors, catalog):
    names = {program_key(name) for name in [*summary["Especialidad"], *instructors["Especialidad"]]}
    transitions = [row for row in load_presencial_transitions()
                   if names & {program_key(row["previous"]), program_key(row["current"])}]
    result = summary.to_dict("records")
    profiles = {(program_key(row["Especialidad"]), name_key(row["Nivel"]), row["Jornada"]) for row in result}
    added = []
    for transition in transitions:
        current = program_key(transition["current"])
        levels = {row["Nivel"] for row in result if program_key(active_program(row["Especialidad"], transitions)) == current}
        for curriculum in catalog["curricula"]:
            if program_key(curriculum["program"]) != current or curriculum["schedule"] == "Virtual":
                continue
            for level in sorted(levels):
                key = current, name_key(level), curriculum["schedule"]
                if key not in profiles:
                    profile = {"Especialidad": transition["current"], "Nivel": level, "Jornada": curriculum["schedule"]}
                    result.append({**profile, "Fichas que pasan": 0, "Fichas que terminan": 0})
                    added.append(profile)
                    profiles.add(key)
    if transitions:
        detail["Programa de planeación"] = detail["Especialidad"].map(lambda name: active_program(name, transitions))
    return pd.DataFrame(result, columns=summary.columns), transitions, added


def shared_plant(instructors, transitions):
    """Cada fila/persona aporta capacidad una sola vez; no altera el reporte original."""
    result = instructors.copy()
    technical = result["Área"].eq("Técnica")
    result.loc[technical, "Especialidad"] = result.loc[technical, "Especialidad"].map(lambda name: active_program(name, transitions))
    result.attrs["specialties"] = [
        {**row, "Especialidad": active_program(row["Especialidad"], transitions) if row["Área"] == "Técnica" else row["Especialidad"]}
        for row in instructors.attrs.get("specialties", [])
    ]
    return result


def transition_rows(transitions):
    return [{"Programa anterior · solo continuaciones": row["previous"],
             "Programa vigente · nuevas ofertas": row["current"],
             "Planta y contratación": "Compartidas entre ambos nombres",
             "Popularidad indicada": "Popular" if row["popular"] else "Según fichas del reporte",
             "Origen": row["source"]} for row in transitions]
