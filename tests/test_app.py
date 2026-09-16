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
        if isinstance(node, element_tree.Dataframe) and node.key and node.key.startswith(("distribution_", "quarter_editor_")):
            return WidgetState(id=node.proto.id, string_value=json.dumps(node.root.session_state[node.key]))
        return original(node)

    monkeypatch.setattr(element_tree, "get_widget_state", with_editor_state)


def app_for_test(db_path, excel_path, fichas_path=None):
    from pathlib import Path
    import app

    app.DATABASE_PATH = Path(db_path)
    app.DEFAULT_EXCEL = Path(excel_path)
    if fichas_path:
        app.DEFAULT_FICHAS = Path(fichas_path)
    app.main()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def projection(app):
    return next(frame.value for frame in app.dataframe if "Horas totales (h/sem)" in frame.value)


def enter_counts(app, counts, endings=None):
    """Edita el estado del widget como lo hace la tabla en el navegador."""
    base = app.session_state["distribution_base"]
    key = f"distribution_{app.session_state['distribution_source']}_{app.session_state['editor_revision']}"
    endings = endings or {}
    app.session_state[key] = {
        "edited_rows": {
            index: {
                "Fichas que pasan": counts.get(index, 0), "Fichas que terminan": endings.get(index, 0),
                "Nivel": base.loc[index, "Nivel"] if pd.notna(base.loc[index, "Nivel"]) else "Técnico",
                "Jornada": base.loc[index, "Jornada"] if pd.notna(base.loc[index, "Jornada"]) else "Diurna",
            }
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
    assert projection(app)["Fichas nuevas"].sum() == 25  # Incluye rotación de nuevas técnicas en T4.
    assert [item.label for item in app.button] == ["Ejecutar y guardar planeación"]
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert len(load_planning(db)[0]) == 71
    assert load_planning(db)[1]["continuing_fichas"] == 30
    assert load_planning(db)[1]["center"]["fichas_que_terminan"] == 10
    assert len(app.metric) == 11
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
    assert len(reopened.metric) == 11
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
    app.number_input(key="target_technical").set_value(1000).run()
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()
    assert projection(app)["Fichas nuevas"].sum() == 53
    assert projection(app)["Fichas que pasan"].sum() == 30
    assert projection(app)["Fichas que terminan"].sum() == 10
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(db)[1]["center"]["fichas_nuevas"] == 53
    assert load_planning(db)[1]["continuing_fichas"] == 30


def test_automatic_growth_can_exceed_target_without_changing_it(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    report = report_path
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    app.radio[0].set_value("Usar reporte incluido").run()
    app.number_input(key="target_technical").set_value(50).run()
    enter_counts(app, {0: 20}, {0: 8})
    assert not app.exception
    assert app.number_input(key="target_technical").value == 50
    base = projection(app)
    assert base["Fichas que pasan"].sum() == 20
    assert base["Fichas que terminan"].sum() == 8
    assert base["Fichas nuevas"].sum() == 8
    button(app, "Ejecutar y guardar planeación").click().run()
    assert load_planning(db)[1]["center"]["fichas_al_cierre"] == 17
    assert load_planning(db)[1]["center"]["reposiciones_siguiente_vigencia"] == 4
    assert load_planning(db)[1]["center"]["fichas_adicionales_sobre_meta"] == 6
    assert any("6 fichas adicionales" in message.value for message in app.warning)
    # Cambiar solo las terminaciones también actualiza automáticamente la proyección.
    enter_counts(app, {0: 20}, {0: 18})
    assert not app.exception
    assert projection(app)["Fichas nuevas"].sum() == 16
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(db)[1]
    assert saved["center"]["fichas_nuevas"] == 16
    assert saved["center"]["fichas_al_cierre"] == 12
    assert saved["center"]["reposiciones_siguiente_vigencia"] == 9
    assert saved["continuing_fichas"] == 20
    assert saved["growth_rule"]["new_fichas"] == 15
    assert saved["target_learners"] == 50
    reopened = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    assert not reopened.exception
    assert reopened.number_input(key="target_technical").value == 50
    assert projection(reopened)["Fichas nuevas"].sum() == 16
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
    assert base["Fichas que terminan"].tolist() == [0]
    assert button(app, "Ejecutar y guardar planeación").disabled
    enter_counts(app, {0: 12})
    assert projection(app)["Fichas nuevas"].tolist() == [28]
    assert any("método anterior" in message.value for message in app.info)
    # Abrir una planeación anterior no la reescribe.
    assert "growth_rule" not in load_planning(db)[1]


def write_fichas_report(path, trimester=2):
    pd.DataFrame([
        ["Fichas programadas 2026 - Trimestre 4"],
        ["N°", "Número Ficha", "Tipo Formación", "Jornada", "Trimestre"],
        ["CONTROL DE LA SEGURIDAD DIGITAL"],
        [1, "001", "Técnico", "Diurna-mañana", trimester],
        [2, "002", "Tecnólogo", "Diurna-tarde", 7],
    ]).to_excel(path, header=False, index=False)


def test_fichas_prefill_overrides_persistence_and_replacement(tmp_path, report_path):
    from io import BytesIO
    from core.export import export_planning

    db = tmp_path / "planning.sqlite3"
    report = tmp_path / "fichas.xlsx"
    write_fichas_report(report)
    args = (str(db), str(report_path), str(report))
    app = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    app.radio(key="source_mode").set_value("Usar reporte incluido").run()
    app.radio(key="fichas_mode").set_value("Usar reporte de fichas incluido").run()
    assert not app.exception
    assert not app.error
    base = app.session_state["distribution_base"]
    assert base["Fichas que pasan"].sum() == 1
    assert base["Fichas que terminan"].sum() == 1
    assert not button(app, "Ejecutar y guardar planeación").disabled
    index = base.index[base["Especialidad"] == "CONTROL DE LA SEGURIDAD DIGITAL"][0]
    enter_counts(app, {int(index): 3}, {int(index): 2})
    app.number_input(key="target_technical").set_value(1000).run()
    assert projection(app)["Fichas que pasan"].sum() == 3  # Una interacción no borra la corrección.
    button(app, "Ejecutar y guardar planeación").click().run()
    loaded, saved = load_planning(db)
    assert saved["continuing_fichas"] == 3
    assert sum(row["Fichas que pasan"] for row in saved["ficha_import"]["summary"]) == 1
    assert saved["ficha_import"]["source_name"] == "fichas.xlsx"
    sheets = pd.ExcelFile(BytesIO(export_planning(loaded, saved))).sheet_names
    assert "Detalle fichas importadas" in sheets
    assert "Continuaciones calculadas" in sheets

    # Recupera el reporte y las correcciones desde SQLite, aun sin el Excel original.
    report.write_bytes(b"archivo invalido")
    reopened = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    assert not reopened.exception
    assert reopened.radio(key="fichas_mode").value == "Usar reporte de fichas guardado"
    assert projection(reopened)["Fichas que pasan"].sum() == 3
    assert not any("pendientes" in message.value for message in reopened.warning)
    app.run()
    assert len(app.error) == 1
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(db)[1]["continuing_fichas"] == 3

    # Mismo nombre, contenido nuevo: renueva los cálculos, sin conservar ediciones ajenas.
    write_fichas_report(report, trimester=3)
    app.run()
    assert not app.exception
    assert app.session_state["distribution_base"]["Fichas que pasan"].sum() == 0


def test_op_schedules_have_automatic_ten_quarter_duration(tmp_path, report_path):
    from pathlib import Path
    fichas = Path(__file__).resolve().parents[1] / "data/reporteFichas_2026_4.xlsx"
    app = AppTest.from_function(app_for_test, args=(str(tmp_path / "db.sqlite3"), str(report_path), str(fichas)), default_timeout=20).run()
    app.radio(key="source_mode").set_value("Usar reporte incluido").run()
    app.radio(key="fichas_mode").set_value("Usar reporte de fichas incluido").run()
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert len(app.selectbox) == 0
    assert not app.exception
    assert projection(app)["Fichas que pasan"].sum() == 54
    assert projection(app)["Fichas que terminan"].sum() == 37
    app.number_input(key="planning_year").set_value(2028).run()
    assert not app.exception
    assert projection(app)["Fichas que pasan"].sum() < 53


def test_two_targets_preview_mixed_hours_and_shared_capacity_survive_reopen(tmp_path):
    db = tmp_path / "planning.sqlite3"
    report = tmp_path / "instructors.xlsx"
    pd.DataFrame([
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["ADSO"], ["Profesora", "001", "Planta", 32],
    ]).to_excel(report, index=False, header=False)
    args = (str(db), str(report))
    app = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    app.radio(key="source_mode").set_value("Usar reporte incluido").run()
    app.number_input(key="target_technical").set_value(25)
    app.number_input(key="target_technologist").set_value(25).run()
    key = f"distribution_{app.session_state['distribution_source']}_{app.session_state['editor_revision']}"
    app.session_state[key] = {
        "edited_rows": {0: {"Nivel": "Técnico", "Jornada": "Diurna", "Fichas que pasan": 0}},
        "added_rows": [{"Especialidad": "ADSO", "Nivel": "Tecnólogo", "Jornada": "Mixta",
                        "Fichas que pasan": 0, "Fichas que terminan": 0}],
        "deleted_rows": [],
    }
    app.run()
    assert not app.exception
    assert projection(app)["Horas totales (h/sem)"].sum() == 56
    assert next(item.value for item in app.metric if item.label == "Pico de horas requeridas / semana") == "56"
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "2688"
    assert not db.exists()
    app.number_input(key="target_technologist").set_value(50).run()
    assert not app.exception
    assert projection(app)["Fichas nuevas"].tolist() == [2, 2]
    assert projection(app)["Horas totales (h/sem)"].sum() == 82
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(db)[1]
    assert saved["targets_by_level"] == {"Técnico": 25, "Tecnólogo": 50}
    assert saved["technical"][0]["Capacidad planta (h/sem)"] == 32
    assert saved["technical"][0]["Demanda técnica (h/sem)"] == 54
    reopened = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    assert not reopened.exception
    assert reopened.number_input(key="target_technical").value == 25
    assert reopened.number_input(key="target_technologist").value == 50
    assert projection(reopened)["Horas totales (h/sem)"].sum() == 82
    assert not any("pendientes" in message.value for message in reopened.warning)


def test_targets_show_annual_reference_even_before_loading_profiles(tmp_path, report_path):
    db = tmp_path / "planning.sqlite3"
    app = AppTest.from_function(app_for_test, args=(str(db), str(report_path)), default_timeout=20).run()
    app.number_input(key="target_technical").set_value(50)
    app.number_input(key="target_technologist").set_value(25).run()
    estimate = next(item.value for item in app.dataframe if "Horas anuales si son diurnas" in item.value)
    assert estimate["Horas anuales si son diurnas"].tolist() == [2160, 1440]
    assert estimate["Horas anuales si son mixtas"].tolist() == [1872, 1248]
    assert not db.exists()


def test_quarter_end_edits_change_annual_hours_and_survive_save(tmp_path):
    db = tmp_path / "planning.sqlite3"
    report = tmp_path / "instructors.xlsx"
    pd.DataFrame([
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["ADSO"], ["Profesora", "001", "Planta", 32],
    ]).to_excel(report, index=False, header=False)
    args = (str(db), str(report))
    app = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    app.radio(key="source_mode").set_value("Usar reporte incluido").run()
    app.number_input(key="target_technical").set_value(0)
    app.number_input(key="target_technologist").set_value(50).run()
    key = f"distribution_{app.session_state['distribution_source']}_{app.session_state['editor_revision']}"
    app.session_state[key] = {"edited_rows": {0: {"Nivel": "Tecnólogo", "Fichas que pasan": 2,
                                                  "Fichas que terminan": 1}}, "added_rows": [], "deleted_rows": []}
    app.run()
    assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "4320"
    quarter_key = next(item.key for item in app.dataframe if item.key and item.key.startswith("quarter_editor_"))
    app.session_state[quarter_key] = {"edited_rows": {0: {"Terminan T1": 0, "Terminan T4": 1}},
                                    "added_rows": [], "deleted_rows": []}
    app.run()
    assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "5400"
    app.number_input(key="weeks_per_quarter").set_value(10).run()
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "4500"
    button(app, "Ejecutar y guardar planeación").click().run()
    saved = load_planning(db)[1]
    assert saved["quarter_endings"][0]["Terminan T4"] == 1
    assert saved["center"]["demanda_total_horas_anuales"] == 4500
    reopened = AppTest.from_function(app_for_test, args=args, default_timeout=20).run()
    assert not reopened.exception
    assert next(item.value for item in reopened.metric if item.label == "Total de horas al año") == "4500"
    assert not any("pendientes" in message.value for message in reopened.warning)
    app.session_state[quarter_key] = {"edited_rows": {0: {"Terminan T1": 1, "Terminan T4": 1}},
                                    "added_rows": [], "deleted_rows": []}
    app.run()
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(db)[1]["center"]["demanda_total_horas_anuales"] == 4500
