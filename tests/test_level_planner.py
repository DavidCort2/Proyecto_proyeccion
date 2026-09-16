from io import BytesIO

import pandas as pd
import pytest

from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.export import export_planning
from core.ficha_projection import project_ficha_carryover
from core.fichas_parser import parse_fichas_excel
from core.level_planner import execute_level_plan


def instructors(heads=1):
    return pd.DataFrame([{
        "Especialidad": "ADSO", "Área": "Técnica", "Nombre": f"Instructor {index}",
        "Documento": str(index), "Tipo Contrato": "Planta", "Es planta": True,
        "Horas programadas actuales": 32.0,
    } for index in range(heads)])


def manual():
    return pd.DataFrame([
        {"Especialidad": "ADSO", "Nivel": "Técnico", "Jornada": "Diurna", "Fichas que pasan": 0, "Fichas que terminan": 0},
        {"Especialidad": "ADSO", "Nivel": "Tecnólogo", "Jornada": "Mixta", "Fichas que pasan": 0, "Fichas que terminan": 0},
    ])


def run(frame=None, technical=25, technologist=25, heads=1):
    return execute_level_plan(instructors(heads), manual() if frame is None else frame,
                              PlanningRules(), {"Técnico": technical, "Tecnólogo": technologist}, 2027, "reporte.xlsx", "abc")


def test_separate_targets_round_independently_and_do_not_mix_levels():
    result = run(technical=26, technologist=26)
    assert [row["Fichas según meta"] for row in result["levels"]] == [2, 2]
    assert [row["Fichas nuevas"] for row in result["distribution"]] == [3, 2]
    assert result["center"]["fichas_segun_meta"] == 4
    assert result["center"]["demanda_total_horas_semana"] == 112
    result = run(technical=75, technologist=0)
    assert [row["Fichas nuevas"] for row in result["distribution"]] == [5, 0]


def test_mixed_hours_and_capacity_are_shared_once_across_levels():
    result = run()
    center = result["center"]
    assert center["demanda_total_horas_semana"] == 56
    assert center["demanda_tecnica_horas_semana"] == 36
    assert center["demanda_bilinguismo_horas_semana"] == 10
    assert center["demanda_integralidad_horas_semana"] == 10
    assert [row["Demanda (h/sem)"] for row in result["transversal"]] == [10, 10]
    assert len(result["technical"]) == 1
    technical = result["technical"][0]
    assert technical["Capacidad planta (h/sem)"] == 32
    assert technical["Horas atendidas por planta (h/sem)"] == 32
    assert technical["Déficit antes de contratar (h/sem)"] == 4
    assert technical["Capacidad equivalente planta (fichas)"] == pytest.approx(32 / 18)
    assert technical["Instructores equivalentes requeridos"] == 1.125


def test_two_instructors_cover_three_fichas_without_one_instructor_per_ficha():
    result = run(technical=50, technologist=25, heads=2)
    technical = result["technical"][0]
    assert technical["Fichas activas"] == 3
    assert technical["Demanda técnica (h/sem)"] == 54
    assert technical["Capacidad planta (h/sem)"] == 64
    assert technical["Contratistas requeridos"] == 0
    assert technical["Horas disponibles planta (h/sem)"] == 10


def test_growth_is_rounded_once_per_specialty_and_level_not_per_schedule():
    frame = manual()
    frame["Nivel"] = "Técnico"
    frame["Fichas que pasan"] = [10, 10]
    frame["Fichas que terminan"] = [2, 3]
    result = run(frame, technical=0, technologist=0)
    assert result["growth_rule"]["growth_fichas"] == 1
    assert result["center"]["fichas_nuevas"] == 7  # 5 reposiciones, 1 crecimiento, 1 rotación en T4.
    assert result["center"]["fichas_adicionales_sobre_meta"] == 7
    assert sum(row["Fichas nuevas"] for row in result["distribution"]) == 7
    assert all(row["Fichas nuevas"] >= row["Fichas que terminan"] for row in result["distribution"])


def test_excess_in_one_level_never_covers_the_other_target():
    frame = manual()
    frame.loc[0, ["Fichas que pasan", "Fichas que terminan"]] = [20, 20]
    result = run(frame, technical=25, technologist=25)
    assert [row["Fichas nuevas"] for row in result["distribution"]] == [17, 1]
    assert [row["Fichas sobre la meta"] for row in result["levels"]] == [16, 0]


def test_missing_level_is_not_inferred_from_specialty_name():
    with pytest.raises(ValueError, match="Tecnólogo"):
        run(manual().iloc[:1])
    frame = manual()
    frame.loc[0, "Nivel"] = None
    with pytest.raises(ValueError, match="Seleccione"):
        run(frame)


def test_capacity_cannot_be_transferred_between_different_specialties():
    frame = manual()
    frame.loc[1, "Especialidad"] = "SIN PLANTA"
    result = run(frame)
    tech = {row["Especialidad"]: row for row in result["technical"]}
    assert tech["ADSO"]["Horas disponibles planta (h/sem)"] == 14
    assert tech["SIN PLANTA"]["Capacidad planta (h/sem)"] == 0
    assert tech["SIN PLANTA"]["Déficit antes de contratar (h/sem)"] == 18


def test_totals_equal_components_for_continuing_and_new_fichas():
    frame = manual()
    frame["Fichas que pasan"] = [3, 5]
    frame["Fichas que terminan"] = [1, 2]
    result = run(frame, technical=100, technologist=150)
    center = result["center"]
    assert center["demanda_total_horas_semana"] == 6 * 30 + 9 * 26
    assert center["demanda_total_horas_anuales"] == sum(center[key] for key in [
        "demanda_tecnica_horas_anuales", "demanda_bilinguismo_horas_anuales", "demanda_integralidad_horas_anuales"])
    assert center["demanda_total_horas_anuales"] == sum(row["Horas requeridas"] for row in result["quarterly"])


def test_import_keeps_levels_and_shift_counts():
    from pathlib import Path
    frame = parse_fichas_excel(Path(__file__).resolve().parents[1] / "data/reporteFichas_2026_4.xlsx")
    detail, grouped = project_ficha_carryover(frame, 2026, 4, 2027, {"P&O-MANANA": 7, "P&O-TARDE": 7}, group_by_profile=True)
    assert grouped["Fichas que pasan"].sum() == 54
    assert set(grouped["Nivel"]) == {"Técnico", "Tecnólogo"}
    assert set(grouped["Jornada"]) == {"Diurna", "Mixta", "Diurna O&P"}
    for level in grouped["Nivel"].unique():
        assert grouped.loc[grouped["Nivel"] == level, "Fichas que pasan"].sum() == detail.loc[detail["Nivel"] == level, "Pasa a la vigencia"].sum()


def test_save_export_retains_both_targets_and_shift_hours(tmp_path):
    execution = run(technical=50, technologist=75)
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors(), execution)
    loaded, saved = load_planning(db)
    assert saved["targets_by_level"] == {"Técnico": 50, "Tecnólogo": 75}
    assert saved["hours"] == execution["hours"]
    workbook = pd.ExcelFile(BytesIO(export_planning(loaded, saved)))
    assert pd.read_excel(workbook, sheet_name="Metas por nivel")["Meta de aprendices"].tolist() == [50, 75]
    assert set(pd.read_excel(workbook, sheet_name="Distribucion")["Jornada"]) == {"Diurna", "Mixta"}
    assert pd.read_excel(workbook, sheet_name="Horas por nivel y jornada")["Horas totales (h/sem)"].sum() == 138


def test_mixed_rules_validation():
    assert PlanningRules().mixed_weekly_technical_hours == 18
    assert PlanningRules(mixed_weekly_hours_per_ficha=7).validate()
