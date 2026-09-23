"""Casos aritméticos independientes: la meta no fija una cuota de instructores."""
from dataclasses import replace

import pandas as pd
import pytest

from core.config import PlanningRules
from core.curriculum_intakes import project_curricular_intakes
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.planner import technical_staffing_plan, transversal_staffing_plan
from test_curriculum import PROGRAM, ficha_frame, instructors_frame
from test_curriculum_automation import malla


def scenario(tmp_path, *, hours=(11, 27, 8, 19), target=75, plants=1, contractors=0, capacity=17,
             learners=25, current=1, offers=(100, 0, 0, 0), rules=None):
    catalog = import_curricula(tmp_path / "audit.sqlite3", [(PROGRAM + " - DIURNA.xlsx", malla(hours))])
    staff = instructors_frame().iloc[:1].copy()
    staff = pd.concat([staff.assign(Nombre=f"Planta {i}", Documento=f"P{i}") for i in range(plants)], ignore_index=True) if plants else staff.iloc[:0]
    # Un reporte puede tener solo contratistas. Su número y horas programadas no son capacidad de planta.
    historical = instructors_frame().iloc[:1].assign(**{"Es planta": False, "Tipo Contrato": "Contratista"})
    staff = pd.concat([staff, *[historical.assign(Nombre=f"Anterior {i}", Documento=f"C{i}")
                               for i in range(max(contractors, int(plants == 0)))]], ignore_index=True)
    imported = prepare_ficha_import(ficha_frame(day_age=current).iloc[:1], staff, catalog, 2027, "fichas.xlsx", "test", 2026, 4)
    rules = rules or PlanningRules(learners_per_ficha=learners, weekly_plant_direct_hours=23,
                                   weekly_contractor_hours=capacity, weeks_per_quarter=10, intake_weights=offers)
    plan = execute_curriculum_plan(staff, imported, catalog, rules, {"Técnico": 0, "Tecnólogo": target}, 2027, "planta.xlsx", "test")
    return plan, staff, imported, catalog


@pytest.mark.parametrize("factor,plants,capacity,learners,weekly,heads", [
    (1, 1, 17, 25, [49, 62, 35, 38], [2, 3, 1, 1]),
    (2, 1, 17, 25, [98, 124, 70, 76], [5, 6, 3, 4]),
    (1, 3, 17, 25, [49, 62, 35, 38], [0, 0, 0, 0]),
    (1, 1, 31, 25, [49, 62, 35, 38], [1, 2, 1, 1]),
    (1, 1, 17, 20, [60, 89, 43, 57], [3, 4, 2, 2]),
])
def test_same_target_changes_with_malla_plant_and_configured_capacity(tmp_path, factor, plants, capacity, learners, weekly, heads):
    # Meta 75; con 25 aprendices/ficha: una continuación y dos nuevas en T1.
    # Continuación: 27,8,19,0. Nuevas: 2*(11,27,8,19). Capacidad planta=23.
    plan, *_ = scenario(tmp_path, hours=[factor * h for h in [11, 27, 8, 19]], plants=plants, capacity=capacity, learners=learners)
    assert plan["center"]["meta_aprendices"] == 75
    assert [r["Horas requeridas"] for r in plan["quarterly"]] == [h * 10 for h in weekly]
    assert [r["contratistas_totales"] for r in plan["quarterly"]] == heads
    assert plan["summary"]["pico_contratistas_total"] == max(heads)
    assert sum(r["Horas asignadas (h/mes)"] for r in plan["monthly_assignments"]) == pytest.approx(sum(weekly) * 10)


@pytest.mark.parametrize("target,new,heads", [
    (0, 0, [1, 0, 0, 0]), (24, 0, [1, 0, 0, 0]), (25, 0, [1, 0, 0, 0]),
    (26, 1, [1, 1, 1, 0]), (50, 1, [1, 1, 1, 0]),
    (51, 2, [2, 3, 1, 1]), (75, 2, [2, 3, 1, 1]), (83, 3, [3, 4, 2, 2]),
])
def test_target_only_changes_whole_fichas_needed_after_carryover(tmp_path, target, new, heads):
    plan, *_ = scenario(tmp_path, target=target)
    assert plan["center"]["fichas_que_pasan"] == 1
    assert plan["center"]["fichas_nuevas"] == new
    assert [r["contratistas_totales"] for r in plan["quarterly"]] == heads
    assert plan["center"]["nuevas_adicionales_por_rotacion"] == 0
    assert "growth_rule" not in plan


def test_high_target_with_zero_curriculum_hours_does_not_force_contractors(tmp_path):
    plan, *_ = scenario(tmp_path, hours=[0] * 4, target=1379, plants=0)
    assert plan["center"]["fichas_nuevas"] == 55
    assert plan["center"]["demanda_total_horas_anuales"] == 0
    assert plan["summary"]["pico_contratistas_total"] == 0
    assert plan["contract_windows"] == []


def test_peak_follows_curriculum_and_offer_dates_not_a_fixed_quarter(tmp_path):
    early, *_ = scenario(tmp_path)
    late, *_ = scenario(tmp_path, current=4, offers=(0, 0, 0, 100))
    assert early["summary"]["trimestres_pico_total"] == [2]
    assert late["summary"]["trimestres_pico_total"] == [4]
    assert [r["Horas requeridas"] for r in late["quarterly"]] == [0, 0, 0, 330]
    assert all(r["Inicio"] == "2027-10-01" for r in late["contract_windows"])


@pytest.mark.parametrize("historical_count", [0, 68, 173])
def test_existing_contractors_never_anchor_the_result(tmp_path, historical_count):
    plan, *_ = scenario(tmp_path, contractors=historical_count)
    assert [r["contratistas_totales"] for r in plan["quarterly"]] == [2, 3, 1, 1]
    assert plan["center"]["demanda_total_horas_anuales"] == 1840


def test_automatic_path_cannot_execute_historical_business_rules(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("El cálculo automático invocó reglas históricas o referencias horarias")

    for name in ["core.level_planner.execute_level_plan", "core.level_planner._execute_unscheduled_plan",
                 "core.level_planner.project_by_level", "core.level_planner.hours_by_profile",
                 "core.calendar_planner.hours_by_profile", "core.calendar_planner.duration_in_quarters",
                 "core.ficha_projection.duration_in_quarters", "core.planner.growth_requirements",
                 "core.planner.calculate_center_plan", "core.planner.suggested_ficha_distribution",
                 "core.transversal_capacity.apply_transversal_capacity", "core.config.PlanningRules.validate"]:
        monkeypatch.setattr(name, forbidden)
    monkeypatch.setattr(PlanningRules, "weekly_technical_hours", property(forbidden))
    monkeypatch.setattr(PlanningRules, "mixed_weekly_technical_hours", property(forbidden))
    rules = PlanningRules(weekly_plant_direct_hours=23, weekly_contractor_hours=17, weeks_per_quarter=10, intake_weights=(100, 0, 0, 0))
    # Incluso referencias incompatibles con el modelo anterior quedan fuera del recorrido.
    rules = replace(rules, weekly_hours_per_ficha=0, mixed_weekly_hours_per_ficha=0)
    plan, *_ = scenario(tmp_path, rules=rules)
    assert [r["contratistas_totales"] for r in plan["quarterly"]] == [2, 3, 1, 1]


def test_unmatched_program_weights_are_rejected_instead_of_using_uniform_defaults(tmp_path):
    _, _, imported, _ = scenario(tmp_path)
    manual = pd.DataFrame(imported["summary"])
    manual["Especialidad"] = "Programa que no aparece en el reporte"
    with pytest.raises(ValueError, match="proporciones predeterminadas"):
        project_curricular_intakes(manual, imported, {"Técnico": 0, "Tecnólogo": 75}, PlanningRules())


@pytest.mark.parametrize("target", [-1, 25.5, float("nan"), float("inf"), True])
def test_invalid_targets_are_not_silently_truncated(tmp_path, target):
    with pytest.raises(ValueError, match="metas de aprendices enteras"):
        scenario(tmp_path, target=target)


@pytest.mark.parametrize("change", [
    {"weekly_contractor_hours": float("nan")}, {"weekly_plant_direct_hours": float("inf")},
    {"learners_per_ficha": 25.5}, {"weeks_per_quarter": 0}, {"intake_weights": (100, 0, 0, float("nan"))},
])
def test_invalid_capacity_and_offer_inputs_cannot_produce_a_result(tmp_path, change):
    with pytest.raises(ValueError):
        scenario(tmp_path, rules=replace(PlanningRules(), **change))


def test_missing_hours_cannot_be_filled_with_nominal_load_or_zero():
    staff = instructors_frame()
    distribution = pd.DataFrame([{"Especialidad": PROGRAM, "Fichas nuevas": 1, "Fichas que pasan": 0}])
    with pytest.raises(ValueError, match="Faltan horas"):
        technical_staffing_plan(staff, distribution, PlanningRules(), demand_by_specialty={})
    with pytest.raises(ValueError, match="Faltan horas"):
        transversal_staffing_plan(staff, 1, PlanningRules(), demand_by_area={"Bilingüismo": 0})
    exact_zero = technical_staffing_plan(staff, distribution, PlanningRules(), demand_by_specialty={PROGRAM: 0})
    assert exact_zero["Contratistas requeridos"].tolist() == [0]
