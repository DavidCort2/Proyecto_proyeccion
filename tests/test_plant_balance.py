from copy import deepcopy
from io import BytesIO
import math

import pandas as pd
import pytest

from core.config import PlanningRules
from core.curriculum_planner import execute_curriculum_plan
from core.curriculum_store import load_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from core.plant_balance import apply_plant_balance
from scripts.validate_curricula import verify
from test_presencial_offers import scenario


def test_full_capacity_of_a_program_is_subtracted_before_hiring(tmp_path):
    staff, plan = scenario(tmp_path, [("Programa", "Diurna", 7, [1, 1])], 50)
    # Two cohorts at 10 h/week; one plant instructor has 32 h/week.
    for row in plan["plant_balance_by_profile"]:
        if row["Programa o perfil"] == "Programa":
            assert row["Horas requeridas (h/sem)"] == 20
            assert row["Capacidad de planta (h/sem)"] == 32
            assert row["Horas descontadas de planta (h/sem)"] == 20
            assert row["Horas libres de planta (h/sem)"] == 12
            assert row["Horas a contratar (h/sem)"] == row["Contratistas requeridos"] == 0
    assert plan["summary"]["pico_contratistas_total"] == 0
    verify(plan)


def test_unused_and_unmatched_plant_capacity_is_visible_without_duplicate_deduction(tmp_path):
    staff, plan = scenario(tmp_path, [("Programa", "Diurna", 7, [1] * 5)], 125)
    staff.loc[len(staff)] = ["Otro perfil", "Técnica", "Planta sin demanda", "04", "Planta", 200, True]
    rules = PlanningRules(**{**plan["rules"], "weeks_per_quarter": 11})
    plan = execute_curriculum_plan(staff, plan["ficha_import"], load_curricula(tmp_path / "mallas.sqlite3"), rules,
        plan["targets_by_level"], 2027, "planta.xlsx", "p")
    verify(plan)
    for row in plan["plant_balance"]:
        assert row["Instructores de planta"] == 4
        assert math.isclose(row["Capacidad total de planta (h/sem)"], 128)
        assert math.isclose(row["Horas requeridas (h/sem)"], 50)
        assert math.isclose(row["Horas descontadas de planta (h/sem)"], 32)
        assert math.isclose(row["Horas libres de planta (h/sem)"], 96)
        assert math.isclose(row["Horas a contratar por perfil (h/sem)"], 18)
        assert row["Saldo global (h/sem)"] == 0
        assert row["Contratistas por perfil"] == 1
    unmatched = [r for r in plan["plant_balance_by_profile"] if r["Programa o perfil"] == "Otro perfil"]
    assert len(unmatched) == 4
    assert all(math.isclose(r["Horas libres de planta (h/sem)"], 32) for r in unmatched)
    assert all(r["Horas descontadas de planta (h/sem)"] == 0 for r in unmatched)


def test_balance_rejects_duplicated_plant_capacity_or_unreconciled_hours(tmp_path):
    _, plan = scenario(tmp_path, [("Programa", "Diurna", 7, [1] * 5)], 125)
    duplicate = deepcopy(plan)
    duplicate["monthly_instructors"].append(duplicate["monthly_instructors"][0])
    with pytest.raises(ValueError, match="dos veces"):
        apply_plant_balance(duplicate, PlanningRules(**plan["rules"]))
    wrong = deepcopy(plan)
    next(row for row in wrong["monthly_staffing"] if row["Horas a contratar (h/mes)"] > 0)["Horas a contratar (h/mes)"] += 1
    with pytest.raises(ValueError, match="no concilian"):
        apply_plant_balance(wrong, PlanningRules(**plan["rules"]))


def test_plant_balance_persists_and_is_exported(tmp_path):
    staff, plan = scenario(tmp_path, [("Programa", "Diurna", 7, [1] * 5)], 125)
    path = tmp_path / "plan.sqlite3"
    save_planning(path, staff, plan)
    saved = load_planning(path)
    assert saved[1]["plant_balance"] == plan["plant_balance"]
    book = BytesIO(export_planning(*saved))
    for key, sheet in [("plant_balance", "Descuento de planta"), ("plant_balance_by_profile", "Planta por programa y perfil")]:
        expected = pd.DataFrame(plan[key]).rename(columns={"Horas libres de planta (h/sem)": "Otras actividades de planta (h/sem)"})
        pd.testing.assert_frame_equal(pd.read_excel(book, sheet_name=sheet), expected, check_dtype=False)
