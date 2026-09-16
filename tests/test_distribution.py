from io import BytesIO

import pandas as pd
import pytest

from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.export import export_planning
from core.planner import growth_requirements, suggested_ficha_distribution
from core.workflow import execute_plan, project_distribution, validate_distribution


def distribution(passing=(60, 30, 10), ending=(0, 0, 0)):
    return pd.DataFrame({
        "Especialidad": [f"Programa {i}" for i in range(len(passing))],
        "Fichas que pasan": list(passing), "Fichas que terminan": list(ending),
    })


@pytest.mark.parametrize("target,expected", [(0, [3, 2, 1]), (4, [3, 2, 1]), (6, [3, 2, 1]), (20, [12, 6, 2])])
def test_growth_without_endings_is_always_covered(target, expected):
    manual = distribution()
    result = suggested_ficha_distribution(manual, target)
    assert result["Fichas nuevas"].tolist() == expected
    assert result["Fichas que pasan"].tolist() == [60, 30, 10]
    assert "Fichas nuevas" not in manual


def test_replacements_and_growth_exceed_an_insufficient_target():
    result = suggested_ficha_distribution(distribution(ending=(2, 10, 3)), 6)
    assert result["Fichas nuevas"].tolist() == [5, 12, 4]
    assert result["Fichas nuevas"].sum() == 21
    assert result["Fichas que terminan"].tolist() == [2, 10, 3]


def test_remaining_target_is_distributed_proportionally_after_minimums():
    result = suggested_ficha_distribution(distribution(ending=(2, 10, 3)), 35)
    # Saldo de 14: cuotas 8.4, 4.2, 1.4 → 9, 4, 1 (primer programa en el empate).
    assert result["Fichas nuevas"].tolist() == [14, 16, 5]
    assert result["Fichas nuevas"].sum() == 35


def test_small_programs_round_growth_up_individually():
    rule = growth_requirements(distribution((1, 5, 21, 0), (0, 2, 21, 0)))
    assert [row["Crecimiento mínimo (5 %)"] for row in rule["rows"]] == [1, 1, 2, 0]
    assert rule["new_fichas"] == 27  # 23 reposiciones + 4 crecimiento.


def test_zero_continuations_use_even_allocation():
    manual = distribution((0, 0), (0, 0))
    assert suggested_ficha_distribution(manual, 5)["Fichas nuevas"].tolist() == [3, 2]
    assert suggested_ficha_distribution(manual, 0)["Fichas nuevas"].sum() == 0


def test_empty_catalog_requires_specialties_for_positive_target():
    manual = distribution((), ())
    assert suggested_ficha_distribution(manual, 0).empty
    with pytest.raises(ValueError, match="especialidad"):
        suggested_ficha_distribution(manual, 2)


@pytest.mark.parametrize("column,value", [
    ("Fichas que pasan", None), ("Fichas que pasan", -1), ("Fichas que pasan", 1.5),
    ("Fichas que terminan", -1), ("Fichas que terminan", 1.5), ("Fichas que terminan", 21),
])
def test_manual_counts_must_be_valid(column, value):
    frame = distribution((20,), (8,)).astype(object)
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        project_distribution(frame, pd.DataFrame({"Especialidad": ["Programa 0"]}), 50, 25)


def test_projection_invariants_for_varied_targets_and_continuations():
    # Cubre metas por debajo, iguales y por encima del mínimo, incluyendo ceros.
    for passing in [(0, 0, 0), (1, 2, 3), (7, 21, 100), (100, 25, 1)]:
        ending = tuple(value // 2 for value in passing)
        minimum = [end + (count + 19) // 20 for count, end in zip(passing, ending)]
        for target in [0, 1, 5, sum(minimum), sum(minimum) + 37]:
            result = suggested_ficha_distribution(distribution(passing, ending), target)
            new = result["Fichas nuevas"].tolist()
            assert sum(new) == max(target, sum(minimum))
            assert all(actual >= required for actual, required in zip(new, minimum))
            assert result["Fichas que pasan"].tolist() == list(passing)
            assert result["Fichas que terminan"].tolist() == list(ending)


def test_saved_plan_and_export_use_actual_projection_not_target(tmp_path):
    instructors = pd.DataFrame([{
        "Especialidad": "Programa 0", "Área": "Técnica", "Nombre": "Ana", "Documento": "001",
        "Tipo Contrato": "Planta", "Es planta": True, "Horas programadas actuales": 32.0,
    }])
    manual = distribution((20,), (8,))
    manual["Fichas nuevas"] = 999  # Un cálculo anterior no puede saltarse la proyección actual.
    execution = execute_plan(instructors, manual, PlanningRules(), 26, 2027, "reporte.xlsx", "abc")
    center = execution["center"]
    assert center["meta_aprendices"] == 26
    assert center["fichas_segun_meta"] == 2
    assert center["fichas_nuevas"] == 9
    assert center["fichas_adicionales_sobre_meta"] == 7
    assert center["aprendices_proyectados"] == 225
    assert center["fichas_activas"] == 29
    assert center["fichas_al_cierre"] == 21
    assert center["demanda_total_horas_semana"] == 29 * 30
    assert execution["technical"][0]["Demanda técnica (h/sem)"] == 29 * 18
    assert [row["Demanda (h/sem)"] for row in execution["transversal"]] == [29 * 6, 29 * 6]
    assert execution["summary"]["contratistas_totales"] == 23  # 13 técnicos + 5 + 5.
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors, execution)
    loaded, saved = load_planning(db)
    assert saved["target_learners"] == 26
    assert saved["distribution"][0]["Fichas nuevas"] == 9
    workbook = pd.ExcelFile(BytesIO(export_planning(loaded, saved)))
    exported = pd.read_excel(workbook, sheet_name="Distribucion")
    assert exported["Fichas que pasan"].tolist() == [20]
    assert exported["Fichas que terminan"].tolist() == [8]
    assert exported["Fichas nuevas"].tolist() == [9]
    summary = pd.read_excel(workbook, sheet_name="Resumen planeacion").iloc[0]
    assert summary["meta_aprendices"] == 26
    assert summary["fichas_nuevas"] == 9
    assert "Regla reposicion y crecimiento" in workbook.sheet_names
