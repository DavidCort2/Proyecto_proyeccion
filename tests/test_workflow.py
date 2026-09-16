from io import BytesIO
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.excel_parser import parse_instructors_excel
from core.export import export_planning
from core.planner import suggested_ficha_distribution, technical_specialty_catalog
from core.workflow import execute_plan, validate_distribution


@pytest.fixture
def instructors(report_path):
    return parse_instructors_excel(report_path)


def execution_for(instructors, name="reporte.xlsx"):
    return execute_plan(
        instructors, manual_distribution(instructors),
        PlanningRules(), 500, 2027, name, name,
    )


def manual_distribution(instructors):
    frame = technical_specialty_catalog(instructors)[["Especialidad"]].copy()
    frame["Fichas que pasan"] = 0
    frame["Fichas que terminan"] = 0
    frame["Fichas nuevas"] = 0
    frame.loc[0, "Fichas que pasan"] = 2
    return suggested_ficha_distribution(frame, 20)


def test_save_load_preserves_names_rules_and_results(tmp_path, instructors):
    db = tmp_path / "planning.sqlite3"
    assert load_planning(db) is None
    assert not db.exists()
    execution = execution_for(instructors)
    save_planning(db, instructors, execution)
    loaded, saved = load_planning(db)
    pd.testing.assert_frame_equal(loaded, instructors)
    assert saved["summary"] == execution["summary"]
    assert saved["rules"] == execution["rules"]
    assert saved["distribution"] == execution["distribution"]
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM plant_instructors").fetchone()[0] == 19
        assert connection.execute("SELECT count(*) FROM specialties").fetchone()[0] == len(instructors.attrs["specialties"])


def test_new_file_replaces_all_previous_data(tmp_path, instructors):
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors, execution_for(instructors))
    replacement = instructors.loc[instructors["Es planta"]].iloc[:1].copy()
    replacement["Nombre"] = "Profesora Nueva"
    replacement["Especialidad"] = "NUEVA ESPECIALIDAD"
    replacement.attrs = {}
    save_planning(db, replacement, execution_for(replacement, "otro.xlsx"))
    loaded, saved = load_planning(db)
    assert loaded["Nombre"].tolist() == ["Profesora Nueva"]
    assert saved["source_name"] == "otro.xlsx"
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT name FROM specialties").fetchall() == [("NUEVA ESPECIALIDAD",)]
        assert connection.execute("SELECT count(*) FROM execution").fetchone()[0] == 1
    # Volver a ejecutar la misma carga no duplica instructores.
    save_planning(db, replacement, execution_for(replacement, "otro.xlsx"))
    assert len(load_planning(db)[0]) == 1


def test_failed_replacement_rolls_back_deleted_data(tmp_path, instructors):
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors, execution_for(instructors))
    previous = load_planning(db)
    broken = instructors.copy()
    broken.loc[0, "Nombre"] = ""  # Viola CHECK después de borrar e insertar especialidades.
    with pytest.raises(sqlite3.IntegrityError):
        save_planning(db, broken, execution_for(instructors, "fallido.xlsx"))
    after = load_planning(db)
    pd.testing.assert_frame_equal(after[0], previous[0])
    assert after[1] == previous[1]


@pytest.mark.parametrize("value", [-1, 1.5, None, "abc", float("inf")])
def test_invalid_ficha_counts_are_rejected(instructors, value):
    distribution = pd.DataFrame([{"Especialidad": "NUEVA", "Fichas nuevas": value, "Fichas que pasan": 0}])
    with pytest.raises(ValueError, match="enteros"):
        validate_distribution(distribution, instructors, 1, 0)


@pytest.mark.parametrize("specialty", ["", "Bilingüismo", "Integralidad"])
def test_invalid_specialty_is_rejected(instructors, specialty):
    distribution = pd.DataFrame([{"Especialidad": specialty, "Fichas nuevas": 1, "Fichas que pasan": 0}])
    with pytest.raises(ValueError):
        validate_distribution(distribution, instructors, 1, 0)


def test_distribution_totals_and_duplicate_specialties_are_rejected(instructors):
    distribution = manual_distribution(instructors)
    with pytest.raises(ValueError, match="sumar"):
        validate_distribution(distribution, instructors, 21, 2)
    with pytest.raises(ValueError, match="repetidas"):
        validate_distribution(pd.concat([distribution, distribution.iloc[:1]]), instructors, 20, 2)


def test_manual_specialties_and_export_survive_restart(tmp_path, instructors):
    distribution = pd.DataFrame([{"Especialidad": "NUEVA", "Fichas nuevas": 20, "Fichas que pasan": 2}])
    execution = execute_plan(instructors, distribution, PlanningRules(), 500, 2027, "reporte.xlsx", "abc")
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors, execution)
    loaded, saved = load_planning(db)
    assert {"Especialidad": "NUEVA", "Área": "Técnica"} in loaded.attrs["specialties"]
    assert saved["technical"][0]["Instructores planta"] == 0
    workbook = pd.ExcelFile(BytesIO(export_planning(loaded, saved)))
    assert len(pd.read_excel(workbook, sheet_name="Instructores planta")) == 19
    assert pd.read_excel(workbook, sheet_name="Resumen planeacion").iloc[0]["Vigencia"] == 2027
    assert pd.read_excel(workbook, sheet_name="Distribucion").iloc[0]["Especialidad"] == "NUEVA"


def test_report_without_technical_instructors_supports_zero_target(instructors):
    transversal = instructors.loc[instructors["Área"] != "Técnica"].copy()
    transversal.attrs = {}
    distribution = pd.DataFrame(columns=["Especialidad", "Fichas nuevas", "Fichas que pasan"])
    execution = execute_plan(transversal, distribution, PlanningRules(), 0, 2027, "transversal.xlsx", "abc")
    assert execution["summary"]["contratistas_totales"] == 0
