import pandas as pd

from core.config import PlanningRules
from core.planner import (
    calculate_center_plan,
    fichas_from_target,
    largest_remainder_allocation,
    staffing_summary,
    technical_staffing_plan,
    transversal_staffing_plan,
)


def sample_instructors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Área": "Técnica", "Especialidad": "ADSO", "Nombre": "A", "Es planta": True},
            {"Área": "Técnica", "Especialidad": "ADSO", "Nombre": "B", "Es planta": True},
            {"Área": "Técnica", "Especialidad": "METROLOGIA", "Nombre": "C", "Es planta": True},
            {"Área": "Bilingüismo", "Especialidad": "Bilingüismo", "Nombre": "D", "Es planta": True},
            {"Área": "Integralidad", "Especialidad": "Integralidad", "Nombre": "E", "Es planta": True},
        ]
    )


def test_fichas_round_up():
    assert fichas_from_target(0, 25) == 0
    assert fichas_from_target(25, 25) == 1
    assert fichas_from_target(26, 25) == 2


def test_center_plan_default_rules():
    rules = PlanningRules()
    result = calculate_center_plan(100, 2, 10, rules)
    assert result["fichas_nuevas"] == 4
    assert result["fichas_activas"] == 6
    assert result["demanda_total_horas_semana"] == 180
    assert result["demanda_tecnica_horas_semana"] == 108
    assert result["capacidad_planta_horas_semana"] == 320
    assert result["saldo_planta_horas_semana"] == 140


def test_largest_remainder_preserves_total():
    allocation = largest_remainder_allocation(10, ["A", "B", "C"], [3, 2, 1])
    assert sum(allocation.values()) == 10


def test_contractors_are_calculated_by_specialty():
    rules = PlanningRules()
    df = sample_instructors()
    distribution = pd.DataFrame(
        [
            {"Especialidad": "ADSO", "Fichas nuevas": 6, "Fichas que pasan": 0},
            {"Especialidad": "METROLOGIA", "Fichas nuevas": 2, "Fichas que pasan": 0},
        ]
    )
    result = technical_staffing_plan(df, distribution, rules)

    adso = result.loc[result["Especialidad"] == "ADSO"].iloc[0]
    # 6 fichas * 18h = 108h. Planta ADSO: 2 * 32 = 64h. Déficit 44h => 2 contratistas.
    assert adso["Déficit antes de contratar (h/sem)"] == 44
    assert adso["Contratistas requeridos"] == 2

    metro = result.loc[result["Especialidad"] == "METROLOGIA"].iloc[0]
    # 2 * 18 = 36h. Planta 32h. Déficit 4h => 1 contratista.
    assert metro["Contratistas requeridos"] == 1


def test_transversal_contractors_and_summary():
    rules = PlanningRules()
    df = sample_instructors()
    distribution = pd.DataFrame(
        [{"Especialidad": "ADSO", "Fichas nuevas": 8, "Fichas que pasan": 0}]
    )
    technical = technical_staffing_plan(df, distribution, rules)
    transversal = transversal_staffing_plan(df, 8, rules)

    # Cada transversal: 8*6=48; planta=32; déficit=16 => 1 contratista.
    assert transversal["Contratistas requeridos"].tolist() == [1, 1]

    summary = staffing_summary(technical, transversal, rules)
    # ADSO: 144-64=80 => 2; + 1 bilingüismo + 1 integralidad = 4.
    assert summary["contratistas_totales"] == 4
