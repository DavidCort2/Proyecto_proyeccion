"""Entradas y parámetros explícitos para Complementaria."""
import math
from numbers import Real

from core.complementary_sources import MODALITIES

COURSE_WEEKLY_HOURS = 10.0  # Intensidad indicada por el centro.
CONTRACTOR_WEEKLY_HOURS = 40.0  # Capacidad indicada por el centro.
PLANT_WEEKLY_HOURS = 32.0  # Horas de formación; no jornada laboral total.
WORKDAYS_PER_WEEK = 5


def default_settings():
    return {"target_learners": 0, "learners_per_course": 25, "duration_hours": None, "plant": []}


def number(value, label, *, minimum=0, integer=False):
    if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            or value < minimum or integer and value % 1):
        raise ValueError(f"{label}: ingrese un número {'entero ' if integer else ''}mayor o igual a {minimum}.")
    return int(value) if integer else float(value)


def normalize_inputs(inputs, year, source_plant=()):
    year = number(year, "Vigencia", minimum=2000, integer=True)
    if year > 2200 or set(inputs) != set(MODALITIES):
        raise ValueError("Revise la vigencia y las dos modalidades de Complementaria.")
    normalized, documents = {}, set()
    forbidden = {str(value).strip() for value in source_plant if str(value).strip()}
    for modality in MODALITIES:
        source = inputs[modality]
        target = number(source.get("target_learners"), "Meta de " + modality, integer=True)
        learners = number(source.get("learners_per_course"), "Aprendices por curso", minimum=1, integer=True)
        duration = source.get("duration_hours")
        if duration is not None or target:
            duration = number(duration, "Duración promedio en horas", minimum=0.01)
        plant = []
        for row in source.get("plant", []):
            raw_name = row.get("Nombre completo")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            raw_document = row.get("Cédula")
            if not isinstance(raw_document, str) or not raw_document.strip() or not name:
                raise ValueError("Ingrese nombre completo y cédula como texto para cada instructor de planta.")
            document = raw_document.strip()
            if document in documents:
                raise ValueError("Una persona de planta debe registrarse una sola vez entre ambas modalidades de Complementaria.")
            if document in forbidden:
                raise ValueError(f"{name}: ya pertenece a la planta de Titulada. Solo se reutilizan sus contratistas.")
            documents.add(document)
            weekly = number(row.get("Horas semanales", PLANT_WEEKLY_HOURS), "Horas semanales de planta", minimum=0.01)
            if weekly > PLANT_WEEKLY_HOURS:
                raise ValueError("La capacidad de formación de planta no puede superar 32 horas semanales.")
            plant.append({"Nombre completo": name, "Cédula": document, "Horas semanales": weekly})
        normalized[modality] = {"target_learners": target, "learners_per_course": learners,
                                "duration_hours": duration, "plant": sorted(plant, key=lambda r: r["Cédula"])}
    return normalized, year
