"""Conciliación de la planta registrada con sus horas realmente asignadas."""
import math


def apply_plant_balance(execution, rules):
    balances, profiles = [], []
    weeks = rules.weeks_per_quarter / 3.0
    for quarter in range(1, 5):
        month = quarter * 3 - 2
        people = [row for row in execution["monthly_instructors"] if row["Mes número"] == month and row["Tipo"] == "Planta"]
        identifiers = [row["Instructor ID"] for row in people]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("La capacidad de una persona de planta no puede contarse dos veces en el mismo período.")
        capacity = math.fsum(row["Capacidad (h/mes)"] for row in people) / weeks
        if not math.isclose(capacity, execution["center"]["capacidad_planta_horas_semana"], abs_tol=1e-7):
            raise ValueError(f"T{quarter}: la capacidad de planta no coincide con todos los instructores del reporte.")
        applied = math.fsum(row["Horas asignadas (h/mes)"] for row in people) / weeks
        staffing = [row for row in execution["monthly_staffing"] if row["Mes número"] == month]
        required = math.fsum(row["Horas requeridas (h/mes)"] for row in staffing) / weeks
        remaining = math.fsum(row["Horas a contratar (h/mes)"] for row in staffing) / weeks
        global_remaining = max(0.0, required - capacity)
        if not math.isclose(required, applied + remaining, abs_tol=1e-7) or applied > capacity + 1e-7:
            raise ValueError(f"T{quarter}: las horas de planta y contrato no concilian con la demanda curricular.")
        balances.append({"Trimestre": quarter, "Instructores de planta": len(people),
                         "Horas requeridas (h/sem)": required, "Capacidad total de planta (h/sem)": capacity,
                         "Horas descontadas de planta (h/sem)": applied,
                         "Horas libres de planta (h/sem)": max(0.0, capacity - applied),
                         "Saldo global (h/sem)": global_remaining,
                         "Horas a contratar por perfil (h/sem)": remaining,
                         "Contratistas por perfil": sum(row["Contratistas requeridos"] for row in staffing)})
        for row in staffing:
            demand = row["Horas requeridas (h/mes)"] / weeks
            pending = row["Horas a contratar (h/mes)"] / weeks
            profiles.append({"Trimestre": quarter, "Área": row["Área"], "Programa o perfil": row["Perfil"],
                             "Instructores de planta": row["Instructores planta"],
                             "Horas requeridas (h/sem)": demand,
                             "Capacidad de planta (h/sem)": row["Capacidad planta (h/mes)"] / weeks,
                             "Horas descontadas de planta (h/sem)": demand - pending,
                             "Horas libres de planta (h/sem)": row["Horas libres de planta (h/mes)"] / weeks,
                             "Horas a contratar (h/sem)": pending,
                             "Contratistas requeridos": row["Contratistas requeridos"]})
    execution["plant_balance"] = balances
    execution["plant_balance_by_profile"] = profiles
    return execution
