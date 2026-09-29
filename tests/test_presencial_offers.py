"""Saldo de meta y reemplazos reales, sin crecimiento de programas pequeños."""
from io import BytesIO

import pandas as pd
import pytest

from core.config import PlanningRules
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from scripts.validate_curricula import verify
from test_curriculum import instructors_frame
from test_curriculum_automation import malla


def scenario(tmp_path, programs, target, *, weights=(50, 25, 15, 10), learners=25, reverse=False):
    """Nombre, jornada, duración curricular y edades del reporte en T4."""
    catalog = import_curricula(tmp_path / "mallas.sqlite3", [
        (f"{name} - {shift}.xlsx", malla([10] * duration)) for name, shift, duration, ages in programs])
    rows = [{"Ficha": f"{p}-{n}", "Especialidad": name, "Jornada": shift, "Nivel": "Tecnólogo", "Trimestre actual": age}
            for p, (name, shift, duration, ages) in enumerate(programs) for n, age in enumerate(ages)]
    staff = instructors_frame()
    staff.loc[0, "Especialidad"] = programs[0][0]
    staff.attrs["specialties"] = staff[["Especialidad", "Área"]].to_dict("records")
    imported = prepare_ficha_import(pd.DataFrame(rows[::-1] if reverse else rows), staff, catalog,
                                    2027, "f.xlsx", "f", 2026, 4)
    plan = execute_curriculum_plan(staff, imported, catalog,
        PlanningRules(learners_per_ficha=learners, intake_weights=weights),
        {"Técnico": 0, "Tecnólogo": target}, 2027, "p.xlsx", "p")
    verify(plan)
    return staff, plan


@pytest.mark.parametrize("learners,target,new", [(25, 500, 10), (20, 400, 10), (25, 501, 11), (25, 250, 0), (25, 100, 0)])
def test_continuing_fichas_are_subtracted_once_using_the_same_size_as_new_fichas(tmp_path, learners, target, new):
    _, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 10)], target, learners=learners)
    assert plan["center"]["fichas_que_pasan"] == 10
    assert plan["center"]["aprendices_que_pasan_estimados"] == 10 * learners
    assert plan["center"]["fichas_nuevas"] == new
    assert plan["center"]["aprendices_proyectados"] == (10 + new) * learners


@pytest.mark.parametrize("duration,age,expected", [(7, 6, [0, 1, 0, 0]), (7, 5, [0, 0, 1, 0]),
    (7, 4, [0, 0, 0, 1]), (5, 1, [0, 0, 0, 0]), (7, 1, [0, 0, 0, 0]), (7, 7, [0, 0, 0, 0])])
def test_small_program_only_replaces_its_continuing_cohort_after_completion(tmp_path, duration, age, expected):
    _, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 10),
                                  ("Pequeño", "Diurna", duration, [age])], 400)
    small = next(row for row in plan["offers_by_program"] if row["Programa"] == "Pequeño")
    assert [small[f"Oferta T{q}"] for q in range(1, 5)] == expected
    assert small["Total anual"] == sum(expected)
    assert small["Criterio de oferta"] == "Solo reemplazos"
    assert all(row["Fichas activas"] <= 1 for row in plan["calendar"] if row["Especialidad"] == "Pequeño")
    assert plan["center"]["fichas_nuevas"] == (5 if age < duration else 6)


def test_replacement_timing_takes_precedence_over_an_early_offer_percentage(tmp_path):
    _, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 10),
                                  ("Pequeño", "Diurna", 7, [6])], 400, weights=(100, 0, 0, 0))
    assert [row["Fichas nuevas"] for row in plan["quarterly"]] == [4, 1, 0, 0]
    assert plan["center"]["fichas_nuevas"] == 5
    assert plan["center"]["nuevas_adicionales_por_rotacion"] == 0


def test_insufficient_net_target_does_not_add_replacements_outside_the_budget(tmp_path):
    _, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 10),
                                  ("Primero", "Diurna", 7, [6]),
                                  ("Después", "Diurna", 7, [5])], 325)
    offers = {row["Programa"]: row for row in plan["offers_by_program"]}
    assert plan["center"]["fichas_nuevas"] == 1
    assert offers["Primero"]["Oferta T2"] == 1
    assert offers["Popular"]["Total anual"] == offers["Después"]["Total anual"] == 0


def test_new_program_declared_popular_receives_intakes_without_reopening_its_predecessor(tmp_path):
    old = "DISEÑO E INTEGRACIÓN DE AUTOMATISMOS MECATRÓNICOS"
    new = "AUTOMATIZACION DE SISTEMAS MECATRONICOS"
    _, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 20),
                                  (old, "Diurna", 7, [1]), (new, "Diurna", 7, [1]),
                                  ("Pequeño", "Diurna", 7, [1])], 875)
    offers = {row["Programa"]: row for row in plan["offers_by_program"]}
    assert old not in offers
    assert offers[new]["Total anual"] == 1
    assert offers["Pequeño"]["Total anual"] == 0
    assert offers["Popular"]["Total anual"] == 11
    assert all(row["Fichas nuevas"] == 0 for row in plan["distribution"] if row["Especialidad"] == old)


def test_popularity_combines_shifts_and_report_order_does_not_change_the_plan(tmp_path):
    programs = [("Dos jornadas", "Diurna", 7, [1] * 3), ("Dos jornadas", "Mixta", 7, [1] * 3),
                ("Otra", "Diurna", 7, [1] * 5)]
    _, plan = scenario(tmp_path, programs, 475)
    _, reversed_plan = scenario(tmp_path, programs, 475, reverse=True)
    assert plan["offers_by_program"] == reversed_plan["offers_by_program"]
    assert plan["offers_by_profile"] == reversed_plan["offers_by_profile"]
    assert next(row for row in plan["offers_by_program"] if row["Programa"] == "Otra")["Total anual"] == 0
    assert [row["Total anual"] for row in plan["offers_by_profile"] if row["Programa"] == "Dos jornadas"] == [4, 4]


def test_intake_decisions_survive_save_reopen_and_export(tmp_path):
    staff, plan = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 4),
                                    ("Pequeño", "Diurna", 7, [6])], 200)
    path = tmp_path / "plan.sqlite3"
    save_planning(path, staff, plan)
    restored_staff, restored = load_planning(path)
    assert restored["intake_decisions"] == plan["intake_decisions"]
    output = BytesIO(export_planning(restored_staff, restored))
    pd.testing.assert_frame_equal(pd.read_excel(output, sheet_name="Reemplazos y popularidad"),
                                  pd.DataFrame(plan["intake_decisions"]), check_dtype=False)
