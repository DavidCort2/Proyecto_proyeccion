import math

import pandas as pd
import pytest

from core.config import PlanningRules
from core.contracting_periods import individual_contract_periods
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from test_curriculum import PROGRAM, curriculum_catalog, curriculum_files, ficha_frame, instructors_frame, run_plan
from test_curriculum_automation import malla


@pytest.mark.parametrize("target,new", [(0, 0), (25, 0), (50, 0), (51, 1), (100, 2), (105, 3)])
def test_target_counts_continuing_learners_once(curriculum_catalog, target, new):
    _, plan = run_plan(curriculum_catalog, target=target)
    assert plan["center"]["fichas_que_pasan"] == 2
    assert plan["center"]["fichas_nuevas"] == new
    assert plan["center"]["cupos_nuevos"] == new * 25
    assert plan["center"]["aprendices_proyectados"] == (new + 2) * 25
    assert plan["center"]["nuevas_adicionales_por_rotacion"] == 0
    assert "growth_rule" not in plan
    assert sum(row["Fichas nuevas"] for row in plan["quarterly"]) == new


def test_five_percent_does_not_add_a_full_ficha_to_every_small_program(tmp_path):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(name + " - DIURNA.xlsx", malla([30] * 7))
                                                       for name in ("Grande", "Pequeño")])
    rows = [{"Ficha": str(i), "Especialidad": "Grande" if i < 39 else "Pequeño", "Nivel": "Tecnólogo",
             "Jornada": "Diurna", "Trimestre actual": 1} for i in range(40)]
    instructors = instructors_frame()
    imported = prepare_ficha_import(pd.DataFrame(rows), instructors, catalog, 2027, "f.xlsx", "x", 2026, 4)
    plan = execute_curriculum_plan(instructors, imported, catalog, PlanningRules(), {"Técnico": 0, "Tecnólogo": 1050}, 2027, "i.xlsx", "x")
    # 1000 aprendices + 5 % = 1050: 40 fichas que pasan y solo 2 nuevas.
    assert plan["center"]["fichas_nuevas"] == 2
    allocations = {row["Especialidad"]: row["Fichas nuevas"] for row in plan["distribution"]}
    assert allocations == {"Grande": 2, "Pequeño": 0}


def test_completed_new_fichas_do_not_create_unbudgeted_replacements(tmp_path):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(PROGRAM + " - DIURNA.xlsx", malla([30] * 3))])
    _, plan = run_plan(catalog, frame=ficha_frame(day_age=3).iloc[:1], target=100)
    assert [row["Fichas nuevas"] for row in plan["quarterly"]] == [4, 0, 0, 0]
    assert [row["Fichas activas"] for row in plan["quarterly"]] == [4, 4, 4, 0]
    assert plan["center"]["demanda_total_horas_anuales"] == 4 * 30 * 12 * 3
    assert all(row["Requerido hasta"] == "2027-09-30" for row in individual_contract_periods(plan))


def test_offer_percentages_apply_to_the_entire_new_intake_budget(curriculum_catalog):
    # 500 = 2 que pasan + 18 nuevas: las ofertas suman exactamente 18.
    _, plan = run_plan(curriculum_catalog, target=500, rules=PlanningRules())
    assert [row["Fichas nuevas"] for row in plan["quarterly"]] == [9, 4, 3, 2]
    assert sum(row["Fichas nuevas"] for row in plan["distribution"]) == 18
    for row in plan["distribution"]:
        quarterly = [q for q in plan["calendar"] if (q["Especialidad"], q["Nivel"], q["Jornada"]) == (row["Especialidad"], row["Nivel"], row["Jornada"])]
        assert sum(q["Fichas nuevas"] for q in quarterly) == row["Fichas nuevas"]


def test_remaining_malla_hours_and_plant_cover_determine_each_contract(tmp_path):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(PROGRAM + " - DIURNA.xlsx", malla([10, 40, 20, 30]))])
    _, plan = run_plan(catalog, frame=ficha_frame(day_age=1).iloc[:1], target=50)
    # Una continuación cursa edades 2,3,4; una nueva cursa 1,2,3,4.
    assert [row["Horas requeridas"] for row in plan["quarterly"]] == [600, 720, 600, 360]
    assert [row["contratistas_totales"] for row in plan["quarterly"]] == [1, 1, 1, 0]
    assert plan["center"]["demanda_total_horas_anuales"] == 2280
    assert individual_contract_periods(plan)[0]["Requerido hasta"] == "2027-09-30"
    assert math.fsum(row["Horas asignadas (h/mes)"] for row in plan["monthly_assignments"]) == 2280
    assert all(row["Horas asignadas (h/mes)"] <= row["Capacidad (h/mes)"] for row in plan["monthly_instructors"])
