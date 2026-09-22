from io import BytesIO

import pandas as pd
import pytest

from core.config import PlanningRules
from core.database import save_planning, load_planning
from core.excel_parser import parse_instructors_excel
from core.export import export_planning
from core.ficha_projection import project_ficha_carryover
from core.level_planner import execute_level_plan
from core.planner import transversal_staffing_plan
from core.transversal_capacity import current_transversal_capacity, suggested_continuity, apply_transversal_capacity, validate_continuity
from core.transversal_modules import module_template, validate_modules


def profile(passes=0, ends=0):
    return pd.DataFrame([{"Especialidad": "SOFTWARE", "Nivel": "Tecnólogo", "Jornada": "Diurna",
                          "Fichas que pasan": passes, "Fichas que terminan": ends}])


def curriculum(manual):
    table = module_template(manual)
    table[["Bilingüismo (h)", "Integralidad (h)"]] = 0.0
    table.loc[table["Trimestre de formación"] == 1, "Bilingüismo (h)"] = 12.0
    table.loc[table["Trimestre de formación"] == 2, "Integralidad (h)"] = 24.0
    return table


def execute(instructors, manual=None, modules=None, imported=None):
    manual = profile() if manual is None else manual
    return execute_level_plan(instructors, manual, PlanningRules(), {"Técnico": 0, "Tecnólogo": 50},
                              2027, "test.xlsx", "test", ficha_import=imported,
                              transversal_modules=curriculum(manual) if modules is None else modules)


def test_current_report_spare_capacity_is_not_treated_as_future_demand(report_path):
    instructors = parse_instructors_excel(report_path)
    rows = current_transversal_capacity(instructors, PlanningRules()).set_index("Área")
    assert rows.loc["Bilingüismo", "Contratistas actuales"] == 7
    assert rows.loc["Integralidad", "Contratistas actuales"] == 9
    assert rows.loc["Bilingüismo", "Horas programadas del reporte (h/sem)"] == 215
    assert rows.loc["Integralidad", "Horas programadas del reporte (h/sem)"] == 200
    assert rows.loc["Bilingüismo", "Horas libres actuales (h/sem)"] == 97
    assert rows.loc["Integralidad", "Horas libres actuales (h/sem)"] == 192


def test_27_total_contractors_are_not_27_additional(report_path):
    instructors = parse_instructors_excel(report_path)
    rules = PlanningRules()
    trans = transversal_staffing_plan(instructors, 127, rules, demand_by_area={"Bilingüismo": 694, "Integralidad": 415})
    assert trans["Contratistas requeridos"].sum() == 27
    execution = {"summary": {}, "quarterly": [{"Trimestre": q} for q in range(1, 5)],
                 "transversal_quarterly": [{**row, "Trimestre": q} for q in range(1, 5) for row in trans.to_dict("records")]}
    result = apply_transversal_capacity(execution, instructors, rules)
    assert result["summary"]["transversales_adicionales_pico"] == 11
    frame = pd.DataFrame(result["transversal_quarterly"])
    assert frame.loc[frame["Área"] == "Bilingüismo", "Contratistas adicionales"].tolist() == [10] * 4
    assert frame.loc[frame["Área"] == "Integralidad", "Contratistas adicionales"].tolist() == [1] * 4


def test_modules_are_charged_once_per_cohort_and_preserve_total_hours(report_path):
    instructors = parse_instructors_excel(report_path)
    result = execute(instructors)
    assert [row["Horas bilingüismo del trimestre"] for row in result["calendar"]] == [12, 12, 0, 0]
    assert [row["Horas integralidad del trimestre"] for row in result["calendar"]] == [0, 24, 24, 0]
    assert result["center"]["demanda_bilinguismo_horas_anuales"] == 24
    assert result["center"]["demanda_integralidad_horas_anuales"] == 48
    assert result["center"]["demanda_total_horas_anuales"] == 7 * 30 * 12
    assert result["center"]["demanda_tecnica_horas_anuales"] == 7 * 30 * 12 - 72
    assert result["summary"]["transversales_adicionales_pico"] == 0


def test_imported_continuations_do_not_repeat_completed_modules(report_path):
    instructors = parse_instructors_excel(report_path)
    fichas = pd.DataFrame([{"Ficha": "1", "Especialidad": "SOFTWARE", "Nivel": "Tecnólogo", "Jornada": "Diurna", "Trimestre actual": 3}])
    detail, manual = project_ficha_carryover(fichas, 2026, 4, 2027, group_by_profile=True)
    modules = curriculum(manual)
    modules.loc[modules["Trimestre de formación"] == 4, "Bilingüismo (h)"] = 36
    imported = {"report_year": 2026, "report_quarter": 4, "detail": detail.to_dict("records")}
    result = execute(instructors, manual, modules, imported)
    # La continuación inicia en trimestre de formación 4: únicamente debe 36 h.
    assert [row["Bilingüismo (h)"] for row in result["continuing_transversal_hours"]] == [36, 0, 0, 0]
    assert [row["Integralidad (h)"] for row in result["continuing_transversal_hours"]] == [0, 0, 0, 0]


def test_unknown_pending_modules_require_explicit_hours(report_path):
    with pytest.raises(ValueError, match="pendientes"):
        execute(parse_instructors_excel(report_path), profile(passes=2, ends=1))


@pytest.mark.parametrize("value", [float("nan"), -1, float("inf"), 400])
def test_unknown_or_impossible_module_hours_are_rejected(value):
    manual = profile()
    modules = curriculum(manual)
    modules.loc[0, "Bilingüismo (h)"] = value
    with pytest.raises(ValueError):
        validate_modules(modules, manual, PlanningRules())


def test_retention_is_quarterly_and_does_not_offset_other_areas(report_path):
    instructors = parse_instructors_excel(report_path)
    rules = PlanningRules()
    trans = transversal_staffing_plan(instructors, 20, rules, demand_by_area={"Bilingüismo": 100, "Integralidad": 0})
    execution = {"summary": {}, "quarterly": [{"Trimestre": q} for q in range(1, 5)],
                 "transversal_quarterly": [{**row, "Trimestre": q} for q in range(1, 5) for row in trans.to_dict("records")]}
    continuity = suggested_continuity(instructors, rules)
    continuity.loc[(continuity["Área"] == "Bilingüismo") & (continuity["Trimestre"] == 2), "Contratistas a conservar"] = 0
    result = apply_transversal_capacity(execution, instructors, rules, continuity)
    frame = pd.DataFrame(result["transversal_quarterly"])
    assert frame.loc[frame["Área"] == "Bilingüismo", "Contratistas adicionales"].tolist() == [0, 2, 0, 0]
    assert frame.loc[frame["Área"] == "Integralidad", "Contratistas adicionales"].sum() == 0
    assert result["summary"]["horas_adicionales_transversales_anuales"] == 68 * 12
    continuity.loc[0, "Contratistas a conservar"] = 999
    with pytest.raises(ValueError, match="más contratistas"):
        validate_continuity(continuity, instructors, rules)


def test_modules_retention_and_additional_hours_survive_save_and_export(tmp_path, report_path):
    instructors = parse_instructors_excel(report_path)
    result = execute(instructors)
    path = tmp_path / "modules.sqlite3"
    save_planning(path, instructors, result)
    loaded, saved = load_planning(path)
    for key in ["transversal_modules", "transversal_continuity", "continuing_transversal_hours", "transversal_quarterly"]:
        assert saved[key] == result[key]
    book = pd.ExcelFile(BytesIO(export_planning(loaded, saved)))
    assert "Modulos transversales" in book.sheet_names
    assert "Continuidad transversal" in book.sheet_names
    assert pd.read_excel(book, "Transversales por trimestre")["Contratistas adicionales"].sum() == 0
