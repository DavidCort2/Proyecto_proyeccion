import json

import pandas as pd
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1 import element_tree

from core.database import load_planning, save_planning


@pytest.fixture(autouse=True)
def serialize_editor_events(monkeypatch):
    # AppTest todavía no transmite los eventos de st.data_editor. Añadimos su
    # mensaje de widget real para conservar las ediciones entre interacciones.
    original = element_tree.get_widget_state

    def with_editor_state(node):
        if isinstance(node, element_tree.Dataframe) and node.key and node.key.startswith("distribution_"):
            return WidgetState(id=node.proto.id, string_value=json.dumps(node.root.session_state[node.key]))
        return original(node)

    monkeypatch.setattr(element_tree, "get_widget_state", with_editor_state)


def app_for_test(db_path, excel_path):
    from pathlib import Path
    import app

    app.DATABASE_PATH = Path(db_path)
    app.DEFAULT_EXCEL = Path(excel_path)
    app.main()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def projection(app):
    return next(frame.value for frame in app.dataframe if "Adicionales para completar la meta" in frame.value)


def enter_counts(app, counts, endings=None):
    """Edita el estado del widget como lo hace la tabla en el navegador."""
    base = app.session_state["distribution_base"]
    key = f"distribution_{app.session_state['distribution_source']}_{app.session_state['editor_revision']}"
    endings = endings or {}
    app.session_state[key] = {
        "edited_rows": {
            index: {"Fichas que pasan": counts.get(index, 0), "Fichas que terminan": endings.get(index, 0)}
            for index in range(len(base))
        },
        "added_rows": [], "deleted_rows": [],
    }
    app.run()
    assert not app.exception


def test_execute_reload_and_replace_file(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    report = tmp_path / "reporte.xlsx"
    report.write_bytes(report_path.read_bytes())
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()
    app.radio[0].set_value("Usar reporte incluido").run()
    assert not app.exception
    assert not db.exists()  # Seleccionar un archivo no escribe ni ejecuta.
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert "continuing_fichas" not in [widget.key for widget in app.number_input]
    enter_counts(app, {0: 20, 1: 10}, {0: 4, 1: 6})
    assert projection(app)["Fichas nuevas"].sum() == 20
    assert [item.label for item in app.button] == ["Ejecutar y guardar planeación"]
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert len(load_planning(db)[0]) == 71
    assert load_planning(db)[1]["continuing_fichas"] == 30
    assert load_planning(db)[1]["center"]["fichas_que_terminan"] == 10
    assert len(app.metric) == 4
    original_summary = load_planning(db)[1]["summary"]
    app.number_input(key="weekly_contractor_hours").set_value(20.0).run()
    assert load_planning(db)[1]["summary"] == original_summary
    assert any("pendientes" in message.value for message in app.warning)
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(db)[1]["rules"]["weekly_contractor_hours"] == 20.0

    reopened = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    assert not reopened.exception
    assert reopened.radio[0].value == "Usar datos guardados"
    assert reopened.number_input(key="weekly_contractor_hours").value == 20.0
    assert len(reopened.metric) == 4
    assert reopened.session_state["distribution_base"]["Fichas que pasan"].sum() == 30
    assert reopened.session_state["distribution_base"]["Fichas que terminan"].sum() == 10

    # Otro archivo con el mismo nombre debe renovar el editor y reemplazar SQLite.
    pd.DataFrame([
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["NUEVA ESPECIALIDAD"], ["Nueva Profesora", "001", "Planta", 32],
    ]).to_excel(report, index=False, header=False)
    app.run()
    assert not app.exception
    assert app.session_state["distribution_base"]["Especialidad"].tolist() == ["NUEVA ESPECIALIDAD"]
    assert app.session_state["distribution_base"]["Fichas que pasan"].isna().all()
    enter_counts(app, {0: 20}, {0: 5})
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(db)[0]["Nombre"].tolist() == ["Nueva Profesora"]

    # Un reporte inválido no reemplaza ni mezcla la última ejecución.
    report.write_bytes(b"not an Excel file")
    app.run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert len(app.error) == 1
    assert load_planning(db)[0]["Nombre"].tolist() == ["Nueva Profesora"]


def test_target_changes_automatically_reproject_without_erasing_counts(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    report = report_path
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    app.radio[0].set_value("Usar reporte incluido").run()
    enter_counts(app, {0: 20, 1: 10}, {0: 4, 1: 6})
    app.number_input(key="target_learners").set_value(1000).run()
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()
    assert projection(app)["Fichas nuevas"].sum() == 40
    assert projection(app)["Fichas que pasan"].sum() == 30
    assert projection(app)["Fichas que terminan"].sum() == 10
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(db)[1]["center"]["fichas_nuevas"] == 40
    assert load_planning(db)[1]["continuing_fichas"] == 30


def test_automatic_growth_can_exceed_target_without_changing_it(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    report = report_path
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    app.radio[0].set_value("Usar reporte incluido").run()
    app.number_input(key="target_learners").set_value(50).run()
    enter_counts(app, {0: 20}, {0: 8})
    assert not app.exception
    assert app.number_input(key="target_learners").value == 50
    base = projection(app)
    assert base["Fichas que pasan"].sum() == 20
    assert base["Fichas que terminan"].sum() == 8
    assert base["Fichas nuevas"].sum() == 9
    button(app, "Ejecutar y guardar planeación").click().run()
    assert load_planning(db)[1]["center"]["fichas_al_cierre"] == 21
    assert load_planning(db)[1]["center"]["fichas_adicionales_sobre_meta"] == 7
    assert any("7 fichas adicionales" in message.value for message in app.warning)
    # Cambiar solo las terminaciones también actualiza automáticamente la proyección.
    enter_counts(app, {0: 20}, {0: 18})
    assert not app.exception
    assert projection(app)["Fichas nuevas"].sum() == 19
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(db)[1]
    assert saved["center"]["fichas_nuevas"] == 19
    assert saved["center"]["fichas_al_cierre"] == 21
    assert saved["continuing_fichas"] == 20
    assert saved["growth_rule"]["new_fichas"] == 19
    assert saved["target_learners"] == 50
    reopened = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    assert not reopened.exception
    assert reopened.number_input(key="target_learners").value == 50
    assert projection(reopened)["Fichas nuevas"].sum() == 19
    assert not any("pendientes" in message.value for message in reopened.warning)


def test_invalid_endings_cannot_be_saved(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    report = report_path
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    app.radio[0].set_value("Usar reporte incluido").run()
    enter_counts(app, {0: 2}, {0: 3})
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()


def test_previous_saved_format_keeps_continuations(tmp_path, report_path):
    from core.config import PlanningRules
    from core.excel_parser import parse_instructors_excel
    from core.workflow import execute_plan

    instructors = parse_instructors_excel(report_path)
    distribution = pd.DataFrame([{
        "Especialidad": "NUEVO PROGRAMA", "Fichas que pasan": 12,
        "Fichas que terminan": 0, "Fichas nuevas": 20,
    }])
    previous = execute_plan(instructors, distribution, PlanningRules(), 500, 2027, "guardado.xlsx", "old")
    # Simula una ejecución de la versión previa, sin terminaciones ni guía.
    previous.pop("growth_rule")
    previous.pop("distribution_basis")
    previous["distribution"][0].pop("Fichas que terminan")
    db = tmp_path / "planning.sqlite3"
    save_planning(db, instructors, previous)
    app = AppTest.from_function(app_for_test, args=(str(db), str(report_path)), default_timeout=20).run()
    assert not app.exception
    base = app.session_state["distribution_base"]
    assert base["Fichas que pasan"].tolist() == [12]
    assert "Fichas nuevas" not in base
    assert projection(app)["Fichas nuevas"].tolist() == [20]
    assert base["Fichas que terminan"].tolist() == [0]
    assert any("método anterior" in message.value for message in app.info)
    # Abrir una planeación anterior no la reescribe.
    assert "growth_rule" not in load_planning(db)[1]
