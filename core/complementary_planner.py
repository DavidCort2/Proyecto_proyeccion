"""Planeación conjunta: planta propia, horas libres de Titulada y saldo adicional."""
from copy import deepcopy
import math

from core.complementary_inputs import (normalize_inputs, COURSE_WEEKLY_HOURS, CONTRACTOR_WEEKLY_HOURS, WORKDAYS_PER_WEEK)
from core.complementary_reports import build_reports
from core.complementary_scheduler import Resource, working_dates, resources_from_sources, place_courses, DAILY_HOURS
from core.complementary_sources import MODALITIES

CALCULATION_BASIS = (
    "Cursos = redondear hacia arriba(meta de aprendices / aprendices por curso). La duración promedio en horas "
    "se usa como carga docente por curso; a 10 horas semanales equivale a duración / 10 semanas. "
    "Se propone una secuencia de cursos, priorizando planta propia y después la disponibilidad contractual guardada de Titulada "
    "presencial y virtual. Ambas modalidades de Complementaria comparten una única reserva de horas. "
    "La planta de Titulada está excluida. Un curso mantiene el mismo instructor y debe caber completo dentro de su disponibilidad; "
    "los contratos de Titulada no se prolongan ni se crean para generar apoyo. Se considera primero el curso de mayor duración "
    "y, ante igualdad, la modalidad con menor proporción cubierta. Si faltan cursos, se estima contratación adicional de 40 horas "
    "semanales compartida entre modalidades. No se suman sus picos independientes. "
    "Las fechas son indicativas: jornadas de 2 horas por curso de lunes a viernes, sin calendario de festivos o recesos. "
    "La última jornada se reserva completa, aunque solo se contabilizan las horas restantes del curso. "
    "La carga presencial se toma a su intensidad semanal; en virtual se respeta cada cambio de actividad, sin usar promedios mensuales. "
    "La estimación es de capacidad agregada: no acredita perfiles para cursos específicos ni resuelve horarios o desplazamientos."
)


def execute_complementary_plan(inputs, sources, year):
    settings, year = normalize_inputs(inputs, year, source_plant=[doc for source in sources for doc in source["plant_documents"]])
    dates = working_dates(year)
    required = {m: math.ceil(settings[m]["target_learners"] / settings[m]["learners_per_course"]) for m in MODALITIES}
    for modality in MODALITIES:
        if required[modality] and settings[modality]["duration_hours"] > len(dates) * DAILY_HOURS:
            raise ValueError(f"{modality}: con 10 horas semanales el curso no termina dentro de la vigencia. Revise la duración promedio.")
    plant = [Resource(f"Complementaria | Planta {row['Cédula']}", row["Nombre completo"], "Planta de Complementaria", modality,
                     "Complementaria", [row["Horas semanales"] / WORKDAYS_PER_WEEK] * len(dates), [0.0] * len(dates))
             for modality in MODALITIES for row in settings[modality]["plant"]]
    support = resources_from_sources(sources, dates)
    pending, courses = dict(required), []
    place_courses(plant, pending, settings, dates, courses, required)
    place_courses(support, pending, settings, dates, courses, required)
    uncovered = dict(pending)
    additional = []
    while any(pending.values()):
        slot = len(additional) + 1
        person = Resource(f"Complementaria | Contrato {slot}", f"Contratista adicional {slot}", "Contratista adicional",
            "Complementaria compartida", "Complementaria", [CONTRACTOR_WEEKLY_HOURS / WORKDAYS_PER_WEEK] * len(dates), [0.0] * len(dates))
        before = sum(pending.values())
        place_courses([person], pending, settings, dates, courses, required)
        if sum(pending.values()) == before:
            raise ValueError("No fue posible programar cursos completos dentro de la vigencia.")
        additional.append(person)
    resources = plant + support + additional
    reports = build_reports(settings, required, courses, resources, dates, uncovered)
    return {"planning_mode": "complementaria_v1", "planning_year": year, "inputs": settings,
            "sources": [deepcopy(source["metadata"]) for source in sources],
            "source_availability": [deepcopy(row) for source in sources for row in source["intervals"]],
            "rules": {"weekly_hours_per_course": COURSE_WEEKLY_HOURS, "weekly_contractor_hours": CONTRACTOR_WEEKLY_HOURS,
                      "workdays_per_week": WORKDAYS_PER_WEEK}, "calculation_basis": CALCULATION_BASIS, **reports}
