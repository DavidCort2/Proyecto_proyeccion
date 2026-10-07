from pathlib import Path

from core.complementary_store import load_complementary
from core.planning_modules import complementary_database, planning_database
from test_curriculum_app import app_args, button
from test_planning_modules_app import (module_args, editor_events, open_app, ready_virtual,
                                      save_presencial, edit, editor)


def configure(app, modality, target=25, duration=10):
    app.radio(key="nav_training").set_value("Complementaria")
    app.radio(key="nav_modality").set_value(modality).run()
    prefix = "complementaria:" + modality.lower() + ":"
    app.number_input(key="complementaria:shared:planning_year").set_value(2027)
    app.number_input(key=prefix + "target_learners").set_value(target)
    app.number_input(key=prefix + "learners_per_course").set_value(25)
    app.number_input(key=prefix + "duration_hours").set_value(float(duration)).run()
    assert not app.exception and not app.error
    return app


def test_joint_complementary_plan_uses_virtual_contractors_in_both_modalities(module_args):
    app = ready_virtual(open_app(module_args))
    button(app, "Ejecutar y guardar planeación").click().run()
    virtual = planning_database(module_args[0], "Virtual")
    original = virtual.read_bytes()
    configure(app, "Presencial")
    configure(app, "Virtual")
    button(app, "Ejecutar y guardar Complementaria").click().run()
    assert not app.exception and not app.error
    path = complementary_database(module_args[0])
    saved = load_complementary(path)
    assert saved["summary"]["cursos_con_apoyo_titulada"] == 2
    assert saved["summary"]["pico_contratistas_adicionales"] == 0
    assert len({row["Instructor ID"] for row in saved["courses"]}) == 1
    assert {row["Modalidad"] for row in saved["courses"]} == {"Presencial", "Virtual"}
    assert virtual.read_bytes() == original
    assert not Path(module_args[0]).exists()
    assert not app.get("download_button")[0].proto.disabled
    reopened = open_app(module_args)
    reopened.radio(key="nav_training").set_value("Complementaria").run()
    assert reopened.number_input(key="complementaria:presencial:target_learners").value == 25
    assert not reopened.exception and not reopened.get("download_button")[0].proto.disabled


def test_own_plant_saved_with_full_capacity_and_inputs_survive_navigation(module_args):
    app = configure(open_app(module_args), "Presencial", target=100, duration=40)
    edit(app, "complementaria:presencial:plant_", added=[{
        "Nombre completo": "Ana Pérez", "Cédula": "00123", "Horas semanales": 32.0}])
    app.radio(key="nav_modality").set_value("Virtual").run()
    app.radio(key="nav_training").set_value("Titulada").run()
    app.radio(key="nav_training").set_value("Complementaria")
    app.radio(key="nav_modality").set_value("Presencial").run()
    assert not app.exception and not app.error
    assert app.number_input(key="complementaria:presencial:target_learners").value == 100
    button(app, "Ejecutar y guardar Complementaria").click().run()
    saved = load_complementary(complementary_database(module_args[0]))
    assert saved["inputs"]["Presencial"]["plant"][0]["Cédula"] == "00123"
    assert saved["summary"]["cursos_con_planta"] == 4
    assert saved["summary"]["pico_contratistas_adicionales"] == 0
    assert len(saved["monthly_instructors"]) == 12
    assert all(row["Total programado (h/mes)"] == row["Capacidad (h/mes)"] for row in saved["monthly_instructors"])
    assert len(editor(app, "complementaria:presencial:plant_").value) == 1
    # Una actualización vacía del control conserva la última duración ingresada.
    app.number_input(key="complementaria:presencial:duration_hours").set_value(None).run()
    assert app.number_input(key="complementaria:presencial:duration_hours").value == 40
    assert not button(app, "Ejecutar y guardar Complementaria").disabled
    assert load_complementary(complementary_database(module_args[0])) == saved


def test_duration_survives_navigation_save_and_reopen_for_each_modality(module_args):
    app = configure(open_app(module_args), "Presencial", duration=48.5)
    configure(app, "Virtual", duration=60)
    app.number_input(key="complementaria:virtual:target_learners").set_value(50).run()
    assert app.number_input(key="complementaria:virtual:duration_hours").value == 60
    app.radio(key="nav_training").set_value("Titulada").run()
    app.radio(key="nav_training").set_value("Complementaria").run()
    assert app.number_input(key="complementaria:virtual:duration_hours").value == 60
    app.radio(key="nav_modality").set_value("Presencial").run()
    assert app.number_input(key="complementaria:presencial:duration_hours").value == 48.5
    button(app, "Ejecutar y guardar Complementaria").click().run()
    saved = load_complementary(complementary_database(module_args[0]))
    assert saved["inputs"]["Presencial"]["duration_hours"] == 48.5
    assert saved["inputs"]["Virtual"]["duration_hours"] == 60
    reopened = open_app(module_args)
    reopened.radio(key="nav_training").set_value("Complementaria").run()
    assert reopened.number_input(key="complementaria:presencial:duration_hours").value == 48.5
    reopened.number_input(key="complementaria:presencial:duration_hours").set_value(52).run()
    reopened.number_input(key="complementaria:presencial:target_learners").set_value(75).run()
    reopened.radio(key="nav_modality").set_value("Virtual").run()
    assert reopened.number_input(key="complementaria:virtual:duration_hours").value == 60
    reopened.number_input(key="complementaria:virtual:duration_hours").set_value(None).run()
    assert reopened.number_input(key="complementaria:virtual:duration_hours").value == 60
    reopened.radio(key="nav_modality").set_value("Presencial").run()
    assert reopened.number_input(key="complementaria:presencial:duration_hours").value == 52
    button(reopened, "Ejecutar y guardar Complementaria").click().run()
    updated = load_complementary(complementary_database(module_args[0]))
    assert updated["inputs"]["Presencial"]["duration_hours"] == 52
    assert updated["inputs"]["Virtual"]["duration_hours"] == 60
    assert updated["summary"]["horas_requeridas"] == 3 * 52 + 2 * 60
    assert not reopened.exception and not reopened.error


def test_titulada_edits_refresh_complementary_preview_without_writing_either_snapshot(module_args):
    app = open_app(module_args)
    save_presencial(app)
    presencial = Path(module_args[0]).read_bytes()
    ready_virtual(app)
    button(app, "Ejecutar y guardar planeación").click().run()
    configure(app, "Presencial", target=250, duration=40)
    button(app, "Ejecutar y guardar Complementaria").click().run()
    path = complementary_database(module_args[0])
    previous = load_complementary(path)
    app.radio(key="nav_training").set_value("Titulada")
    app.radio(key="nav_modality").set_value("Virtual").run()
    app.number_input(key="virtual:target_technologist").set_value(25).run()
    button(app, "Ejecutar y guardar planeación").click().run()
    virtual_path = planning_database(module_args[0], "Virtual")
    virtual = virtual_path.read_bytes()
    app.radio(key="nav_training").set_value("Complementaria").run()
    assert not app.exception and not app.error
    assert app.get("download_button")[0].proto.disabled
    assert load_complementary(path) == previous
    button(app, "Ejecutar y guardar Complementaria").click().run()
    assert not app.exception and not app.error
    assert load_complementary(path)["sources"] != previous["sources"]
    assert virtual_path.read_bytes() == virtual
    assert Path(module_args[0]).read_bytes() == presencial


def test_presencial_reset_preserves_complementary_inputs_and_saved_database(module_args):
    app = open_app(module_args)
    save_presencial(app)
    configure(app, "Presencial", target=50, duration=48)
    button(app, "Ejecutar y guardar Complementaria").click().run()
    path = complementary_database(module_args[0])
    snapshot = path.read_bytes()
    app.radio(key="nav_training").set_value("Titulada").run()
    app.checkbox(key="confirm_system_reset").check().run()
    button(app, "Formatear sistema").click().run()
    assert not app.exception and path.read_bytes() == snapshot
    app.radio(key="nav_training").set_value("Complementaria").run()
    assert app.number_input(key="complementaria:presencial:target_learners").value == 50
    assert app.number_input(key="complementaria:presencial:duration_hours").value == 48
    assert not app.exception and not app.error
