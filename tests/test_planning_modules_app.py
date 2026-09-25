import json
from datetime import date
from pathlib import Path

import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest, element_tree

from core.database import load_planning, save_planning
from core.planning_modules import planning_database
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules
from test_curriculum_app import app_args, button
from test_virtual_schedules import schedule_bytes


@pytest.fixture(autouse=True)
def editor_events(monkeypatch):
    original = element_tree.get_widget_state

    def state(node):
        if isinstance(node, element_tree.Dataframe) and node.key:
            return WidgetState(id=node.proto.id, string_value=json.dumps(node.root.session_state[node.key]))
        return original(node)

    monkeypatch.setattr(element_tree, "get_widget_state", state)


def module_app_for_test(db_path, instructors_path, fichas_path, curricula_paths, virtual_file):
    from io import BytesIO
    from pathlib import Path
    from unittest.mock import patch
    import streamlit as st
    from ui.navigation import render_application

    st.session_state["_visible_uploads"] = []

    def upload(label, *, key, **kwargs):
        st.session_state["_visible_uploads"].append(key)
        base_key = key.removeprefix("virtual:").split("_reset_", 1)[0]
        paths = {"report_upload": [instructors_path], "fichas_upload": [fichas_path],
                 "curricula_upload": curricula_paths, "schedules_upload": [virtual_file]}
        if not st.session_state.get("test_" + key):
            return [] if base_key in ("curricula_upload", "schedules_upload") else None
        files = []
        for filename in paths[base_key]:
            path = Path(filename)
            content = BytesIO(path.read_bytes())
            content.name = path.name
            files.append(content)
        return files if base_key in ("curricula_upload", "schedules_upload") else files[0]

    with patch("streamlit.file_uploader", side_effect=upload):
        render_application(Path(db_path))


@pytest.fixture
def module_args(app_args, tmp_path):
    virtual_file = tmp_path / "Cronograma Software.xlsx"
    virtual_file.write_bytes(schedule_bytes())
    return (*app_args, str(virtual_file))


def open_app(args):
    return AppTest.from_function(module_app_for_test, args=args, default_timeout=30).run()


def editor(app, prefix):
    return next(node for node in app.dataframe if node.key and node.key.startswith(prefix))


def edit(app, prefix, *, rows=None, added=None, deleted=None):
    node = editor(app, prefix)
    app.session_state[node.key] = {"edited_rows": rows or {}, "added_rows": added or [], "deleted_rows": deleted or []}
    app.run()
    assert not app.exception


def ready_virtual(app):
    app.radio(key="nav_modality").set_value("Virtual").run()
    app.session_state["test_virtual:schedules_upload"] = True
    app.run()
    button(app, "Importar y guardar cronogramas").click().run()
    assert len(editor(app, "virtual:schedule_competencies_").value) == 2
    assert not app.exception
    edit(app, "virtual:virtual_programs_", rows={0: {"Nivel": "Tecnólogo"}})
    app.number_input(key="virtual:planning_year").set_value(2027)
    app.number_input(key="virtual:target_technologist").set_value(100)
    for q, weight in enumerate([100, 0, 0, 0]):
        app.number_input(key=f"virtual:intake_weight_{q}").set_value(weight)
    app.run()
    assert not app.date_input  # Ofertas automáticas; fin lectiva se ingresa en la tabla.
    assert not app.exception
    assert not app.error
    assert not button(app, "Ejecutar y guardar planeación").disabled
    return app


def save_presencial(app):
    app.radio(key="nav_modality").set_value("Presencial").run()
    for key in ("report_upload", "fichas_upload", "curricula_upload"):
        app.session_state["test_" + key] = True
    app.number_input(key="planning_year").set_value(2027)
    app.number_input(key="target_technologist").set_value(100).run()
    button(app, "Digitalizar y guardar mallas").click().run()
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert not app.error


def test_navigation_independent_parameters_and_empty_complementaria(module_args):
    app = open_app(module_args)
    assert app.radio(key="nav_modality").value == "Presencial"
    app.number_input(key="target_technical").set_value(750)
    app.number_input(key="weekly_plant_direct_hours").set_value(20.0).run()
    app.radio(key="nav_modality").set_value("Virtual").run()
    assert not app.exception
    assert app.number_input(key="virtual:target_technical").value == 0
    assert app.number_input(key="virtual:weekly_plant_direct_hours").value == 32
    assert app.session_state["_visible_uploads"] == ["virtual:schedules_upload"]
    labels = [node.label.lower() for node in app.number_input]
    assert not any("jornada" in label or "trimestre" in label or "diurna" in label or "mixta" in label for label in labels)
    app.number_input(key="virtual:target_technical").set_value(100).run()
    app.radio(key="nav_training").set_value("Complementaria").run()
    assert not app.number_input and not app.button and not app.metric
    app.radio(key="nav_modality").set_value("Presencial").run()
    assert not app.number_input and not app.exception
    assert not Path(module_args[0]).exists()
    assert not planning_database(module_args[0], "Virtual").exists()
    app.radio(key="nav_training").set_value("Titulada").run()
    assert app.number_input(key="target_technical").value == 750
    assert app.number_input(key="weekly_plant_direct_hours").value == 20
    app.radio(key="nav_modality").set_value("Virtual").run()
    assert app.number_input(key="virtual:target_technical").value == 100


def test_virtual_manual_workflow_save_reopen_and_export(module_args):
    app = ready_virtual(open_app(module_args))
    edit(app, "virtual:virtual_cohorts_", added=[{
        "Programa": "Software", "Fecha fin lectiva": "2027-01-14"} for _ in range(2)])
    edit(app, "virtual:virtual_plant_", added=[{"Nombre completo": "Ana María Pérez", "Cédula": "00123", "Tipo": "Técnico", "Perfil": "Software"}])
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == "68"
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception and not app.error
    path = planning_database(module_args[0], "Virtual")
    saved = load_planning(path)
    assert sum(row["Fichas que pasan"] for row in saved[1]["virtual_inputs"]["cohorts"]) == 2
    assert len(saved[0]) == 1
    assert saved[0].iloc[0]["Nombre"] == "Ana María Pérez"
    assert saved[0].iloc[0]["Documento"] == "00123"
    assert not Path(module_args[0]).exists()
    assert not app.get("download_button")[0].proto.disabled
    reopened = open_app(module_args)
    reopened.radio(key="nav_modality").set_value("Virtual").run()
    assert not reopened.exception and not reopened.error
    assert reopened.number_input(key="virtual:target_technologist").value == 100
    assert next(item.value for item in reopened.metric if item.label == "Total de horas al año") == "68"
    assert not reopened.get("download_button")[0].proto.disabled


def test_unsaved_manual_edits_survive_switches(module_args):
    app = ready_virtual(open_app(module_args))
    edit(app, "virtual:virtual_cohorts_", added=[{
        "Programa": "Software", "Fecha fin lectiva": "2027-01-14"} for _ in range(2)])
    hours = next(item.value for item in app.metric if item.label == "Total de horas al año")
    for training, modality in [("Titulada", "Presencial"), ("Complementaria", "Virtual"), ("Titulada", "Virtual")]:
        app.radio(key="nav_training").set_value(training)
        app.radio(key="nav_modality").set_value(modality).run()
        assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Total de horas al año") == hours
    assert sum(row["Fichas que pasan"] for row in app.session_state["virtual:schedule_manual_draft"]["cohorts"]) == 2
    assert load_planning(planning_database(module_args[0], "Virtual")) is None


@pytest.mark.parametrize("reset_virtual", [True, False])
def test_save_and_reset_do_not_touch_other_module(module_args, reset_virtual):
    app = open_app(module_args)
    save_presencial(app)
    presencial = Path(module_args[0])
    snapshot_p = presencial.read_bytes()
    app = ready_virtual(app)
    button(app, "Ejecutar y guardar planeación").click().run()
    virtual = planning_database(presencial, "Virtual")
    snapshot_v = virtual.read_bytes()
    assert presencial.read_bytes() == snapshot_p
    if not reset_virtual:
        app.radio(key="nav_modality").set_value("Presencial").run()
    prefix = "virtual:" if reset_virtual else ""
    app.checkbox(key=prefix + "confirm_system_reset").check().run()
    button(app, "Formatear sistema").click().run()
    assert not app.exception
    assert any("Sistema limpio" in item.value for item in app.success)
    assert load_planning(virtual if reset_virtual else presencial) is None
    assert (presencial if reset_virtual else virtual).read_bytes() == (snapshot_p if reset_virtual else snapshot_v)
    app.radio(key="nav_modality").set_value("Presencial" if reset_virtual else "Virtual").run()
    assert not app.exception
    assert app.metric
    assert app.number_input(key=("" if reset_virtual else "virtual:") + "target_technologist").value == 100


def test_invalid_virtual_input_blocks_saving_and_preserves_previous(module_args):
    app = ready_virtual(open_app(module_args))
    button(app, "Ejecutar y guardar planeación").click().run()
    path = planning_database(module_args[0], "Virtual")
    saved = load_planning(path)[1]
    edit(app, "virtual:virtual_cohorts_", added=[{
        "Programa": "Software", "Fecha fin lectiva": "2025-01-01"}])
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert any("terminaron" in item.value for item in app.warning)
    assert load_planning(path)[1] == saved


def test_wrong_modality_curriculum_is_not_saved(module_args):
    args = (*module_args[:-1], module_args[3][0])  # Intentar usar una malla presencial en Virtual.
    app = open_app(args)
    app.radio(key="nav_modality").set_value("Virtual").run()
    app.session_state["test_virtual:schedules_upload"] = True
    app.run()
    assert not app.exception
    assert any("cronograma" in item.value.lower() for item in app.error)
    assert load_virtual_schedules(planning_database(module_args[0], "Virtual"))["schedules"] == []


def test_older_presencial_execution_opens_without_forcing_a_new_save(module_args):
    app = open_app(module_args)
    save_presencial(app)
    staff, plan = load_planning(module_args[0])
    plan.pop("training_type")
    plan.pop("modality")
    save_planning(module_args[0], staff, plan)
    reopened = open_app(module_args)
    assert not reopened.exception and not reopened.error
    assert not reopened.get("download_button")[0].proto.disabled


def test_virtual_draft_survives_schedule_replacement(module_args):
    app = ready_virtual(open_app(module_args))
    edit(app, "virtual:virtual_cohorts_", added=[{
        "Programa": "Software", "Fecha fin lectiva": "2027-01-14"} for _ in range(2)])
    edit(app, "virtual:virtual_plant_", added=[{"Nombre completo": "Ana Pérez", "Cédula": "00123", "Tipo": "Técnico", "Perfil": "Software"}])
    # Simula reemplazo por otra sesión; la carga visible se retira antes de recargar.
    app.session_state["test_virtual:schedules_upload"] = False
    app.session_state["virtual:uploads:virtual:schedules_upload"] = []
    path = planning_database(module_args[0], "Virtual")
    original = Path(module_args[-1]).read_bytes()
    for content in [schedule_bytes(durations=(14, 7, 7)), original]:
        import_virtual_schedules(path, [("Cronograma Software.xlsx", content)])
        app.run()
        assert not app.exception
        assert sum(row["Fichas que pasan"] for row in app.session_state["virtual:schedule_manual_draft"]["cohorts"]) == 2
        assert app.session_state["virtual:schedule_manual_draft"]["plant"][0]["Cédula"] == "00123"
        assert not button(app, "Ejecutar y guardar planeación").disabled  # Recalcula con la nueva duración y conserva el fin lectivo.


def test_activity_edits_and_transversal_plant_apply_only_after_saving(module_args):
    app = ready_virtual(open_app(module_args))
    edit(app, "virtual:virtual_plant_", added=[{"Nombre completo": "Luis Pérez", "Cédula": "987", "Tipo": "Transversal", "Perfil": "240202501"}])
    button(app, "Ejecutar y guardar planeación").click().run()
    path = planning_database(module_args[0], "Virtual")
    previous = load_planning(path)[1]
    assert previous["virtual_inputs"]["plant"][0]["Tipo"] == "Transversal"
    edit(app, "virtual:schedule_competencies_", rows={0: {"Tipo": "Transversal"}})
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_planning(path)[1] == previous
    app.radio(key="nav_modality").set_value("Presencial").run()
    app.radio(key="nav_modality").set_value("Virtual").run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not button(app, "Guardar clasificación de competencias").disabled
    button(app, "Guardar clasificación de competencias").click().run()
    assert load_virtual_schedules(path)["schedules"][0]["activities"][0]["teaching_type"] == "Transversal"
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    assert load_planning(path)[1]["center"]["demanda_total_horas_anuales"] == 24


def test_productive_stage_is_not_editable_and_older_plan_requires_recalculation(module_args):
    Path(module_args[-1]).write_bytes(schedule_bytes(productive_days=14))
    app = ready_virtual(open_app(module_args))
    assert len(editor(app, "virtual:schedule_competencies_").value) == 2
    assert "Etapa productiva" not in editor(app, "virtual:schedule_competencies_").value["Competencia"].tolist()
    button(app, "Ejecutar y guardar planeación").click().run()
    path = planning_database(module_args[0], "Virtual")
    staff, previous = load_planning(path)
    previous.pop("workload_scope")
    previous["center"]["demanda_total_horas_anuales"] = 999
    save_planning(path, staff, previous)
    reopened = open_app(module_args)
    reopened.radio(key="nav_modality").set_value("Virtual").run()
    assert not reopened.exception and not reopened.error
    assert any("anterior al cálculo solo lectivo" in item.value for item in reopened.info)
    assert next(item.value for item in reopened.metric if item.label == "Total de horas al año") == "88"
    assert reopened.get("download_button")[0].proto.disabled
    assert not reopened.get("download_button")[-1].proto.disabled
    button(reopened, "Ejecutar y guardar planeación").click().run()
    assert load_planning(path)[1]["workload_scope"] == "lectiva"
    assert not reopened.get("download_button")[0].proto.disabled


def test_transversal_profile_edit_is_applied_only_after_saving(module_args):
    app = ready_virtual(open_app(module_args))
    path = planning_database(module_args[0], "Virtual")
    base = editor(app, "virtual:schedule_competencies_").value
    assert base.iloc[0]["Perfil docente"] == "Transversal general"
    edit(app, "virtual:schedule_competencies_", rows={0: {"Tipo": "Transversal", "Perfil docente": "Perfil corregido"}})
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not button(app, "Guardar clasificación de competencias").disabled
    assert load_virtual_schedules(path)["schedules"][0]["activities"][0]["teaching_profile"] == "Transversal general"
    button(app, "Guardar clasificación de competencias").click().run()
    assert not app.exception and not app.error
    assert not button(app, "Ejecutar y guardar planeación").disabled
    assert load_virtual_schedules(path)["schedules"][0]["activities"][0]["teaching_profile"] == "Perfil corregido"


def test_physical_education_profile_plant_and_export_preserve_presencial(module_args):
    from io import BytesIO
    from openpyxl import load_workbook
    from core.export import export_planning
    from test_virtual_schedules import FIXTURES

    app = open_app(module_args)
    save_presencial(app)
    presencial_before = Path(module_args[0]).read_bytes()
    path = planning_database(module_args[0], "Virtual")
    import_virtual_schedules(path, [(name, (FIXTURES / name).read_bytes())
                                    for name in ("adso_fases.xlsx", "ciberseguridad_fases.xlsx")])
    app.radio(key="nav_modality").set_value("Virtual").run()
    competencies = editor(app, "virtual:schedule_competencies_").value
    physical = competencies[competencies["Competencia"] == "230101507"]
    assert len(physical) == 1
    assert physical.iloc[0]["Perfil docente"] == "Cultura física"
    plant_config = json.loads(editor(app, "virtual:virtual_plant_").proto.columns)
    assert "Cultura física" in plant_config["Perfil"]["type_config"]["options"]
    edit(app, "virtual:virtual_programs_", rows={0: {"Nivel": "Tecnólogo"}, 1: {"Nivel": "Técnico"}})
    app.number_input(key="virtual:planning_year").set_value(2027)
    app.number_input(key="virtual:target_technical").set_value(250)
    app.number_input(key="virtual:target_technologist").set_value(250)
    for q, weight in enumerate([100, 0, 0, 0]):
        app.number_input(key=f"virtual:intake_weight_{q}").set_value(weight)
    app.run()
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception and not app.error
    first = load_planning(path)[1]
    assert any(row["Perfil"] == "Cultura física" for row in first["contracts"])
    edit(app, "virtual:virtual_plant_", added=[{"Nombre completo": "Docente de Educación Física", "Cédula": "456",
                                               "Tipo": "Transversal", "Perfil": "Cultura física"}])
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception and not app.error
    saved = load_planning(path)
    assert not any(row["Perfil"] == "Cultura física" for row in saved[1]["contracts"])
    assert [r for r in first["contracts"] if r["Tipo"] == "Técnico"] == [r for r in saved[1]["contracts"] if r["Tipo"] == "Técnico"]
    book = load_workbook(BytesIO(export_planning(*saved)), read_only=True)
    exported = list(book["Competencias unicas"].values)
    assert len([row for row in exported[1:] if row[0] == "230101507" and row[2] == "Cultura física"]) == 1
    assert any("Cultura física" in row for row in book["Cobertura por perfil"].values)
    assert Path(module_args[0]).read_bytes() == presencial_before
    reopened = open_app(module_args)
    reopened.radio(key="nav_modality").set_value("Virtual").run()
    assert not reopened.exception and not reopened.error
    assert not reopened.get("download_button")[0].proto.disabled


def test_virtual_contracts_show_each_slot_once_and_expose_separate_periods(module_args):
    app = ready_virtual(open_app(module_args))
    slots = next(frame.value for frame in app.dataframe if "Cupo de contratación" in frame.value.columns)
    periods = next(frame.value for frame in app.dataframe if "Período del cupo" in frame.value.columns)
    assert len(slots) == 2  # Un cupo técnico con pausa y un cupo de Bilingüismo.
    assert len(periods) == 3
    technical = slots[slots["Tipo"] == "Técnico"].iloc[0]
    assert technical["Número de períodos"] == 2
    assert technical["Pausas sin contratación"] == "2027-01-08 a 2027-01-14"
    peaks = next(frame.value for frame in app.dataframe if "Primer inicio del pico" in frame.value.columns)
    assert peaks["Pico simultáneo de contratistas"].sum() == 2
    assert next(item.value for item in app.metric if item.label == "Total de contratistas requeridos") == "1"
    app.selectbox(key="virtual:audit_profile").set_value("Bilingüismo").run()
    assert not app.exception and not app.error
    activities = next(frame.value for frame in app.dataframe if "Código de actividad" in frame.value.columns)
    assert len(activities) == 1
    assert activities.iloc[0]["Competencia"] == "240202501"
    assert activities.iloc[0]["Fase"] == "Fase 2 · Planeación"


def test_bilingual_profile_editor_cannot_assign_general_capacity(module_args):
    app = ready_virtual(open_app(module_args))
    path = planning_database(module_args[0], "Virtual")
    original = load_virtual_schedules(path)
    edit(app, "virtual:schedule_competencies_", rows={1: {"Perfil docente": "Transversal general"}})
    button(app, "Guardar clasificación de competencias").click().run()
    assert not app.exception
    assert any("perfil exclusivo Bilingüismo" in node.value for node in app.error)
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert load_virtual_schedules(path) == original
