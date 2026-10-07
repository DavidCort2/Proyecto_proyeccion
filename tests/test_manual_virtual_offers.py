from copy import deepcopy
from io import BytesIO
import json

import pandas as pd
import pytest

from core.database import load_planning, save_planning
from core.export import export_planning
from core.manual_virtual_offers import OFFER_COLUMNS
from test_virtual_schedules import configured_catalog, plan


def offers(counts, year=2027):
    return {"planning_year": year, "programs": [
        {"Programa": "Software", "Nivel": "Tecnólogo", **dict(zip(OFFER_COLUMNS, counts))}]}


def test_move_virtual_offers_rebuilds_phases_hours_and_contracts(tmp_path):
    _, catalog = configured_catalog(tmp_path, durations=(100, 100, 100))
    _, original = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 100})
    _, changed = plan(catalog, targets=original["targets_by_level"], manual_offers=offers([0, 0, 0, 4]))
    assert changed["center"]["fichas_nuevas"] == 4
    assert changed["center"]["demanda_total_horas_anuales"] < original["center"]["demanda_total_horas_anuales"]
    assert changed["cohort_dates"][0]["Fecha inicio lectiva estimada"] == "2027-10-01"
    assert changed["cohort_dates"][0]["Fecha fin lectiva"] == "2028-07-26"
    assert [r["Fichas nuevas"] for r in changed["quarterly"]] == [0, 0, 0, 4]
    assert min(r["Inicio"] for r in changed["contracts"]) == "2027-10-01"
    assert all(r["Mes"] >= 10 for r in changed["monthly_assignments"])
    assert changed["targets_by_level"] == original["targets_by_level"]


@pytest.mark.parametrize("new,shortfall,excess", [(0, 50, 0), (1, 25, 0), (5, 0, 75)])
def test_manual_virtual_total_keeps_carryovers_and_reports_actual_goal_coverage(tmp_path, new, shortfall, excess):
    _, catalog = configured_catalog(tmp_path)
    args = dict(targets={"Técnico": 0, "Tecnólogo": 100}, cohorts=[
        {"Programa": "Software", "Fichas que pasan": 2, "Fecha fin lectiva": "2027-01-14"}])
    _, original = plan(catalog, **args)
    _, result = plan(catalog, **args, manual_offers=offers([0, 0, 0, new]))
    assert result["center"]["fichas_que_pasan"] == 2
    assert result["center"]["fichas_nuevas"] == new
    assert result["center"]["aprendices_proyectados"] == (2 + new) * 25
    assert result["center"]["aprendices_sin_cobertura"] == shortfall
    assert result["center"]["aprendices_sobre_meta"] == excess
    assert result["center"]["demanda_total_horas_anuales"] == 30 + new * 25
    assert result["cohort_dates"][0] == original["cohort_dates"][0]
    assert sum(r["Fichas nuevas"] for r in result["distribution"]) == new
    assert sum(r["Fichas nuevas"] for r in result["levels"]) == new


def test_manual_virtual_same_counts_and_restoring_leave_auto_calculation_unchanged(tmp_path):
    _, catalog = configured_catalog(tmp_path)
    _, automatic = plan(catalog)
    _, manual = plan(catalog, manual_offers=offers([1, 0, 0, 0]))
    for key in ("cohort_dates", "monthly_assignments", "monthly_instructors", "contracts", "offers_by_program", "summary"):
        assert manual[key] == automatic[key]
    _, restored = plan(catalog, manual_offers=None)
    assert restored == automatic


@pytest.mark.parametrize("value", [-1, 1.5, True, None, float("nan"), float("inf"), "3"])
def test_virtual_editor_rejects_invalid_counts_without_mutating_catalog(tmp_path, value):
    _, catalog = configured_catalog(tmp_path)
    original = deepcopy(catalog)
    with pytest.raises(ValueError, match="enteras no negativas"):
        plan(catalog, manual_offers=offers([value, 0, 0, 0]))
    assert catalog == original


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "level", "year", "column"])
def test_virtual_editor_rejects_stale_tables(tmp_path, change):
    _, catalog = configured_catalog(tmp_path)
    manual = offers([1, 0, 0, 0])
    if change == "missing":
        manual["programs"].clear()
    elif change == "duplicate":
        manual["programs"] *= 2
    elif change == "unknown":
        manual["programs"][0]["Programa"] = "Otro"
    elif change == "level":
        manual["programs"][0]["Nivel"] = "Técnico"
    elif change == "column":
        del manual["programs"][0]["Oferta 1"]
    else:
        manual["planning_year"] += 1
    with pytest.raises(ValueError):
        plan(catalog, manual_offers=manual)


def test_saved_virtual_offers_are_replayable_and_exported(tmp_path):
    path, catalog = configured_catalog(tmp_path)
    staff, result = plan(catalog, manual_offers=offers([0, 2, 0, 3]))
    save_planning(path, staff, result)
    saved_staff, saved = load_planning(path)
    _, replayed = plan(catalog, manual_offers=saved["manual_offers"])
    assert json.loads(json.dumps(replayed)) == {k: v for k, v in saved.items() if k != "saved_at"}
    workbook = pd.ExcelFile(BytesIO(export_planning(saved_staff, saved)))
    assert workbook.parse("Ofertas editadas")[OFFER_COLUMNS].iloc[0].tolist() == [0, 2, 0, 3]
    assert workbook.parse("Fichas por oferta")["Total anual"].sum() == 5
    assert workbook.parse("Contratistas y fechas")["Inicio"].tolist() == [r["Inicio"] for r in result["contracts"]]
