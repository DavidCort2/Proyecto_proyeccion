"""Jornada completa de planta, separada de la cobertura curricular real."""
import math


PLANT_WORKLOAD_BASIS = (
    "La planta tiene programada toda su jornada: formación compatible más otras actividades. "
    "Otras actividades = capacidad del período − horas de formación asignadas. "
    "Solo las horas de formación cubren la demanda de las fichas y se descuentan de la contratación; "
    "se conservan las compatibilidades y los perfiles docentes."
)


def apply_plant_workload(execution, *, virtual=False):
    rows = []
    for source in execution["monthly_instructors"]:
        row = dict(source)
        if virtual:
            plant = row["Vinculación"] == "Planta"
            capacity = row["Capacidad en horas"]
            weekly = row["Capacidad semanal"]
            teaching = row.pop("Horas asignadas")
            row.pop("Horas disponibles")
        else:
            plant = row["Tipo"] == "Planta"
            capacity = row["Capacidad (h/mes)"]
            weekly = row["Capacidad (h/sem)"]
            teaching = row.pop("Horas asignadas (h/mes)")
            row.pop("Horas libres (h/mes)")
        if not all(math.isfinite(v) and v >= 0 for v in (capacity, weekly, teaching)) or teaching > capacity + 1e-7:
            raise ValueError("La jornada de planta requiere horas de formación dentro de la capacidad del instructor.")
        other = max(0.0, capacity - teaching) if plant else 0.0
        total = capacity if plant else teaching
        row.update({"Horas totales programadas (h/sem)": weekly * total / capacity if capacity else 0.0,
                    "Horas totales programadas (h/mes)": total,
                    "Horas de formación (h/mes)": teaching, "Otras actividades (h/mes)": other,
                    "Horas sin programar (h/mes)": max(0.0, capacity - total)})
        first = (["Mes", "Instructor", "Nombre", "Cédula", "Vinculación", "Tipo", "Perfil"] if virtual else
                 ["Mes número", "Mes", "Instructor", "Documento", "Tipo", "Área", "Perfil"])
        first += ["Horas totales programadas (h/sem)", "Horas totales programadas (h/mes)",
                  "Horas de formación (h/mes)", "Otras actividades (h/mes)", "Horas sin programar (h/mes)"]
        rows.append({**{key: row[key] for key in first}, **row})
    # La trazabilidad docente original permanece disponible para conciliar las fichas.
    execution["monthly_workload"] = rows
    execution["plant_workload_basis"] = PLANT_WORKLOAD_BASIS
    execution["calculation_basis"] += " " + PLANT_WORKLOAD_BASIS
    return execution


def workload_capacity_rows(execution, key):
    """Evita mostrar como tiempo libre la jornada completada con otras actividades."""
    rows = execution[key]
    if not execution.get("plant_workload_basis"):
        return rows
    names = {f"Horas libres de planta ({unit})": f"Otras actividades de planta ({unit})"
             for unit in ("h/sem", "h/mes")}
    return [{names.get(k, k): v for k, v in row.items()} for row in rows]
