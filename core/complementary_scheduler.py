"""Cursos completos dentro de ventanas de capacidad, compartidas entre modalidades."""
from dataclasses import dataclass, field
from datetime import date, timedelta
import math

from core.complementary_inputs import COURSE_WEEKLY_HOURS, WORKDAYS_PER_WEEK

DAILY_HOURS = COURSE_WEEKLY_HOURS / WORKDAYS_PER_WEEK
EPSILON = 1e-7


def working_dates(year):
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    return [start + timedelta(days=i) for i in range((end - start).days)
            if (start + timedelta(days=i)).weekday() < WORKDAYS_PER_WEEK]


@dataclass
class Resource:
    identifier: str
    name: str
    kind: str
    modality: str
    profile: str
    capacity: list
    titled: list
    reserved: list = field(default_factory=list)
    assigned: dict = field(default_factory=dict)

    def __post_init__(self):
        self.reserved = [0.0] * len(self.capacity)
        self.assigned = {mode: [0.0] * len(self.capacity) for mode in ("Presencial", "Virtual")}

    def window(self, duration):
        count = math.ceil(duration / DAILY_HOURS - EPSILON)
        run = 0
        for index, (capacity, titled, reserved) in enumerate(zip(self.capacity, self.titled, self.reserved)):
            run = run + 1 if capacity - titled - reserved + EPSILON >= DAILY_HOURS else 0
            if run >= count:
                return index - count + 1, index + 1
        return None

    def allocate(self, modality, duration, start, end):
        remaining = duration
        for index in range(start, end):
            self.reserved[index] += DAILY_HOURS
            hours = min(DAILY_HOURS, remaining)
            self.assigned[modality][index] += hours
            remaining -= hours
        if abs(remaining) > EPSILON:
            raise ValueError("Las fechas del curso no cubren su duración en horas.")


def resources_from_sources(sources, dates):
    resources, occupied = {}, {}
    for source in sources:
        for row in source["intervals"]:
            identifier = row["Instructor ID"]
            person = resources.setdefault(identifier, Resource(identifier, row["Instructor"], "Apoyo de Titulada",
                row["Modalidad de origen"], row["Perfil"], [0.0] * len(dates), [0.0] * len(dates)))
            start, end = date.fromisoformat(row["Inicio"]), date.fromisoformat(row["Fin"])
            capacity, used = row["Capacidad (h/sem)"], row["Titulada (h/sem)"]
            if start > end or not all(math.isfinite(v) and v >= 0 for v in (capacity, used)) or used > capacity + EPSILON:
                raise ValueError("Revise los intervalos y la capacidad guardada de Titulada.")
            for index, day in enumerate(dates):
                if start <= day <= end:
                    if (identifier, index) in occupied:
                        raise ValueError("La disponibilidad de un contratista de Titulada está duplicada en la misma fecha.")
                    occupied[identifier, index] = True
                    person.capacity[index] = capacity / WORKDAYS_PER_WEEK
                    person.titled[index] = used / WORKDAYS_PER_WEEK
    return list(resources.values())


def place_courses(resources, pending, settings, dates, courses, required):
    """Primero los cursos de mayor duración; ante igualdad, equilibra cobertura."""
    while any(pending.values()):
        choices = []
        for modality, count in pending.items():
            if not count:
                continue
            duration = settings[modality]["duration_hours"]
            candidates = []
            for person in resources:
                if person.kind == "Planta de Complementaria" and person.modality != modality:
                    continue
                window = person.window(duration)
                if window:
                    # Ante el mismo inicio, aprovecha primero el contrato que termina antes.
                    last = max(i for i, capacity in enumerate(person.capacity) if capacity > 0)
                    candidates.append((window[0], last, person.identifier, window, person))
            if candidates:
                best = min(candidates, key=lambda value: value[:3])
                choices.append((-duration, (required[modality] - count) / required[modality], modality, best))
        if not choices:
            return
        _, _, modality, (_, _, _, (start, end), person) = min(choices, key=lambda value: value[:3])
        duration = settings[modality]["duration_hours"]
        person.allocate(modality, duration, start, end)
        number = required[modality] - pending[modality] + 1
        courses.append({"Curso": f"{modality} {number:04d}", "Modalidad": modality,
                        "Aprendices proyectados": settings[modality]["learners_per_course"],
                        "Duración (horas)": duration, "Duración equivalente (semanas)": duration / COURSE_WEEKLY_HOURS,
                        "Inicio": dates[start].isoformat(), "Fin": dates[end - 1].isoformat(),
                        "Instructor ID": person.identifier, "Instructor": person.name, "Tipo de recurso": person.kind,
                        "Modalidad de origen": person.modality, "Perfil de origen": person.profile})
        pending[modality] -= 1
