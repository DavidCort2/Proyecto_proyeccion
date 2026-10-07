from io import BytesIO

import pandas as pd
import pytest

from core.database import load_planning, save_planning
from core.export import export_planning
from core.virtual_schedule_planner import VirtualRules
from test_presencial_offers import scenario
from test_virtual_schedules import configured_catalog, person, plan
from test_virtual_technical_support import mixed_catalog, assert_single_capacity


def assert_complete_workday(result, *, virtual=False):
    for row in result["monthly_workload"]:
        capacity = row["Capacidad en horas" if virtual else "Capacidad (h/mes)"]
        plant = row["Vinculación" if virtual else "Tipo"] == "Planta"
        assert row["Horas totales programadas (h/mes)"] == pytest.approx(
            row["Horas de formación (h/mes)"] + row["Otras actividades (h/mes)"])
        assert row["Horas totales programadas (h/mes)"] <= capacity + 1e-7
        if plant:
            assert row["Horas totales programadas (h/mes)"] == capacity
            assert row["Horas sin programar (h/mes)"] == 0
            assert row["Horas totales programadas (h/sem)"] == pytest.approx(
                result["rules"]["weekly_plant_direct_hours"])
        else:
            assert row["Otras actividades (h/mes)"] == 0


@pytest.mark.parametrize("fichas,contracts", [(0, 0), (2, 0), (5, 1)])
def test_presencial_plant_has_full_workday_without_inventing_teaching_hours(tmp_path, fichas, contracts):
    _, result = scenario(tmp_path, [("Programa", "Diurna", 7, [1] * fichas or [7])], fichas * 25)
    assert_complete_workday(result)
    assert result["summary"]["pico_contratistas_total"] == contracts
    assert sum(r["Horas de formación (h/mes)"] for r in result["monthly_workload"]) == fichas * 10 * 48
    for row in result["monthly_workload"]:
        if row["Tipo"] == "Planta" and row["Área"] != "Técnica":
            assert row["Horas de formación (h/mes)"] == 0
            assert row["Otras actividades (h/mes)"] == row["Capacidad (h/mes)"]


@pytest.mark.parametrize("profile", ["Bilingüismo", "Cultura física", "Transversal general"])
def test_virtual_other_activities_never_replace_exclusive_teaching_profiles(tmp_path, profile):
    _, catalog = mixed_catalog(tmp_path, transversal_profile=profile)
    _, result = plan(catalog, plant=[person()])
    assert_complete_workday(result, virtual=True)
    assert_single_capacity(result)
    assert result["center"]["demanda_total_horas_anuales"] == 15
    assert result["summary"]["pico_contratistas_total"] == (0 if profile == "Transversal general" else 1)
    january = next(r for r in result["monthly_workload"] if r["Mes"] == 1 and r["Vinculación"] == "Planta")
    expected_teaching = 15 if profile == "Transversal general" else 10
    assert january["Horas de formación (h/mes)"] == expected_teaching
    assert january["Otras actividades (h/mes)"] == january["Capacidad en horas"] - expected_teaching
    # Al acabar las fichas, continúa la jornada completa de planta con otras actividades.
    assert all(r["Otras actividades (h/mes)"] == r["Capacidad en horas"]
               for r in result["monthly_workload"] if r["Mes"] > 1)


@pytest.mark.parametrize("weekly", [24, 32, 36])
def test_full_plant_workday_uses_configured_hours_even_without_fichas(tmp_path, weekly):
    _, catalog = configured_catalog(tmp_path)
    _, result = plan(catalog, plant=[person()], targets={"Técnico": 0, "Tecnólogo": 0},
                     rules=VirtualRules(weekly_plant_direct_hours=weekly))
    assert_complete_workday(result, virtual=True)
    assert result["center"]["demanda_total_horas_anuales"] == 0
    assert len(result["monthly_workload"]) == 12 and not result["contracts"]


@pytest.mark.parametrize("virtual", [False, True])
def test_workday_is_saved_and_visible_in_export_without_fake_ficha_assignments(tmp_path, virtual):
    if virtual:
        _, catalog = configured_catalog(tmp_path)
        staff, result = plan(catalog, plant=[person()])
        sheet = "Capacidad por instructor"
    else:
        staff, result = scenario(tmp_path, [("Programa", "Diurna", 7, [1])], 25)
        sheet = "Capacidad mensual instructores"
    path = tmp_path / "saved.sqlite3"
    save_planning(path, staff, result)
    saved = load_planning(path)
    assert saved[1]["monthly_workload"] == result["monthly_workload"]
    actual = pd.read_excel(BytesIO(export_planning(*saved)), sheet_name=sheet, dtype=str).fillna("")
    assert "Otras actividades (h/mes)" in actual.columns
    assert len(actual) == len(result["monthly_workload"])
    assert pd.to_numeric(actual["Otras actividades (h/mes)"]).sum() > 0
    assert not any("Otras actividades" in str(r) for r in result["monthly_assignments"])
