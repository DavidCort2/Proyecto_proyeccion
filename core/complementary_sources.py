"""Capacidad contractual de Titulada por fechas, nunca promedios de carga virtual."""
from calendar import monthrange
from datetime import date
from hashlib import sha256
import json
import math

from core.database import load_planning
from core.planning_modules import planning_database

MODALITIES = ("Presencial", "Virtual")


def source_signature(plan):
    return sha256(json.dumps(plan, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def source_availability(modality, plan, year, *, plant_documents=()):
    metadata = {"Modalidad": modality, "Vigencia": plan.get("planning_year") if plan else None,
                "Guardado": plan.get("saved_at", "") if plan else "",
                "Huella": source_signature(plan) if plan else "", "Estado": "Disponible"}
    result = {"metadata": metadata, "intervals": [], "plant_documents": []}
    if not plan or plan.get("planning_year") != year:
        metadata["Estado"] = "Sin planeación guardada" if not plan else "Corresponde a otra vigencia"
        return result
    result["plant_documents"] = list(plant_documents)
    if modality == "Virtual":
        if plan.get("planning_mode") != "virtual_schedule_v3":
            raise ValueError("Ejecute y guarde Titulada virtual con cronogramas antes de reutilizar su capacidad.")
        intervals = plan.get("instructor_intervals")
        if intervals is None:
            # Compatibilidad con instantáneas anteriores: reconstrucción en memoria.
            from core.virtual_schedule_planner import execute_virtual_schedule_plan, VirtualRules
            inputs = plan["virtual_inputs"]
            _, rebuilt = execute_virtual_schedule_plan(plan["schedule_catalog"],
                **{key: inputs[key] for key in ("programs", "cohorts", "plant")},
                rules=VirtualRules(**plan["rules"]), targets=plan["targets_by_level"], year=year,
                manual_offers=plan.get("manual_offers"))
            if rebuilt["monthly_assignments"] != plan["monthly_assignments"]:
                raise ValueError("La carga guardada de Titulada virtual usa otro cálculo. Ejecute y guarde esa planeación antes de compartir horas.")
            intervals = rebuilt["instructor_intervals"]
        for row in intervals:
            if row["Vinculación"] == "Contratista":
                result["intervals"].append(_interval(modality, row["Instructor"], row["Nombre"], row["Perfil"],
                    row["Inicio"], row["Fin"], row["Capacidad (h/sem)"], row["Formación (h/sem)"]))
    else:
        if "monthly_instructors" not in plan:
            raise ValueError("Ejecute y guarde Titulada presencial con el detalle mensual antes de compartir horas.")
        for row in plan["monthly_instructors"]:
            if row["Tipo"] != "Contratista proyectado":
                continue
            month = row["Mes número"]
            capacity = row["Capacidad (h/sem)"]
            weeks = row["Capacidad (h/mes)"] / capacity if capacity else 0
            if weeks <= 0:
                raise ValueError("Revise la capacidad mensual de los contratistas de Titulada presencial.")
            result["intervals"].append(_interval(modality, row["Instructor ID"], row["Instructor"], row["Perfil"],
                date(year, month, 1).isoformat(), date(year, month, monthrange(year, month)[1]).isoformat(),
                capacity, row["Horas asignadas (h/mes)"] / weeks))
    metadata["Cupos de contratistas"] = len({row["Instructor ID"] for row in result["intervals"]})
    return result


def _interval(modality, identifier, name, profile, start, end, capacity, used):
    if not all(math.isfinite(v) and v >= 0 for v in (capacity, used)) or used > capacity + 1e-7:
        raise ValueError("La carga de Titulada supera la capacidad del contratista.")
    return {"Instructor ID": f"Titulada {modality} | {identifier}", "Instructor": name,
            "Modalidad de origen": modality, "Perfil": profile, "Inicio": start, "Fin": end,
            "Capacidad (h/sem)": capacity, "Titulada (h/sem)": used,
            "Disponible (h/sem)": max(0.0, capacity - used)}


def load_support_sources(base_path, year):
    sources = []
    for modality in MODALITIES:
        saved = load_planning(planning_database(base_path, modality))
        staff, plan = saved if saved else (None, None)
        documents = staff.loc[staff["Es planta"], "Documento"].astype(str).tolist() if saved else []
        sources.append(source_availability(modality, plan, year, plant_documents=documents))
    return sources
