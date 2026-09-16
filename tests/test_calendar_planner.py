from io import BytesIO

import pandas as pd
import pytest

from core.calendar_planner import ENDING_COLUMNS, suggested_endings
from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.export import export_planning
from core.ficha_projection import duration_in_quarters, project_ficha_carryover
from core.level_planner import PROFILE_COLUMNS, execute_level_plan


def staff(heads=2):
    return pd.DataFrame([{"Especialidad": "SOFTWARE", "Área": "Técnica", "Nombre": f"Profe {i}",
                          "Documento": str(i), "Tipo Contrato": "Planta", "Es planta": True,
                          "Horas programadas actuales": 32} for i in range(heads)])


def profile(level="Tecnólogo", schedule="Diurna", passes=0, ends=0):
    return pd.DataFrame([{"Especialidad": "SOFTWARE", "Nivel": level, "Jornada": schedule,
                          "Fichas que pasan": passes, "Fichas que terminan": ends}])


def plan(frame=None, target=500, endings=None, rules=None):
    frame = profile() if frame is None else frame
    schedule = frame[PROFILE_COLUMNS].copy()
    for column, number in zip(ENDING_COLUMNS, endings or [0, 0, 0, 0]):
        schedule[column] = number
    return execute_level_plan(staff(), frame, rules or PlanningRules(),
                              {"Técnico": target if frame.iloc[0]["Nivel"] == "Técnico" else 0,
                               "Tecnólogo": target if frame.iloc[0]["Nivel"] == "Tecnólogo" else 0},
                              2027, "test.xlsx", "test", quarter_endings=schedule)


def test_annual_hours_respect_staggered_intakes_and_48_weeks():
    result = plan()
    assert [q["Fichas nuevas"] for q in result["quarterly"]] == [10, 5, 3, 2]
    assert [q["Fichas activas"] for q in result["quarterly"]] == [10, 15, 18, 20]
    assert result["center"]["demanda_total_horas_anuales"] == 63 * 30 * 12
    assert result["center"]["demanda_total_horas_anuales"] < 20 * 30 * 48
    assert result["levels"][1]["Horas anuales requeridas"] == 22680
    assert sum(row["Horas totales del trimestre"] for row in result["calendar"]) == 22680


def test_mixed_annual_components_use_26_18_4_4():
    result = plan(profile(schedule="Mixta"))
    center = result["center"]
    assert center["demanda_total_horas_anuales"] == 63 * 26 * 12
    assert center["demanda_tecnica_horas_anuales"] == 63 * 18 * 12
    assert center["demanda_bilinguismo_horas_anuales"] == 63 * 4 * 12
    assert center["demanda_integralidad_horas_anuales"] == 63 * 4 * 12


def test_replacements_keep_small_program_stable_without_extra_instructor():
    result = plan(profile(passes=2, ends=1), target=0, endings=[0, 1, 0, 0])
    assert [q["Fichas nuevas"] for q in result["quarterly"]] == [1, 0, 1, 0]
    assert [q["Fichas activas"] for q in result["quarterly"]] == [3, 3, 3, 3]
    # Dos instructores cubren 54 h; sumar todas las fichas del año daría 72 h erróneamente.
    assert all(row["Demanda técnica (h/sem)"] == 54 for row in result["technical_quarterly"])
    assert all(row["Contratistas requeridos"] == 0 for row in result["technical_quarterly"])
    assert result["center"]["demanda_total_horas_anuales"] == 3 * 30 * 48


def test_technical_three_quarters_and_t4_replacement_are_counted_once():
    result = plan(profile(level="Técnico"), target=50)
    assert [q["Fichas nuevas"] for q in result["quarterly"]] == [1, 1, 0, 1]
    assert [q["Fichas activas"] for q in result["quarterly"]] == [1, 2, 2, 2]
    assert result["center"]["demanda_total_horas_anuales"] == 7 * 30 * 12
    assert result["center"]["nuevas_adicionales_por_rotacion"] == 1
    assert result["center"]["reposiciones_siguiente_vigencia"] == 1  # Cohorte de T2 acaba en T4.
    assert result["center"]["fichas_al_cierre"] == 1


def test_q4_endings_are_deferred_without_duplicating_active_fichas():
    result = plan(profile(passes=2, ends=2), target=0, endings=[0, 0, 0, 2])
    assert [q["Fichas nuevas"] for q in result["quarterly"]] == [1, 0, 0, 0]
    assert result["center"]["reposiciones_siguiente_vigencia"] == 2
    assert result["center"]["fichas_al_cierre"] == 1
    assert result["growth_rule"]["replacement_fichas"] == 0


@pytest.mark.parametrize("schedule", ["O&P", "O&P-mañana", "P&O-tarde", "Diurna O&P"])
def test_op_always_ten_quarters_and_diurnal_even_with_old_override(schedule):
    assert duration_in_quarters("Tecnólogo", schedule, {schedule: 7}) == 10
    frame = pd.DataFrame([{"Ficha": "1", "Especialidad": "SOFTWARE", "Nivel": "Tecnólogo",
                           "Jornada": schedule, "Trimestre actual": 9}])
    detail, summary = project_ficha_carryover(frame, 2026, 4, 2027, group_by_profile=True)
    assert detail.iloc[0]["Trimestre fin estimado"] == 1
    assert summary.iloc[0]["Jornada"] == "Diurna O&P"
    frame.loc[0, "Trimestre actual"] = 10
    detail, _ = project_ficha_carryover(frame, 2026, 4, 2027, group_by_profile=True)
    assert not detail.iloc[0]["Pasa a la vigencia"]


def test_op_new_fichas_use_30_hours_and_remain_active_all_four_quarters():
    result = plan(profile(schedule="Diurna O&P"), target=25)
    assert [q["Fichas activas"] for q in result["quarterly"]] == [1, 1, 1, 1]
    assert result["center"]["demanda_total_horas_anuales"] == 30 * 48
    assert result["center"]["reposiciones_siguiente_vigencia"] == 0


def test_imported_finishes_and_manual_corrections_have_matching_totals():
    frame = profile(passes=3, ends=2)
    imported = {"detail": [{"Especialidad": "software .", "Nivel": "Tecnólogo", "Jornada de planeación": "Diurna",
                            "Termina en la vigencia": True, "Trimestre fin estimado": q} for q in [2, 4]]}
    assert suggested_endings(frame, imported)[ENDING_COLUMNS].iloc[0].tolist() == [0, 1, 0, 1]
    frame["Fichas que terminan"] = 3
    assert suggested_endings(frame, imported)[ENDING_COLUMNS].iloc[0].tolist() == [0, 2, 0, 1]


@pytest.mark.parametrize("endings", [[0, 0, 0, 0], [-1, 1, 1, 0], [0.5, 0.5, 0, 0]])
def test_invalid_quarterly_endings_cannot_execute(endings):
    with pytest.raises(ValueError, match="terminaciones|Terminan"):
        plan(profile(passes=1, ends=1), endings=endings)


def test_custom_calendar_changes_annual_hours_not_annual_target():
    result = plan(rules=PlanningRules(weeks_per_quarter=10, intake_weights=(100, 0, 0, 0)))
    assert result["center"]["fichas_nuevas"] == 20
    assert result["center"]["demanda_total_horas_anuales"] == 20 * 30 * 40
    with pytest.raises(ValueError, match="100"):
        plan(rules=PlanningRules(intake_weights=(50, 30, 20, 10)))


def test_quarterly_results_and_annual_hours_survive_sqlite_and_export(tmp_path):
    result = plan()
    path = tmp_path / "calendar.sqlite3"
    save_planning(path, staff(), result)
    instructors, saved = load_planning(path)
    assert saved["calendar"] == result["calendar"]
    assert saved["quarter_endings"] == result["quarter_endings"]
    assert saved["rules"]["weeks_per_quarter"] == 12
    book = pd.ExcelFile(BytesIO(export_planning(instructors, saved)))
    assert "Planta tecnica por trimestre" in book.sheet_names
    assert pd.read_excel(book, "Resumen trimestral")["Horas requeridas"].sum() == 22680
    assert pd.read_excel(book, "Metas por nivel")["Horas anuales requeridas"].sum() == 22680


def test_zero_targets_and_no_continuations_have_zero_annual_hours():
    result = plan(target=0)
    assert len(result["quarterly"]) == 4
    assert result["center"]["demanda_total_horas_anuales"] == 0
    assert result["summary"]["contratistas_totales"] == 0
