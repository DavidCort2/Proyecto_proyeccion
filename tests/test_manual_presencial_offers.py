from copy import deepcopy
from io import BytesIO

import pandas as pd
import pytest

from core.config import PlanningRules
from core.contracting_periods import contracting_headline
from core.curriculum_intakes import OFFER_COLUMNS
from core.curriculum_planner import execute_curriculum_plan
from core.curriculum_store import load_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from core.manual_presencial_offers import apply_manual_offers
from scripts.validate_curricula import verify
from test_curriculum import curriculum_catalog, curriculum_files, run_plan
from test_presencial_offers import scenario


def offer_input(plan, counts=None):
    rows = [{key: row[key] for key in ["Programa", "Nivel", *OFFER_COLUMNS]}
            for row in plan["offers_by_program"]]
    if counts is not None:
        for row, values in zip(rows, counts):
            row.update(zip(OFFER_COLUMNS, values))
    return {"planning_year": plan["planning_year"], "programs": rows}


def recalculate(staff, catalog, previous, offers):
    plan = execute_curriculum_plan(staff, previous["ficha_import"], catalog, PlanningRules(**previous["rules"]),
        previous["targets_by_level"], previous["planning_year"], previous["source_name"], previous["source_digest"],
        manual_offers=offers)
    verify(plan)
    return plan


def test_move_intakes_recalculates_curricular_hours_peak_and_contract_dates(curriculum_catalog):
    staff, before = run_plan(curriculum_catalog, target=250)
    after = recalculate(staff, curriculum_catalog, before, offer_input(before, [[0, 0, 0, 8]]))
    assert [row["Fichas nuevas"] for row in after["quarterly"]] == [0, 0, 0, 8]
    assert after["center"]["fichas_que_pasan"] == before["center"]["fichas_que_pasan"] == 2
    # Four diurna (30 h/week) and four mixta (26), one quarter instead of four.
    assert before["center"]["demanda_total_horas_anuales"] == 11424
    assert after["center"]["demanda_total_horas_anuales"] == 3360
    assert contracting_headline(after)["Trimestre del pico máximo"] == "T4"
    assert after["contract_windows"] != before["contract_windows"]
    assert after["monthly_assignments"] != before["monthly_assignments"]
    assert [row["Total anual"] for row in after["offers_by_profile"]] == [4, 4]


@pytest.mark.parametrize("new,expected_hours,shortfall,excess", [(0, 672, 50, 0), (1, 1032, 25, 0), (6, 2688, 0, 100)])
def test_changed_annual_total_updates_all_counts_and_target_coverage(curriculum_catalog, new, expected_hours, shortfall, excess):
    staff, before = run_plan(curriculum_catalog)
    after = recalculate(staff, curriculum_catalog, before, offer_input(before, [[0, 0, 0, new]]))
    assert after["center"]["fichas_nuevas"] == new
    assert after["center"]["aprendices_proyectados"] == (2 + new) * 25
    assert after["center"]["demanda_total_horas_anuales"] == expected_hours
    assert after["center"]["aprendices_sin_cobertura"] == shortfall
    assert after["center"]["aprendices_sobre_meta"] == excess
    assert sum(row["Fichas nuevas"] for row in after["distribution"]) == new
    assert sum(row["Fichas nuevas asignadas"] for row in after["intake_allocation"]) == new
    assert sum(row["Cupos nuevos"] for row in after["levels"]) == new * 25
    assert after["targets_by_level"] == before["targets_by_level"]
    assert after["ficha_import"] == before["ficha_import"]


def test_same_counts_preserve_hours_and_shift_allocation(curriculum_catalog):
    staff, before = run_plan(curriculum_catalog)
    after = recalculate(staff, curriculum_catalog, before, offer_input(before))
    for key in ("distribution", "monthly_fichas", "monthly_assignments", "contract_windows"):
        assert after[key] == before[key]
    pd.testing.assert_frame_equal(pd.DataFrame(after["offers_by_profile"]).drop(columns="Criterio de oferta"),
                                  pd.DataFrame(before["offers_by_profile"]).drop(columns="Criterio de oferta"))


@pytest.mark.parametrize("value", [-1, 1.5, True, None, float("nan"), float("inf"), "3"])
def test_invalid_counts_are_rejected_without_mutating_saved_inputs(curriculum_catalog, value):
    staff, before = run_plan(curriculum_catalog)
    original = deepcopy(before)
    offers = offer_input(before, [[value, 0, 0, 0]])
    with pytest.raises(ValueError, match="entera no negativa"):
        recalculate(staff, curriculum_catalog, before, offers)
    assert before == original


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "year"])
def test_stale_or_ambiguous_manual_table_is_rejected(curriculum_catalog, change):
    staff, before = run_plan(curriculum_catalog)
    offers = offer_input(before)
    if change == "missing":
        offers["programs"].clear()
    elif change == "duplicate":
        offers["programs"] *= 2
    elif change == "unknown":
        offers["programs"][0]["Programa"] = "Desconocido"
    else:
        offers["planning_year"] += 1
    with pytest.raises(ValueError):
        recalculate(staff, curriculum_catalog, before, offers)


def test_manual_inputs_save_reopen_export_and_restore_automatic(curriculum_catalog, tmp_path):
    staff, before = run_plan(curriculum_catalog)
    after = recalculate(staff, curriculum_catalog, before, offer_input(before, [[0, 0, 1, 0]]))
    path = tmp_path / "saved.sqlite3"
    save_planning(path, staff, after)
    stored_staff, stored = load_planning(path)
    replay = recalculate(stored_staff, curriculum_catalog, stored, stored["manual_offers"])
    assert replay == after
    book = BytesIO(export_planning(stored_staff, stored))
    pd.testing.assert_frame_equal(pd.read_excel(book, sheet_name="Fichas por oferta"), pd.DataFrame(after["offers_by_program"]), check_dtype=False)
    pd.testing.assert_frame_equal(pd.read_excel(book, sheet_name="Ofertas editadas"), pd.DataFrame(after["manual_offers"]["programs"]), check_dtype=False)
    assert recalculate(staff, curriculum_catalog, stored, None) == before


def test_manual_program_mapping_and_transitions_preserve_continuations(tmp_path):
    old = "DISEÑO E INTEGRACIÓN DE AUTOMATISMOS MECATRÓNICOS"
    new = "AUTOMATIZACION DE SISTEMAS MECATRONICOS"
    staff, before = scenario(tmp_path, [("Popular", "Diurna", 7, [1] * 10),
        (old, "Diurna", 7, [6]), (new, "Diurna", 7, [1]), ("Pequeño", "Diurna", 7, [6])], 400)
    catalog = load_curricula(tmp_path / "mallas.sqlite3")
    offers = offer_input(before)
    for row in offers["programs"]:
        row.update(zip(OFFER_COLUMNS, [0, 0, 0, 2 if row["Programa"] == new else 1]))
    after = recalculate(staff, catalog, before, offers)
    assert all(row["Fichas nuevas"] == 0 for row in after["distribution"] if row["Especialidad"] == old)
    assert after["center"]["fichas_que_pasan"] == before["center"]["fichas_que_pasan"]
    assert next(row for row in after["offers_by_program"] if row["Programa"] == new)["Oferta T4"] == 2
    offers["programs"].reverse()
    assert recalculate(staff, catalog, before, offers) == after


def test_presencial_manual_offers_cannot_enter_virtual_path():
    with pytest.raises(ValueError, match="no se aplica a virtual"):
        apply_manual_offers({}, {"input_mode": "virtual_manual"}, {})
