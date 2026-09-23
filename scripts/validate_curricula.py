"""Comprueba la planeación real y exporta una revisión sin reemplazar la ejecución."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import PlanningRules
from core.contracting_periods import contracting_headline, individual_contract_periods
from core.curriculum_planner import execute_curriculum_plan
from core.curriculum_store import load_curricula
from core.database import load_planning
from core.export import export_planning


def verify(plan):
    if plan.get("target_basis"):
        for level in plan["levels"]:
            pending = max(0, level["Meta de aprendices"] - level["Fichas que pasan"] * plan["rules"]["learners_per_ficha"])
            assert level["Fichas nuevas"] == math.ceil(pending / plan["rules"]["learners_per_ficha"])
        assert plan["center"]["nuevas_adicionales_por_rotacion"] == 0
    if "offers_by_program" in plan:
        assert sum(row["Total anual"] for row in plan["offers_by_program"]) == plan["center"]["fichas_nuevas"]
        for table in (plan["offers_by_program"], plan["offers_by_profile"]):
            for row in table:
                assert sum(row[f"Oferta T{q}"] for q in range(1, 5)) == row["Total anual"]
            for quarter in plan["quarterly"]:
                assert sum(row[f"Oferta T{quarter['Trimestre']}"] for row in table) == quarter["Fichas nuevas"]
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
    headline = contracting_headline(plan)
    assert headline["Total de contratistas requeridos"] == max(row["Contratistas requeridos"] for row in plan["monthly"])
    assert headline["Técnicos en el pico"] + headline["Transversales en el pico"] == headline["Total de contratistas requeridos"]
    periods = individual_contract_periods(plan)
    for month in range(1, 13):
        active = [row["Instructor ID"] for row in periods
                  if int(row["Requerido desde"][5:7]) <= month <= int(row["Requerido hasta"][5:7])]
        expected = [row["Instructor ID"] for row in plan["monthly_instructors"]
                    if row["Mes número"] == month and row["Tipo"] == "Contratista proyectado"]
        assert sorted(active) == sorted(expected)


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
    print(f"Contratistas con fechas individuales: {len(individual_contract_periods(plan))}. Pico: {contracting_headline(plan)['Trimestre del pico máximo']}.")
    print(f"Exportado: {output}. La ejecución guardada se conserva.")


if __name__ == "__main__":
    main()
