"""Competencias virtuales únicas; clasificación sugerida por el texto del archivo."""
from collections import defaultdict
import re

from core.excel_parser import normalize_text


TRANSVERSAL_TEXT = (
    r"\b(INGLES|INGLESA|ENGLISH|OFIMATICA|TIC|PSICOMOTRICES|EMPRENDEDOR\w*|EMPRENDIMIENTO)\b",
    r"PRINCIPIOS Y LEYES FISICAS|PROCEDIMIENTOS ARITMETICOS",
    r"COMPONENTES DE LA COMUNICACION|SITUACIONES COMUNICATIVAS",
    r"IMPACTO AMBIENTAL|ENFERMEDADES LABORALES|CONDICIONES PSICOMOTRICES",
    r"VALORES ETICOS|PRINCIPIOS ETICOS|DERECHOS (?:HUMANOS|FUNDAMENTALES)",
    r"INTERACCION SOCIAL ORAL|SITUACIONES COTIDIANAS Y LABORALES",
    r"CARACTERISTICAS SOCIOECONOMICAS",
)


def suggest_classifications(activities):
    grouped = defaultdict(list)
    for row in activities:
        grouped[row["competency"]].append(row)
    for rows in grouped.values():
        text = normalize_text(" ".join(row["activity"] for row in rows))
        choice = "Transversal" if any(re.search(pattern, text) for pattern in TRANSVERSAL_TEXT) else "Técnico"
        for row in rows:
            row["teaching_type"] = choice
            row["classification_source"] = "automatic"


def competency_rows(catalog):
    from core.virtual_schedule import lective_activities
    grouped = defaultdict(list)
    for item in catalog["schedules"]:
        for row in lective_activities(item):
            grouped[row["competency"]].append((item["program"], row))
    result = []
    for competency, pairs in sorted(grouped.items()):
        choices = {row["teaching_type"] for _, row in pairs}
        if len(choices) != 1:
            raise ValueError(f"La competencia {competency} tiene clasificaciones distintas entre programas. Guarde una sola clasificación.")
        result.append({"Competencia": competency, "Tipo": choices.pop(),
                       "Actividad de referencia": pairs[0][1]["activity"],
                       "Programas": " · ".join(sorted({name for name, _ in pairs})),
                       "Fases": " · ".join(sorted({row["phase"] for _, row in pairs}))})
    return result
