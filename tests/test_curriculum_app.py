import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest, element_tree

from core.curriculum_store import load_curricula
from core.config import PlanningRules
from core.database import database_reset_version, load_planning, reset_planning_database

PROGRAM = "ANALISIS Y DESARROLLO DE SOFTWARE"


@pytest.fixture(autouse=True)
def editor_events(monkeypatch):
    original = element_tree.get_widget_state

    def state(node):
        if isinstance(node, element_tree.Dataframe) and node.key and node.key.startswith("competencies_editor_"):
            return WidgetState(id=node.proto.id, string_value=json.dumps(node.root.session_state[node.key]))
        return original(node)

    monkeypatch.setattr(element_tree, "get_widget_state", state)


def automatic_app_for_test(db_path, instructors_path, fichas_path, curricula_paths):
    from io import BytesIO
    from pathlib import Path
    from unittest.mock import patch
    import streamlit as st
    import app

    app.DATABASE_PATH = Path(db_path)

    def upload(label, *, key, **kwargs):
        base_key = key.split("_reset_", 1)[0]
        paths = {"report_upload": [instructors_path], "fichas_upload": [fichas_path], "curricula_upload": curricula_paths}
        if not st.session_state.get("test_" + key):
            return [] if base_key == "curricula_upload" else None
        files = []
        for filename in paths[base_key]:
            path = Path(filename)
            content = BytesIO(path.read_bytes())
            content.name = path.name
            files.append(content)
        return files if base_key == "curricula_upload" else files[0]

    with patch("streamlit.file_uploader", side_effect=upload):
        app.main()


@pytest.fixture
def app_args(tmp_path):
    instructors = tmp_path / "instructores.xlsx"
    pd.DataFrame([
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        [PROGRAM], ["Instructor", "001", "Planta", 32],
        ["Contrato histórico técnico", "091", "Contratista", 40],
        ["Bilingüismo"], ["Instructora", "002", "Planta", 32],
        ["Contrato histórico inglés", "092", "Contratista", 40],
    ]).to_excel(instructors, index=False, header=False)
    fichas = tmp_path / "fichas.xlsx"
    pd.DataFrame([
        ["Fichas programadas 2026 - Trimestre 4"],
        ["N°", "Número Ficha", "Tipo Formación", "Jornada", "Trimestre"],
        [PROGRAM],
        [1, "001", "Tecnólogo", "Diurna-mañana", 6],
        [2, "002", "Tecnólogo", "Mixta", 8],
    ]).to_excel(fichas, index=False, header=False)
    curricula = [str(p) for p in sorted((Path(__file__).parent / "fixtures" / "curricula").glob("*.xlsx"))]
    return str(tmp_path / "planeacion.sqlite3"), str(instructors), str(fichas), curricula


def button(app, label):
    return next(item for item in app.button if item.label == label)


def open_ready_app(args):
    app = AppTest.from_function(automatic_app_for_test, args=args, default_timeout=30).run()
    for key in ["report_upload", "fichas_upload", "curricula_upload"]:
        app.session_state["test_" + key] = True
    app.number_input(key="planning_year").set_value(2027)
    app.number_input(key="target_technical").set_value(0)
    app.number_input(key="target_technologist").set_value(100)
    for q, weight in enumerate([100, 0, 0, 0]):
        app.number_input(key=f"intake_weight_{q}").set_value(weight)
    app.run()
    assert button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Digitalizar y guardar mallas").click().run()
    return app


def test_automatic_flow_import_execute_export_and_reopen(app_args):
    app = open_ready_app(app_args)
    assert not app.exception
    assert not app.error
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "3360"
    editors = [node.key for node in app.dataframe if node.key]
    assert all(key.startswith("competencies_editor_") for key in editors)
    assert len(load_curricula(app_args[0])["curricula"]) == 2
    assert load_planning(app_args[0]) is None
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    saved = load_planning(app_args[0])[1]
    assert saved["planning_mode"] == "curricula_v4"
    assert [item.label for item in app.metric[:4]] == ["Total de contratistas requeridos", "Trimestre del pico máximo", "Técnicos en el pico", "Transversales en el pico"]
    assert sum(item.label == "Total de contratistas requeridos" for item in app.metric) == 1
    assert not any("actuales" in item.label.lower() or "adicionales" in item.label.lower() for item in app.metric)
    assert saved["center"]["demanda_total_horas_anuales"] == 3360
    reopened = AppTest.from_function(automatic_app_for_test, args=app_args, default_timeout=30).run()
    assert not reopened.exception
    assert not button(reopened, "Ejecutar y guardar planeación").disabled
    assert not any("pendientes de ejecutar" in item.value for item in reopened.warning)
    assert reopened.radio(key="source_mode").value == "Usar datos guardados"
    assert reopened.radio(key="fichas_mode").value == "Usar reporte de fichas guardado"
    assert [tab.label for tab in reopened.tabs] == ["Planeación", "Reportes y parámetros", "Mallas y competencias"]
    assert not reopened.tabs[0].number_input
    assert not reopened.tabs[0].radio
    assert all(not expander.proto.expanded for expander in reopened.tabs[0].expander)
    collapsed_tables = {id(node) for expander in reopened.tabs[0].expander for node in expander.dataframe}
    assert all(id(node) in collapsed_tables for node in reopened.tabs[0].dataframe)
    assert all("Contrato histórico" not in str(node.value) for node in reopened.dataframe)
    assert all("contratistas actuales" not in node.value.lower() for node in reopened.caption)
    detail = next(item for item in reopened.tabs[0].expander if item.label == "Contratistas requeridos y fecha de finalización")
    assert {"Instructor proyectado", "Perfil", "Requerido desde", "Requerido hasta"}.issubset(detail.dataframe[0].value.columns)
    assert detail.dataframe[0].value["Requerido hasta"].notna().all()


def test_unique_classification_save_and_pending_execution(app_args):
    app = open_ready_app(app_args)
    button(app, "Ejecutar y guardar planeación").click().run()
    node = next(item for item in app.dataframe if item.key and item.key.startswith("competencies_editor_"))
    assert len(node.value) == 18
    assert node.value["Competencia"].is_unique
    assert node.value["Transversal"].sum() == 11
    index = int(node.value.index[node.value["Competencia"] == "INGLES"][0])
    app.session_state[node.key] = {"edited_rows": {index: {"Transversal": False}}, "added_rows": [], "deleted_rows": []}
    app.run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Guardar clasificación de competencias").click().run()
    assert not app.exception
    assert any("pendientes de ejecutar" in item.value for item in app.warning)
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(app_args[0])[1]["center"]["demanda_bilinguismo_horas_anuales"] > 0
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(app_args[0])[1]["center"]["demanda_bilinguismo_horas_anuales"] == 0
    reopened = AppTest.from_function(automatic_app_for_test, args=app_args, default_timeout=30).run()
    assert not reopened.exception
    assert not any("pendientes de ejecutar" in item.value for item in reopened.warning)


def test_invalid_reports_and_missing_mallas_never_replace_saved_result(app_args):
    app = open_ready_app(app_args)
    button(app, "Ejecutar y guardar planeación").click().run()
    previous = load_planning(app_args[0])[1]
    Path(app_args[2]).write_bytes(b"invalid")
    app.run()
    assert not app.exception
    assert app.error
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(app_args[0])[1] == previous
    assert not app.metric  # Una entrada inválida no deja cifras anteriores como resultado vigente.
    app.number_input(key="intake_weight_0").set_value(99).run()
    assert button(app, "Ejecutar y guardar planeación").disabled


def test_missing_shift_is_visible_and_prevents_execution(app_args):
    args = (*app_args[:3], app_args[3][:1])
    app = open_ready_app(args)
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert any("Faltan mallas" in item.value and "Mixta" in item.value for item in app.warning)
    assert load_planning(args[0]) is None


def test_reports_required_even_with_mallas_and_no_manual_counts(app_args):
    app = AppTest.from_function(automatic_app_for_test, args=app_args, default_timeout=30).run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not app.selectbox
    assert not app.dataframe
    assert not any("modular" in item.value.lower() for item in app.radio)
    assert app.number_input(key="target_technical").value == 0
    assert app.number_input(key="target_technologist").value == 0


@pytest.mark.parametrize("from_button", [False, True])
def test_database_reset_clears_existing_browser_inputs_and_uploads(app_args, from_button):
    app = open_ready_app(app_args)
    app.number_input(key="learners_per_ficha").set_value(20)
    app.number_input(key="weekly_plant_direct_hours").set_value(25.0).run()
    button(app, "Ejecutar y guardar planeación").click().run()
    assert load_planning(app_args[0])
    if from_button:
        app.checkbox(key="confirm_system_reset").check().run()
        button(app, "Formatear sistema").click().run()
        assert any("Sistema limpio" in item.value for item in app.success)
    else:
        reset_planning_database(app_args[0])
        app.run()
    assert not app.exception
    assert not app.metric
    assert app.number_input(key="target_technical").value == 0
    assert app.number_input(key="target_technologist").value == 0
    assert app.number_input(key="learners_per_ficha").value == PlanningRules().learners_per_ficha
    assert app.number_input(key="weekly_plant_direct_hours").value == PlanningRules().weekly_plant_direct_hours
    assert not app.checkbox(key="confirm_system_reset").value
    assert button(app, "Formatear sistema").disabled
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(app_args[0]) is None
    assert load_curricula(app_args[0])["curricula"] == []
    revision = app.session_state["_database_reset_version"]
    assert revision > 0
    for key in ["report_upload", "fichas_upload", "curricula_upload"]:
        app.session_state[f"test_{key}_reset_{revision}"] = True
    app.run()
    button(app, "Digitalizar y guardar mallas").click().run()
    assert not app.exception
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert len(load_curricula(app_args[0])["curricula"]) == 2


def test_format_requires_confirmation_and_explicit_click(app_args):
    app = open_ready_app(app_args)
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(app_args[0])[1]
    catalog = load_curricula(app_args[0])
    revision = database_reset_version(app_args[0])
    assert button(app, "Formatear sistema").disabled
    app.checkbox(key="confirm_system_reset").check().run()
    assert not button(app, "Formatear sistema").disabled
    assert load_planning(app_args[0])[1] == saved
    assert load_curricula(app_args[0]) == catalog
    app.checkbox(key="confirm_system_reset").uncheck().run()
    assert button(app, "Formatear sistema").disabled
    assert load_planning(app_args[0])[1] == saved
    assert database_reset_version(app_args[0]) == revision


def test_format_failure_is_visible_without_resetting_inputs(app_args, monkeypatch):
    app = open_ready_app(app_args)
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(app_args[0])[1]
    revision = database_reset_version(app_args[0])

    def fail_reset(path):
        raise sqlite3.OperationalError("Base de datos ocupada")

    monkeypatch.setattr("ui.system_reset.reset_planning_database", fail_reset)
    app.checkbox(key="confirm_system_reset").check().run()
    button(app, "Formatear sistema").click().run()
    assert not app.exception
    assert any("No fue posible completar la limpieza" in item.value for item in app.error)
    assert not any("Sistema limpio" in item.value for item in app.success)
    assert app.number_input(key="target_technologist").value == 100
    assert app.checkbox(key="confirm_system_reset").value
    assert load_planning(app_args[0])[1] == saved
    assert len(load_curricula(app_args[0])["curricula"]) == 2
    assert database_reset_version(app_args[0]) == revision
