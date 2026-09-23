"""Duraciones y fechas dependen de las mallas, nunca del nivel o de una jornada nominal."""
from dataclasses import replace

import pandas as pd
import pytest

from core.calendar_planner import ENDING_COLUMNS, calendar_rows, suggested_endings
from core.config import PlanningRules
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.ficha_projection import project_ficha_carryover
from test_curriculum import PROGRAM, curriculum_catalog, curriculum_files, ficha_frame, instructors_frame, run_plan
from test_curriculum_automation import malla


@pytest.mark.parametrize("level,schedule,hours,age,finish", [
    ("Técnico", "Diurna", [7, 11, 13, 17, 19], 3, "2031-06-30"),
    ("Técnico", "Mixto", [8, 15], 1, "2031-03-31"),
    ("Tecnólogo", "Diurno", [1, 2, 3, 4, 5, 6, 7, 8], 6, "2031-06-30"),
    ("Tecnólogo", "P&O-tarde", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 8, "2031-09-30"),
])
def test_duration_end_date_and_monthly_hours_come_from_each_workbook(tmp_path, level, schedule, hours, age, finish):
    filename = f"{PROGRAM} - {schedule}.xlsx"
    catalog = import_curricula(tmp_path / "db.sqlite3", [(filename, malla(hours))])
    frame = ficha_frame().iloc[:1].copy()
    frame.loc[0, ["Nivel", "Jornada", "Trimestre actual"]] = [level, schedule, age]
    staff = instructors_frame()
    imported = prepare_ficha_import(frame, staff, catalog, 2031, "fichas.xlsx", "source", 2030, 4)
    plan = execute_curriculum_plan(staff, imported, catalog, PlanningRules(), {"Técnico": 0, "Tecnólogo": 0}, 2031, "planta.xlsx", "source")
    row = plan["ficha_import"]["detail"][0]
    assert row["Duración (trimestres)"] == len(hours)
    assert row["Trimestre al iniciar la vigencia"] == age + 1
    assert row["Trimestres pendientes al iniciar la vigencia"] == len(hours) - age
    assert row["Fecha fin estimada"] == finish
    assert row["Archivo malla"] == filename
    expected = hours[age:] + [0] * (4 - len(hours[age:]))
    assert [row["Horas requeridas"] for row in plan["quarterly"]] == [weekly * 12 for weekly in expected]
    assert plan["center"]["demanda_total_horas_anuales"] == sum(hours[age:]) * 12
    assert all(row["Duración (trimestres)"] == len(hours) and row["Fecha fin estimada"] == finish for row in plan["monthly_fichas"])
    assert max(row["Mes número"] for row in plan["monthly_fichas"]) == int(finish[5:7])


def test_programs_of_the_same_level_and_shift_have_independent_durations(tmp_path):
    catalog = import_curricula(tmp_path / "db.sqlite3", [("Corto - DIURNA.xlsx", malla([3, 5])),
                                                       ("Largo - DIURNA.xlsx", malla([3, 5, 7, 11, 13]))])
    rows = [{"Ficha": str(i), "Especialidad": program, "Nivel": "Tecnólogo", "Jornada": "Diurna", "Trimestre actual": 1}
            for i, program in enumerate(["Corto", "Largo"])]
    imported = prepare_ficha_import(pd.DataFrame(rows), instructors_frame(), catalog, 2031, "f.xlsx", "x", 2030, 4)
    assert [row["Duración (trimestres)"] for row in imported["detail"]] == [2, 5]
    assert [row["Fecha fin estimada"] for row in imported["detail"]] == ["2031-03-31", "2031-12-31"]


@pytest.mark.parametrize("year,passes,start_age", [(2031, True, 5), (2032, False, None)])
def test_earlier_report_and_later_planning_year_advance_actual_training_age(tmp_path, year, passes, start_age):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(PROGRAM + " - DIURNA.xlsx", malla([3] * 5))])
    imported = prepare_ficha_import(ficha_frame(day_age=2).iloc[:1], instructors_frame(), catalog, year, "f.xlsx", "x", 2030, 2)
    row = imported["detail"][0]
    assert row["Fecha fin estimada"] == "2031-03-31"
    assert row["Pasa a la vigencia"] == passes
    assert row["Trimestre al iniciar la vigencia"] == start_age


def test_reimport_recomputes_endings_without_using_stored_ages_or_duration(tmp_path):
    path = tmp_path / "db.sqlite3"
    filename = PROGRAM + " - DIURNA.xlsx"
    original = import_curricula(path, [(filename, malla([3] * 6))])
    staff, before = run_plan(original, frame=ficha_frame(day_age=2).iloc[:1], target=0)
    assert before["ficha_import"]["detail"][0]["Fecha fin estimada"] == "2027-12-31"
    assert before["center"]["demanda_total_horas_anuales"] == 144
    imported = before["ficha_import"]
    imported["detail"][0]["Duración (trimestres)"] = 100
    imported["detail"][0]["Trimestre actual"] = 99
    shorter = import_curricula(path, [(filename, malla([3] * 3))])
    after = execute_curriculum_plan(staff, imported, shorter, PlanningRules(), {"Técnico": 0, "Tecnólogo": 0}, 2027, "i.xlsx", "x")
    assert after["ficha_import"]["detail"][0]["Fecha fin estimada"] == "2027-03-31"
    assert after["ficha_import"]["detail"][0]["Duración (trimestres)"] == 3
    assert after["center"]["demanda_total_horas_anuales"] == 36


def test_missing_curriculum_cannot_use_nominal_or_manual_duration():
    frame = ficha_frame(day_age=7).iloc[:1]
    with pytest.raises(ValueError, match="Faltan mallas.*Diurna"):
        project_ficha_carryover(frame, 2026, 4, 2027, {"DIURNA-MANANA": 7}, curriculum_durations={})
    distribution = pd.DataFrame([{"Especialidad": PROGRAM, "Nivel": "Tecnólogo", "Jornada": "Diurna",
                                  "Fichas que pasan": 0, "Fichas nuevas": 0, "Fichas que terminan": 0}])
    endings = distribution.assign(**{column: 0 for column in ENDING_COLUMNS})
    with pytest.raises(ValueError, match="Faltan mallas.*Diurna"):
        calendar_rows(distribution, endings, PlanningRules(), durations={}, intake_schedule={0: [0] * 4})


def test_report_age_beyond_curriculum_is_an_error_not_a_completed_ficha(tmp_path):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(PROGRAM + " - DIURNA.xlsx", malla([3, 5]))])
    with pytest.raises(ValueError, match="Ficha 001.*supera los 2 trimestres"):
        run_plan(catalog, frame=ficha_frame(day_age=3).iloc[:1], target=0)


def test_strict_endings_never_spread_unknown_dates_across_quarters():
    manual = pd.DataFrame([{"Especialidad": PROGRAM, "Nivel": "Tecnólogo", "Jornada": "Diurna", "Fichas que terminan": 2}])
    with pytest.raises(ValueError, match="terminaciones no coinciden"):
        suggested_endings(manual, {"detail": []}, strict=True)


def test_curricular_execution_never_calls_legacy_duration_growth_or_hour_rules(curriculum_catalog, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Se llamó una regla histórica en el cálculo curricular")

    for function in ["core.ficha_projection.duration_in_quarters", "core.calendar_planner.duration_in_quarters",
                     "core.level_planner.project_by_level", "core.level_planner.growth_requirements",
                     "core.planner.growth_requirements", "core.level_planner.hours_by_profile",
                     "core.calendar_planner.hours_by_profile"]:
        monkeypatch.setattr(function, forbidden)
    _, original = run_plan(curriculum_catalog)
    rules = replace(PlanningRules(intake_weights=(100, 0, 0, 0)), weekly_hours_per_ficha=123,
                    mixed_weekly_hours_per_ficha=456, weekly_bilingual_hours=17, weekly_integrality_hours=19,
                    mixed_weekly_bilingual_hours=21, mixed_weekly_integrality_hours=23)
    _, changed_references = run_plan(curriculum_catalog, rules=rules)
    for key in ["center", "calendar", "quarterly", "monthly", "monthly_fichas", "summary", "contract_windows"]:
        assert original[key] == changed_references[key]
    assert original["center"]["demanda_total_horas_anuales"] == 3360


@pytest.mark.parametrize("duration,finish", [(2, "2027-12-31"), (5, "2028-09-30")])
def test_new_fichas_finish_from_their_offer_and_workbook_duration(tmp_path, duration, finish):
    catalog = import_curricula(tmp_path / "db.sqlite3", [(PROGRAM + " - MIXTA.xlsx", malla([6] * duration))])
    frame = ficha_frame(mixed_age=duration).iloc[1:]
    _, plan = run_plan(catalog, frame=frame, rules=PlanningRules(intake_weights=(0, 0, 100, 0)), target=25)
    assert [row["Fichas activas"] for row in plan["quarterly"]] == [0, 0, 1, 1]
    assert {row["Trimestre de formación"] for row in plan["monthly_fichas"]} == {1, 2}
    assert {row["Fecha fin estimada"] for row in plan["monthly_fichas"]} == {finish}
    assert {row["Duración (trimestres)"] for row in plan["monthly_fichas"]} == {duration}
