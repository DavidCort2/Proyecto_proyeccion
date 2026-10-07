"""Resumen de cobertura, contratos y conciliación de capacidad compartida."""
from collections import Counter
import math

from core.complementary_inputs import WORKDAYS_PER_WEEK
from core.complementary_sources import MODALITIES


def build_reports(settings, required, courses, resources, dates, uncovered):
    monthly, workload, intervals, contracts = [], [], [], []
    daily_support = [set() for _ in dates]
    daily_contracts = [set() for _ in dates]
    for person in resources:
        active = [i for i in range(len(dates)) if sum(person.assigned[m][i] for m in MODALITIES) > 1e-8]
        if person.kind == "Contratista adicional":
            # Su capacidad se contrata únicamente en los días que requiere el escenario.
            for i in range(len(dates)):
                if i not in active:
                    person.capacity[i] = 0.0
            spans = []
            for index in active:
                if spans and spans[-1][1] == index:
                    spans[-1] = spans[-1][0], index + 1
                else:
                    spans.append((index, index + 1))
            for start, end in spans:
                contracts.append({"Instructor ID": person.identifier, "Instructor": person.name,
                    "Inicio": dates[start].isoformat(), "Fin": dates[end - 1].isoformat(),
                    "Capacidad (h/sem)": person.capacity[start] * WORKDAYS_PER_WEEK,
                    "Modalidades atendidas": ", ".join(m for m in MODALITIES if any(person.assigned[m][start:end]))})
        last_signature = None
        for index, day in enumerate(dates):
            capacity, titled, reserved = person.capacity[index], person.titled[index], person.reserved[index]
            presencial, virtual = (person.assigned[m][index] for m in MODALITIES)
            if titled + reserved > capacity + 1e-7 or presencial + virtual > reserved + 1e-7:
                raise ValueError("Se está asignando dos veces la capacidad de un instructor.")
            if not capacity:
                last_signature = None
                continue
            signature = (capacity, titled, reserved, presencial, virtual, day.month)
            other = max(0.0, capacity - presencial - virtual) if person.kind == "Planta de Complementaria" else 0.0
            if signature == last_signature:
                intervals[-1]["Fin"] = day.isoformat()
                intervals[-1]["Días hábiles"] += 1
            else:
                intervals.append({"Instructor ID": person.identifier, "Instructor": person.name, "Tipo de recurso": person.kind,
                    "Modalidad de origen": person.modality, "Perfil de origen": person.profile,
                    "Inicio": day.isoformat(), "Fin": day.isoformat(), "Días hábiles": 1,
                    "Capacidad (h/sem)": capacity * WORKDAYS_PER_WEEK, "Titulada (h/sem)": titled * WORKDAYS_PER_WEEK,
                    "Complementaria presencial (h/sem)": presencial * WORKDAYS_PER_WEEK,
                    "Complementaria virtual (h/sem)": virtual * WORKDAYS_PER_WEEK,
                    "Reserva complementaria (h/sem)": reserved * WORKDAYS_PER_WEEK,
                    "Capacidad sin reservar (h/sem)": max(0.0, capacity - titled - reserved) * WORKDAYS_PER_WEEK,
                    "Otras actividades de planta (h/sem)": other * WORKDAYS_PER_WEEK,
                    "Total programado (h/sem)": (titled + presencial + virtual + other) * WORKDAYS_PER_WEEK})
            last_signature = signature
            if presencial + virtual > 0:
                if person.kind == "Apoyo de Titulada":
                    daily_support[index].add(person.identifier)
                elif person.kind == "Contratista adicional":
                    daily_contracts[index].add(person.identifier)
        for month in range(1, 13):
            indices = [i for i, day in enumerate(dates) if day.month == month]
            capacity = math.fsum(person.capacity[i] for i in indices)
            if not capacity:
                continue
            titled = math.fsum(person.titled[i] for i in indices)
            assigned = {m: math.fsum(person.assigned[m][i] for i in indices) for m in MODALITIES}
            other = max(0.0, capacity - sum(assigned.values())) if person.kind == "Planta de Complementaria" else 0.0
            workload.append({"Mes": month, "Instructor ID": person.identifier, "Instructor": person.name,
                "Tipo de recurso": person.kind, "Modalidad de origen": person.modality, "Perfil de origen": person.profile,
                "Capacidad (h/mes)": capacity, "Titulada (h/mes)": titled,
                "Complementaria presencial (h/mes)": assigned["Presencial"], "Complementaria virtual (h/mes)": assigned["Virtual"],
                "Otras actividades de planta (h/mes)": other,
                "Total programado (h/mes)": titled + sum(assigned.values()) + other})
    summaries = []
    for modality in MODALITIES:
        own_courses = [r for r in courses if r["Modalidad"] == modality]
        types = Counter(r["Tipo de recurso"] for r in own_courses)
        settings_row = settings[modality]
        mode_people = [p for p in resources if any(p.assigned[modality])]
        peaks = [sum(p.kind == "Contratista adicional" and p.assigned[modality][i] > 0 for p in mode_people) for i in range(len(dates))]
        peak_index = max(range(len(dates)), key=lambda i: peaks[i])
        summaries.append({"Modalidad": modality, "Meta de aprendices": settings_row["target_learners"],
            "Aprendices por curso": settings_row["learners_per_course"], "Duración promedio (horas)": settings_row["duration_hours"],
            "Cursos necesarios": required[modality], "Cupos proyectados": required[modality] * settings_row["learners_per_course"],
            "Horas requeridas": sum(r["Duración (horas)"] for r in own_courses),
            "Cursos con planta propia": types["Planta de Complementaria"],
            "Cursos con apoyo de Titulada": types["Apoyo de Titulada"], "Cursos que requieren contratación adicional": uncovered[modality],
            "Pico de contratistas adicionales": peaks[peak_index],
            "Inicio del pico adicional": dates[peak_index].isoformat() if peaks[peak_index] else "",
            "Trimestre del pico adicional": (dates[peak_index].month - 1) // 3 + 1 if peaks[peak_index] else None})
        for month in range(1, 13):
            indices = [i for i, day in enumerate(dates) if day.month == month]
            hours = Counter()
            for person in mode_people:
                hours[person.kind] += math.fsum(person.assigned[modality][i] for i in indices)
            monthly.append({"Modalidad": modality, "Mes": month, "Trimestre": (month - 1) // 3 + 1,
                "Cursos que inician": sum(int(r["Inicio"][5:7]) == month for r in own_courses),
                "Cursos que terminan": sum(int(r["Fin"][5:7]) == month for r in own_courses),
                "Horas requeridas": sum(hours.values()), "Horas de planta propia": hours["Planta de Complementaria"],
                "Horas reutilizadas de Titulada": hours["Apoyo de Titulada"], "Horas de contratación adicional": hours["Contratista adicional"],
                "Pico de contratistas adicionales": max(peaks[i] for i in indices)})
    peak_index = max(range(len(dates)), key=lambda i: len(daily_contracts[i]))
    total_hours = math.fsum(row["Horas requeridas"] for row in monthly)
    if not math.isclose(total_hours, math.fsum(r["Duración (horas)"] for r in courses), abs_tol=1e-7):
        raise ValueError("Las horas mensuales no coinciden con la duración de los cursos.")
    return {"summary": {"cursos_necesarios": sum(required.values()), "horas_requeridas": total_hours,
                "cursos_con_planta": sum(r["Cursos con planta propia"] for r in summaries),
                "cursos_con_apoyo_titulada": sum(r["Cursos con apoyo de Titulada"] for r in summaries),
                "cursos_que_requieren_contratacion": sum(uncovered.values()),
                "pico_contratistas_adicionales": len(daily_contracts[peak_index]),
                "inicio_pico_adicional": dates[peak_index].isoformat() if daily_contracts[peak_index] else "",
                "pico_instructores_apoyo": max(map(len, daily_support))},
            "modalities": summaries, "courses": sorted(courses, key=lambda r: (r["Inicio"], r["Modalidad"], r["Curso"])),
            "monthly": monthly, "monthly_instructors": workload, "instructor_intervals": intervals, "contracts": contracts}
