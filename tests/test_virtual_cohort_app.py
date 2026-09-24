from pathlib import Path

from core.database import load_planning, save_planning
from core.planning_modules import planning_database
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules
from test_planning_modules_app import (
    app_args, button, edit, editor, editor_events, module_args, open_app, ready_virtual,
)
from test_virtual_schedules import plan, schedule_bytes


def metric(app, label):
    return next(row.value for row in app.metric if row.label == label)


def add_fichas(app, quantity, program="Software"):
    app.selectbox(key="virtual:cohort_batch_program").select(program)
    app.number_input(key="virtual:cohort_batch_quantity").set_value(quantity)
    button(app, "Agregar fichas").click().run()
    assert not app.exception and not app.error


def test_add_ten_with_individual_dates_count_calculate_save_and_reopen(module_args):
    app = ready_virtual(open_app(module_args))
    add_fichas(app, 10)
    frame = editor(app, "virtual:virtual_cohorts_").value
    assert len(frame) == 10
    assert frame["Programa"].tolist() == ["Software"] * 10
    assert "Fichas que pasan" not in frame.columns
    assert metric(app, "Total de fichas que pasan") == "10"
    assert metric(app, "Fechas pendientes") == "10"
    assert button(app, "Ejecutar y guardar planeación").disabled
    edit(app, "virtual:virtual_cohorts_", rows={i: {"Fecha fin lectiva": "2027-01-07" if i < 5 else "2027-01-14"} for i in range(10)})
    assert metric(app, "Fechas pendientes") == "0"
    assert metric(app, "Total de horas al año") == "150"  # 5 × 10 h pendientes + 5 × 20 h.
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception and not app.error
    saved = load_planning(planning_database(module_args[0], "Virtual"))[1]
    assert len(saved["virtual_inputs"]["cohorts"]) == 10
    assert all(row["Fichas que pasan"] == 1 for row in saved["virtual_inputs"]["cohorts"])
    assert saved["center"]["fichas_que_pasan"] == 10
    assert not Path(module_args[0]).exists()
    reopened = open_app(module_args)
    reopened.radio(key="nav_modality").set_value("Virtual").run()
    assert not reopened.exception and not reopened.error
    assert metric(reopened, "Total de fichas que pasan") == "10"
    assert metric(reopened, "Total de horas al año") == "150"
    assert not reopened.get("download_button")[0].proto.disabled
    dates = editor(reopened, "virtual:virtual_cohorts_").value["Fecha fin lectiva"].dt.strftime("%Y-%m-%d").tolist()
    assert dates == ["2027-01-07"] * 5 + ["2027-01-14"] * 5


def test_add_again_preserves_edits_deletions_plant_and_navigation(module_args):
    app = ready_virtual(open_app(module_args))
    add_fichas(app, 2)
    edit(app, "virtual:virtual_cohorts_", rows={i: {"Fecha fin lectiva": "2027-01-14"} for i in range(2)})
    edit(app, "virtual:virtual_plant_", added=[{"Nombre completo": "Ana Pérez", "Cédula": "00123", "Tipo": "Técnico", "Perfil": "Software"}])
    add_fichas(app, 3)
    assert metric(app, "Total de fichas que pasan") == "5"
    assert metric(app, "Fechas pendientes") == "3"
    edit(app, "virtual:virtual_cohorts_", deleted=[0, 3])
    assert metric(app, "Total de fichas que pasan") == "3"
    assert metric(app, "Fechas pendientes") == "2"
    app.radio(key="nav_modality").set_value("Presencial").run()
    app.radio(key="nav_modality").set_value("Virtual").run()
    assert not app.exception and not app.error
    assert metric(app, "Total de fichas que pasan") == "3"
    add_fichas(app, 1)
    assert metric(app, "Total de fichas que pasan") == "4"
    assert metric(app, "Fechas pendientes") == "3"
    draft = app.session_state["virtual:schedule_manual_draft"]
    assert draft["plant"][0]["Cédula"] == "00123"
    assert draft["programs"][0]["Nivel"] == "Tecnólogo"
    assert [row["Fecha fin lectiva"] for row in draft["cohorts"]] == ["2027-01-14", None, None, None]


def test_old_groups_expand_without_losing_counts_and_program_counter_updates(module_args):
    path = planning_database(module_args[0], "Virtual")
    catalog = import_virtual_schedules(path, [("Software.xlsx", schedule_bytes())])
    staff, execution = plan(catalog, cohorts=[{"Programa": "Software", "Fichas que pasan": 3, "Fecha fin lectiva": "2027-01-14"}])
    save_planning(path, staff, execution)
    import_virtual_schedules(path, [("Redes.xlsx", schedule_bytes(program="Redes"))])
    app = open_app(module_args)
    app.radio(key="nav_modality").set_value("Virtual").run()
    assert not app.exception and not app.error
    assert metric(app, "Total de fichas que pasan") == "3"
    assert metric(app, "Fechas pendientes") == "0"
    frame = editor(app, "virtual:virtual_cohorts_").value
    assert len(frame) == 3 and frame["Fecha fin lectiva"].notna().all()
    add_fichas(app, 2, "Redes")
    assert metric(app, "Total de fichas que pasan") == "5"
    summary = next(node.value for node in app.dataframe if list(node.value.columns) == ["Programa", "Fichas", "Fechas pendientes"])
    assert summary.to_dict("records") == [
        {"Programa": "Redes", "Fichas": 2, "Fechas pendientes": 2},
        {"Programa": "Software", "Fichas": 3, "Fechas pendientes": 0},
    ]
    # Las filas nuevas no reemplazan la planeación guardada mientras faltan fechas.
    assert load_planning(path)[1]["virtual_inputs"]["cohorts"] == execution["virtual_inputs"]["cohorts"]
    assert len(load_virtual_schedules(path)["schedules"]) == 2


def test_open_session_keeps_unsaved_old_groups_and_incomplete_rows(module_args):
    app = ready_virtual(open_app(module_args))
    # Simula el borrador del antiguo editor al actualizar una sesión abierta.
    draft = dict(app.session_state["virtual:schedule_manual_draft"])
    draft["cohorts"] = [
        {"Programa": "Software", "Fichas que pasan": 2, "Fecha fin lectiva": "2027-01-14"},
        {"Programa": "Software", "Fichas que pasan": None, "Fecha fin lectiva": None},
    ]
    app.session_state["virtual:schedule_manual_draft"] = draft
    del app.session_state["virtual:cohort_parent_revision"]
    app.run()
    assert not app.exception and not app.error
    assert metric(app, "Total de fichas que pasan") == "3"
    assert metric(app, "Fechas pendientes") == "1"
    assert len(editor(app, "virtual:virtual_cohorts_").value) == 3
