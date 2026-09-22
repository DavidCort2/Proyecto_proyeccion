"""Comprueba la planeación real y exporta una revisión sin reemplazar la ejecución."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import PlanningRules
from core.curriculum_planner import execute_curriculum_plan
from core.curriculum_store import load_curricula
from core.database import load_planning
from core.export import export_planning


def verify(plan):
    for quarter in plan["quarterly"]:
        months = [row for row in plan["monthly"] if row["Trimestre"] == quarter["Trimestre"]]
        assert math.isclose(sum(row["Horas requeridas"] for row in months), quarter["Horas requeridas"])
        assert all(row["Contratistas requeridos"] == quarter["contratistas_totales"] for row in months)
    for row in plan["contracting_profile_quarterly"]:
        active = sum(window["Contratistas"] for window in plan["contract_windows"]
                     if window["Área"] == row["Área"] and window["Perfil"] == row["Perfil"]
                     and window["Desde T"] <= row["Trimestre"] <= window["Hasta T"])
        assert active == row["Contratistas requeridos"]
    required, assigned = {}, {}
    for row in plan["monthly_fichas"]:
        key = row["Ficha"], row["Mes número"]
        assert key not in required, f"Ficha y mes duplicados: {key}"
        required[key] = row["Horas requeridas (h/mes)"]
    for row in plan["monthly_assignments"]:
        key = row["Ficha"], row["Mes número"]
        assigned[key] = assigned.get(key, 0) + row["Horas asignadas (h/mes)"]
    assert all(math.isclose(assigned.get(key, 0), hours) for key, hours in required.items())
    assert math.isclose(sum(assigned.values()), plan["center"]["demanda_total_horas_anuales"])
    assert all(row["Horas asignadas (h/mes)"] <= row["Capacidad (h/mes)"] + 1e-8 for row in plan["monthly_instructors"])
    assert {row["Tipo"] for row in plan["monthly_instructors"]} <= {"Planta", "Contratista proyectado"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/planeacion.sqlite3")
    parser.add_argument("--output", default="data/validaciones/planeacion_periodos_contratacion.xlsx")
    args = parser.parse_args()
    catalog = load_curricula(args.database)
    saved = load_planning(args.database)
    if not saved or not saved[1].get("ficha_import"):
        parser.error("Se necesita una ejecución con los dos reportes guardados.")
    instructors, prior = saved
    plan = execute_curriculum_plan(instructors, prior["ficha_import"], catalog, PlanningRules(**prior["rules"]),
                                   prior["targets_by_level"], prior["planning_year"], prior["source_name"], prior["source_digest"])
    verify(plan)
    plan["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(export_planning(instructors, plan))
    print(f"Verificados {len(plan['monthly_fichas'])} registros ficha/mes y {len(plan['monthly_assignments'])} asignaciones.")
    print(f"Horas anuales: {plan['center']['demanda_total_horas_anuales']:g}.")
    for row in plan["monthly"][::3]:
        print(f"T{row['Trimestre']}: {row['Horas requeridas']:g} h/mes; contratistas {row['Contratistas requeridos']} (técnicos {row['Contratistas técnicos']}, transversales {row['Contratistas transversales']}).")
    print(f"Períodos propuestos: {len(plan['contract_windows'])}. Meses-contratista evitables frente a conservar los picos por perfil: {plan['summary']['meses_contratista_evitables']}.")
    print(f"Exportado: {output}. La ejecución guardada se conserva.")


if __name__ == "__main__":
    main()
