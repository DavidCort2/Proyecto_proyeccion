"""Competencias virtuales únicas; clasificación sugerida por el texto del archivo."""
from collections import defaultdict
import json
from pathlib import Path
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


def teaching_profile(activity):
    """Perfil aplicado al catálogo; el código es respaldo de catálogos sin adaptar."""
    return activity.get("teaching_profile") or activity["competency"]


def assign_teaching_profiles(activities):
    """Aplica perfiles por competencia, incluidos los exclusivos del centro."""
    policy = json.loads((Path(__file__).resolve().parents[1] / "config" / "virtual_staffing.json").read_text(encoding="utf-8"))
    references = json.loads((Path(__file__).resolve().parents[1] / "config" / "virtual_competency_references.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for row in activities:
        grouped[row["competency"]].append(row)
    for rows in grouped.values():
        required = policy.get("exclusive_competency_profiles", {}).get(rows[0]["competency"])
        manual = {teaching_profile(row) for row in rows if row.get("profile_source") == "manual"}
        if not required and len(manual) > 1:
            raise ValueError(f"La competencia {rows[0]['competency']} tiene varios perfiles manuales; unifique su perfil.")
        if required:
            # La nueva decisión del centro sustituye agrupaciones anteriores,
            # incluso manuales. No depende del programa ni del texto del resultado.
            profile, source = required, "center_policy"
        elif manual:
            profile, source = manual.pop(), "manual"
        else:
            reference = references.get(rows[0]["competency"], {})
            text = normalize_text(" ".join(row["activity"] for row in rows) + " " + reference.get("topic", ""))
            profile = policy["bilingual_profile"] if re.search(policy["bilingual_text_pattern"], text) else policy["general_profile"]
            source = "automatic"
        for row in rows:
            row.update(teaching_profile=profile, profile_source=source)
            if required:
                row.update(teaching_type="Transversal", classification_source="center_policy",
                           required_teaching_profile=required)
            else:
                row.pop("required_teaching_profile", None)
            if row["competency"] in references:
                row["profile_reference"] = references[row["competency"]]["source_url"]


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
        profiles = {teaching_profile(row) for _, row in pairs}
        if len(profiles) != 1:
            raise ValueError(f"La competencia {competency} tiene perfiles docentes distintos entre programas. Guarde un solo perfil.")
        result.append({"Competencia": competency, "Tipo": choices.pop(), "Perfil docente": profiles.pop(),
                       "Actividad de referencia": pairs[0][1]["activity"],
                       "Programas": " · ".join(sorted({name for name, _ in pairs})),
                       "Fases": " · ".join(sorted({row["phase"] for _, row in pairs}))})
    return result
