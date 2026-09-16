from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from core.database import load_planning


def app_for_test(db_path, excel_path):
    from pathlib import Path
    import app

    app.DATABASE_PATH = Path(db_path)
    app.DEFAULT_EXCEL = Path(excel_path)
    app.main()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_execute_reload_and_replace_file(tmp_path):
    db = tmp_path / "planning.sqlite3"
    report = tmp_path / "reporte.xlsx"
    report.write_bytes((Path(__file__).resolve().parents[1] / "data/reporteInstructores_2026_4.xlsx").read_bytes())
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    assert not app.exception
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()
    app.radio[0].set_value("Usar reporte incluido").run()
    assert not app.exception
    assert not db.exists()  # Seleccionar un archivo no escribe ni ejecuta.
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert len(load_planning(db)[0]) == 71
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

    # Otro archivo con el mismo nombre debe renovar el editor y reemplazar SQLite.
    pd.DataFrame([
        ["Nombre", "Documento", "Tipo Contrato", "Total Horas"],
        ["NUEVA ESPECIALIDAD"], ["Nueva Profesora", "001", "Planta", 32],
    ]).to_excel(report, index=False, header=False)
    app.run()
    assert not app.exception
    assert app.session_state["distribution_base"]["Especialidad"].tolist() == ["NUEVA ESPECIALIDAD"]
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


def test_inconsistent_distribution_blocks_execution(tmp_path):
    db = tmp_path / "planning.sqlite3"
    report = Path(__file__).resolve().parents[1] / "data/reporteInstructores_2026_4.xlsx"
    app = AppTest.from_function(app_for_test, args=(str(db), str(report)), default_timeout=20).run()
    app.radio[0].set_value("Usar reporte incluido").run()
    app.number_input(key="target_learners").set_value(1000).run()
    assert button(app, "Ejecutar y guardar planeación").disabled
    assert not db.exists()
    button(app, "Generar distribución proporcional").click().run()
    assert not button(app, "Ejecutar y guardar planeación").disabled
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception
    assert load_planning(db)[1]["center"]["fichas_nuevas"] == 40
