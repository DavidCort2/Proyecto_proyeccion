"""Orden de ofertas, conservación de cupos y efecto real en horas y contratación."""
from io import BytesIO
import random

import pandas as pd
import pytest

from core.config import PlanningRules
from core.curriculum_intakes import OFFER_COLUMNS, curricular_offer_schedule
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from core.planner import largest_remainder_allocation
from scripts.validate_curricula import verify
from test_curriculum import instructors_frame
from test_curriculum_automation import malla


def offer_inputs(rows):
    """Programa, jornada, nivel, fichas del reporte, nuevas ya presupuestadas."""
    audit = [{"Especialidad": program, "Jornada": shift, "Nivel": level,
              "Fichas del reporte": census, "Fichas nuevas asignadas": new}
             for program, shift, level, census, new in rows]
    distribution = pd.DataFrame([{**row, "Fichas nuevas": row["Fichas nuevas asignadas"]} for row in audit])
    return distribution, audit


def test_lower_presence_programs_enter_first_and_popular_program_fills_later_offers():
    distribution, audit = offer_inputs([
        ("Popular", "Diurna", "Tecnólogo", 7, 7),
        ("Menor", "Diurna", "Tecnólogo", 2, 2),
        ("Intermedio", "Diurna", "Tecnólogo", 3, 3),
    ])
    schedule = curricular_offer_schedule(distribution, PlanningRules(intake_weights=(25, 25, 25, 25)), audit)
    assert schedule == {0: [0, 1, 3, 3], 1: [2, 0, 0, 0], 2: [1, 2, 0, 0]}


def test_presence_sums_jornadas_and_levels_keep_their_own_offer_budget():
    distribution, audit = offer_inputs([
        ("Varias jornadas", "Diurna", "Tecnólogo", 2, 2),
        ("Varias jornadas", "Mixta", "Tecnólogo", 2, 2),
        ("Una jornada", "Diurna", "Tecnólogo", 3, 3),
        ("Técnico único", "Diurna", "Técnico", 8, 3),
    ])
    schedule = curricular_offer_schedule(distribution, PlanningRules(intake_weights=(40, 30, 30, 0)), audit)
    assert schedule == {0: [0, 1, 1, 0], 1: [0, 1, 1, 0], 2: [3, 0, 0, 0], 3: [1, 1, 1, 0]}


def test_equal_presence_shares_offers_and_does_not_depend_on_report_order():
    distribution, audit = offer_inputs([
        ("B", "Diurna", "Tecnólogo", 3, 4),
        ("A", "Diurna", "Tecnólogo", 3, 4),
    ])
    rules = PlanningRules(intake_weights=(25, 25, 25, 25))
    assert curricular_offer_schedule(distribution, rules, audit) == {0: [1, 1, 1, 1], 1: [1, 1, 1, 1]}
    rules = PlanningRules(intake_weights=(40, 30, 20, 10))
    before = curricular_offer_schedule(distribution, rules, audit)
    after = curricular_offer_schedule(distribution.iloc[::-1], rules, audit[::-1])
    assert before == after


@pytest.mark.parametrize("weights", [(100, 0, 0, 0), (0, 0, 0, 100), (0, 60, 40, 0), (50, 25, 15, 10)])
def test_integer_quotas_and_early_priority_hold_for_varied_program_sizes(weights):
    rng = random.Random(4096)
    for _ in range(30):
        rows = [(f"Programa {i}", "Diurna", "Tecnólogo", rng.randint(1, 30), rng.randint(0, 12))
                for i in range(8)]
        distribution, audit = offer_inputs(rows)
        rules = PlanningRules(intake_weights=weights)
        schedule = curricular_offer_schedule(distribution, rules, audit)
        expected = largest_remainder_allocation(sum(row[-1] for row in rows), range(4), weights)
        for i, offers in schedule.items():
            assert sum(offers) == rows[i][-1]
            assert all(isinstance(count, int) and count >= 0 for count in offers)
        assert {q: sum(offers[q] for offers in schedule.values()) for q in range(4)} == expected
        for i, left in enumerate(rows):
            for j, right in enumerate(rows):
                if left[-2] < right[-2]:
                    for q in range(4):
                        # No se pospone una ficha de menor presencia si ya ingresó una de mayor presencia.
                        assert not (sum(schedule[i][q + 1:]) and schedule[j][q])


@pytest.mark.parametrize("problem", ["missing", "duplicate", "zero"])
def test_missing_or_invalid_source_presence_is_not_replaced_with_default_weights(problem):
    distribution, audit = offer_inputs([("A", "Diurna", "Tecnólogo", 3, 2)])
    if problem == "missing":
        audit = []
    elif problem == "duplicate":
        audit += audit
    else:
        audit[0]["Fichas del reporte"] = 0
    with pytest.raises(ValueError, match="cantidad de fichas del reporte"):
        curricular_offer_schedule(distribution, PlanningRules(), audit)


@pytest.fixture
def two_program_plan(tmp_path):
    catalog = import_curricula(tmp_path / "mallas.sqlite3", [
        ("Menor - DIURNA.xlsx", malla([10, 20])),
        ("Popular - DIURNA.xlsx", malla([5, 15, 25, 35])),
    ])
    staff = instructors_frame()
    staff.loc[0, "Especialidad"] = "Popular"
    staff.attrs["specialties"] = staff[["Especialidad", "Área"]].to_dict("records")
    fichas = pd.DataFrame([{"Ficha": str(i), "Especialidad": program, "Nivel": "Tecnólogo",
                            "Jornada": "Diurna", "Trimestre actual": 1}
                           for i, program in enumerate(["Menor", "Popular", "Popular", "Popular"])])
    imported = prepare_ficha_import(fichas, staff, catalog, 2027, "f.xlsx", "f", 2026, 4)
    rules = PlanningRules(intake_weights=(50, 0, 0, 50))
    plan = execute_curriculum_plan(staff, imported, catalog, rules, {"Técnico": 0, "Tecnólogo": 200}, 2027, "i.xlsx", "i")
    return staff, plan


def test_offers_drive_training_ages_monthly_hours_and_contract_end_dates(two_program_plan):
    _, plan = two_program_plan
    programs = {row["Programa"]: row for row in plan["offers_by_program"]}
    assert [programs["Menor"][column] for column in OFFER_COLUMNS] == [1, 0, 0, 0]
    assert [programs["Popular"][column] for column in OFFER_COLUMNS] == [1, 0, 0, 2]
    assert programs["Popular"]["Fichas del reporte"] == 3
    assert sum(row["Total anual"] for row in programs.values()) == 4
    # T1: continuación Menor 20 + Popular 3*15; nuevas 10+5 = 80 h/sem.
    # T2: Popular 3*25 + nuevas 20+15 = 110; T3: 3*35+25 = 130.
    # T4: Popular de T1 cursa edad 4 (35) y dos nuevas cursan edad 1 (2*5).
    assert [row["Horas requeridas"] for row in plan["quarterly"]] == [960, 1320, 1560, 540]
    assert [row["Horas requeridas"] for row in plan["monthly"]] == [320] * 3 + [440] * 3 + [520] * 3 + [180] * 3
    # Planta de Popular cubre 32 h/sem; los contratistas se comparten entre fichas.
    assert [row["contratistas_totales"] for row in plan["quarterly"]] == [2, 3, 3, 1]
    late = [row for row in plan["monthly_fichas"] if row["Cohorte"] == "Oferta T4"]
    assert {row["Trimestre de formación"] for row in late} == {1}
    assert {row["Mes número"] for row in late} == {10, 11, 12}
    assert {row["Fecha fin estimada"] for row in late} == {"2028-09-30"}
    assert len({row["Ficha"] for row in late}) == 2
    assert {(row["Desde T"], row["Hasta T"]) for row in plan["contract_windows"] if row["Perfil"] == "Menor"} == {(1, 2)}
    verify(plan)


def test_offer_tables_survive_save_reopen_and_excel_export(tmp_path, two_program_plan):
    staff, plan = two_program_plan
    path = tmp_path / "saved.sqlite3"
    save_planning(path, staff, plan)
    reopened_staff, reopened = load_planning(path)
    for key in ("offers_by_program", "offers_by_profile", "offer_basis"):
        assert reopened[key] == plan[key]
    content = BytesIO(export_planning(reopened_staff, reopened))
    for key, sheet in [("offers_by_program", "Fichas por oferta"), ("offers_by_profile", "Ofertas por jornada")]:
        pd.testing.assert_frame_equal(pd.read_excel(content, sheet_name=sheet), pd.DataFrame(plan[key]))
    assert pd.read_excel(content, sheet_name="Criterio de ofertas").iloc[0, 0] == plan["offer_basis"]


def test_zero_new_intakes_keep_program_rows_and_do_not_force_openings(two_program_plan):
    staff, previous = two_program_plan
    plan = execute_curriculum_plan(staff, previous["ficha_import"], previous["curriculum_catalog"],
                                   PlanningRules(), {"Técnico": 0, "Tecnólogo": 100}, 2027, "i.xlsx", "i")
    assert len(plan["offers_by_program"]) == 2
    assert all(row[column] == 0 for row in plan["offers_by_program"] for column in [*OFFER_COLUMNS, "Total anual"])
    assert [row["Fichas del reporte"] for row in plan["offers_by_program"]] == [1, 3]
    assert sum(row["Horas requeridas"] for row in plan["quarterly"]) > 0
    verify(plan)
