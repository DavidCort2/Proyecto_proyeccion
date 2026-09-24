from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
import pytest

from core.curriculum_store import import_curricula
from core.database import load_planning, reset_planning_database, save_planning
from core.export import export_planning
from core.virtual_schedule import lective_activities, parse_virtual_schedule
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules, save_virtual_activity_settings
from core.virtual_schedule_planner import VirtualRules, execute_virtual_schedule_plan
from test_curriculum_automation import malla

REAL_SCHEDULE = Path(__file__).parent / "fixtures/virtual_schedules/cronograma_adso.xlsx"


def schedule_bytes(program="Software", durations=(7, 7, 7), start=date(2026, 1, 1), productive_days=0):
    book = Workbook()
    sheet = book.active
    sheet.title = "Cronograma"
    end = start + timedelta(days=sum(durations) + productive_days - 1)
    sheet.append(["CRONOGRAMA GENERAL DE FORMACIÓN TITULADA VIRTUAL"])
    sheet.append(["Nombre de programa: " + program])
    sheet.append(["Fecha Inicio:", None, None, None, start])
    sheet.append(["Fecha Fin:", None, None, None, end])
    sheet.append(["Fases", "Actividades del proyecto", "Actividades de Aprendizaje", "Tiempo de duración estimado Meses",
                  "Tiempo de duración estimado Horas", "Fecha Inicio", "Fecha Final"])
    for i, days in enumerate(durations, 1):
        finish = start + timedelta(days=days - 1)
        code = "240202501" if i == 2 else "220501092"
        sheet.append([f"Fase {i} {'Análisis' if i == 1 else 'Planeación' if i == 2 else 'Ejecución'}", f"AP{i} Proyecto",
                      f"GA{i}-{code}-AA1 Actividad {i}", 1, f"{i * 100} HORAS", start, finish])
        start = finish + timedelta(days=1)
    if productive_days:
        sheet.append(["ETAPA PRODUCTIVA", None, None, None, "864 HORAS", start, end])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def configured_catalog(tmp_path, **kwargs):
    path = tmp_path / "virtual.sqlite3"
    catalog = import_virtual_schedules(path, [("Cronograma.xlsx", schedule_bytes(**kwargs))])
    for item in catalog["schedules"]:
        settings = [{"id": row["id"], "teaching_type": "Transversal" if i == 1 else "Técnico", "instructor_hours": (i + 1) * 10}
                    for i, row in enumerate(item["activities"])]
        catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"], settings)
    return path, catalog


def plan(catalog, **kwargs):
    arguments = dict(programs=[{"Programa": "Software", "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1}],
                     cohorts=[], plant=[], rules=VirtualRules(intake_weights=(100, 0, 0, 0)),
                     targets={"Técnico": 0, "Tecnólogo": 25}, year=2027,
                     offers=["2027-01-01", None, None, None])
    arguments.update(kwargs)
    return execute_virtual_schedule_plan(catalog, **arguments)


def test_reads_users_real_excel_without_duplicating_merged_hours():
    item = parse_virtual_schedule(REAL_SCHEDULE.read_bytes(), REAL_SCHEDULE.name)
    assert item["program"] == "Análisis y desarrollo de software"
    assert len(item["activities"]) == 101
    assert len(item["blocks"]) == 11
    assert {row["phase"] for row in item["blocks"]} == {
        "Inducción", "Fase 1 · Análisis", "Fase 2 · Planeación", "Fase 3 · Ejecución", "Fase 4 · Evaluación", "Etapa productiva"}
    assert sum(row["source_hours"] for row in item["blocks"] if row["phase"].startswith("Fase")) == 3072
    assert item["summaries"][0]["hours"] == 3120
    assert any("48 h" in warning for warning in item["warnings"])
    assert all(row["instructor_hours"] is None and row["teaching_type"] is None for row in item["activities"])
    row42 = next(row for row in item["activities"] if row["source_row"] == 42)
    assert row42["phase"] == "Fase 2 · Planeación" and row42["end"] == "2025-03-31"
    row77 = next(row for row in item["activities"] if row["source_row"] == 77)
    assert row77["phase"] == "Fase 3 · Ejecución" and row77["end"] == "2026-02-05"
    assert item["blocks"][-1]["source_hours"] == 864
    assert item["activities"][-1]["activity"] == "Seguimiento de etapa productiva"
    assert {row["competency"] for row in item["activities"] if row["source_row"] == 43} == {"220501093", "220501095"}
    assert len([row for row in item["activities"] if row["source_row"] == 77]) == 2


def test_classification_and_manual_hours_survive_reimport_but_changed_dates_need_review(tmp_path):
    path, catalog = configured_catalog(tmp_path)
    before = deepcopy(catalog)
    reimported = import_virtual_schedules(path, [("Cronograma.xlsx", schedule_bytes())])
    assert reimported["schedules"][0]["activities"] == before["schedules"][0]["activities"]
    changed = import_virtual_schedules(path, [("Cronograma.xlsx", schedule_bytes(durations=(14, 7, 7)))])
    assert all(row["instructor_hours"] is None for row in changed["schedules"][0]["activities"])
    assert changed["schedules"][0]["activities"][1]["teaching_type"] == "Transversal"
    assert load_virtual_schedules(path) == changed


def test_missing_docent_hours_block_calculation_instead_of_using_learner_hours(tmp_path):
    catalog = import_virtual_schedules(tmp_path / "db.sqlite3", [("Software.xlsx", schedule_bytes())])
    with pytest.raises(ValueError, match="faltan tipo u horas"):
        plan(catalog)


def test_variable_phase_lengths_exact_dates_and_shared_transversal_plant(tmp_path):
    _, catalog = configured_catalog(tmp_path, durations=(7, 14, 7))
    _, execution = plan(catalog, plant=[{"Tipo": "Transversal", "Perfil": "240202501", "Instructores de planta": 1}])
    assert execution["center"]["demanda_total_horas_anuales"] == pytest.approx(60)
    assert execution["summary"]["pico_contratistas_total"] == 1
    assert {row["Tipo"] for row in execution["contracts"]} == {"Técnico"}
    assert [(row["Inicio"], row["Fin"]) for row in execution["contracts"]] == [("2027-01-01", "2027-01-07"), ("2027-01-22", "2027-01-28")]
    assert execution["cohort_dates"][0]["Fecha fin prevista"] == "2027-01-28"
    assert "Jornada" not in str(execution) and "Trimestre" not in str(execution)


def test_continuing_dates_count_only_pending_activity_hours(tmp_path):
    _, catalog = configured_catalog(tmp_path)
    _, execution = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 100},
                        cohorts=[{"Programa": "Software", "Fichas que pasan": 2, "Fecha inicio formación": "2026-12-25"}])
    assert execution["center"]["fichas_nuevas"] == 2
    assert execution["center"]["demanda_total_horas_anuales"] == pytest.approx(220)
    assert execution["cohort_dates"][0]["Fases al iniciar la vigencia"] == "Fase 2 · Planeación"


def test_offers_are_four_dates_not_calendar_quarters(tmp_path):
    _, catalog = configured_catalog(tmp_path)
    _, execution = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 100}, rules=VirtualRules(intake_weights=(25, 25, 25, 25)),
                        offers=["2027-02-10", "2027-05-20", "2027-08-15", "2027-11-25"])
    assert [row["Fecha inicio formación"] for row in execution["cohort_dates"]] == ["2027-02-10", "2027-05-20", "2027-08-15", "2027-11-25"]
    assert execution["center"]["demanda_total_horas_anuales"] == pytest.approx(240)


def test_export_save_and_reset_keep_presencial_untouched(tmp_path):
    path, catalog = configured_catalog(tmp_path)
    presencial = tmp_path / "presencial.sqlite3"
    import_curricula(presencial, [("Software - DIURNA.xlsx", malla([12, 12]))])
    snapshot = presencial.read_bytes()
    staff, execution = plan(catalog)
    assert staff.empty
    save_planning(path, staff, execution)
    restored = load_planning(path)
    assert restored[1]["virtual_inputs"] == execution["virtual_inputs"]
    book = load_workbook(BytesIO(export_planning(*restored)), read_only=True)
    assert {"Cronogramas y fases", "Actividades y clasificacion", "Fechas de ofertas", "Contratistas y fechas"} <= set(book.sheetnames)
    assert all("jornada" not in name.lower() and "trimestre" not in name.lower() for name in book.sheetnames)
    book.close()
    reset_planning_database(path)
    assert load_virtual_schedules(path) == {"schedules": []}
    assert load_planning(path) is None
    assert presencial.read_bytes() == snapshot


@pytest.mark.parametrize("kwargs", [
    {"offers": [None] * 4}, {"offers": ["2026-01-01", None, None, None]},
    {"offers": ["2027-03-01", "2027-02-01", None, None]},
    {"plant": [{"Tipo": "Técnico", "Perfil": "240202501", "Instructores de planta": 1}]},
    {"plant": [{"Tipo": "Transversal", "Perfil": "240202501", "Instructores de planta": -1}]},
    {"cohorts": [{"Programa": "Software", "Fichas que pasan": 1, "Fecha inicio formación": "2025-01-01"}]},
])
def test_invalid_inputs_do_not_produce_a_plan(tmp_path, kwargs):
    _, catalog = configured_catalog(tmp_path)
    with pytest.raises(ValueError):
        plan(catalog, **kwargs)


def test_monthly_peak_does_not_hide_short_high_demand_and_partial_year_hours(tmp_path):
    path, catalog = configured_catalog(tmp_path, durations=(7,))
    item = catalog["schedules"][0]
    catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"],
                                             [{"id": item["activities"][0]["id"], "teaching_type": "Técnico", "instructor_hours": 80}])
    _, execution = plan(catalog, offers=["2027-12-29", None, None, None])
    assert execution["summary"]["pico_contratistas_total"] == 2
    assert execution["monthly"][-1]["Pico simultáneo de contratistas"] == 2
    assert execution["center"]["demanda_total_horas_anuales"] == pytest.approx(80 * 3 / 7)
    assert execution["contracts"][0]["Fin"] == "2027-12-31"


def test_transversal_capacity_is_shared_once_across_programs(tmp_path):
    path, catalog = configured_catalog(tmp_path)
    catalog = import_virtual_schedules(path, [("Redes.xlsx", schedule_bytes(program="Redes"))])
    item = next(item for item in catalog["schedules"] if item["program"] == "Redes")
    catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"], [
        {"id": row["id"], "teaching_type": "Transversal" if i == 1 else "Técnico", "instructor_hours": (i + 1) * 10}
        for i, row in enumerate(item["activities"])])
    staff, execution = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 50},
                            programs=[{"Programa": program, "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1}
                                      for program in ("Software", "Redes")],
                            plant=[{"Tipo": "Transversal", "Perfil": "240202501", "Instructores de planta": 1}])
    shared = next(row for row in execution["staffing"] if row["Tipo"] == "Transversal" and row["Inicio"] == "2027-01-08")
    assert len(staff) == 1
    assert shared["Horas requeridas (h/sem)"] == 40
    assert shared["Capacidad planta (h/sem)"] == 32
    assert shared["Horas a contratar"] == 8
    assert shared["Contratistas requeridos"] == 1
    assert execution["summary"]["pico_contratistas_total"] == 2  # Técnicos simultáneos, uno por programa.
    save_planning(path, staff, execution)
    assert load_planning(path)[0].iloc[0]["Área"] == "Transversal"


def test_real_excel_manual_workload_can_be_planned_saved_and_exported(tmp_path):
    path = tmp_path / "real.sqlite3"
    catalog = import_virtual_schedules(path, [(REAL_SCHEDULE.name, REAL_SCHEDULE.read_bytes())])
    item = catalog["schedules"][0]
    catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"], [
        {"id": row["id"], "teaching_type": "Transversal" if row["competency"] == "240202501" else "Técnico",
         "instructor_hours": 14 if row["phase"] == "Inducción" else 0} for row in item["activities"]])
    staff, execution = plan(catalog, programs=[{"Programa": item["program"], "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1}])
    assert execution["center"]["demanda_total_horas_anuales"] == 56
    assert len(execution["schedule_catalog"]["schedules"][0]["activities"]) == 101
    assert all(row["Horas instructor en vigencia"] == 0 for row in execution["activity_hours"] if row["Fase"] != "Inducción")
    save_planning(path, staff, execution)
    book = load_workbook(BytesIO(export_planning(*load_planning(path))), read_only=True)
    assert book["Actividades y clasificacion"].max_row == 102
    assert any("48 h" in str(row) for row in book["Observaciones del origen"].values)
    book.close()


def test_invalid_import_and_stale_classification_preserve_saved_schedule(tmp_path):
    path, before = configured_catalog(tmp_path)
    with pytest.raises(ValueError):
        import_virtual_schedules(path, [("Redes.xlsx", schedule_bytes(program="Redes")), ("Otro.xlsx", b"invalid")])
    assert load_virtual_schedules(path) == before
    item = before["schedules"][0]
    with pytest.raises(ValueError, match="cambió"):
        save_virtual_activity_settings(path, item["program_key"], "stale-source", [])
    assert load_virtual_schedules(path) == before
    with pytest.raises(ValueError, match="exclusivamente en Excel"):
        import_virtual_schedules(path, [("Cronograma.pdf", b"%PDF")])


@pytest.mark.parametrize("productive_hours", [None, 0, 1000])
def test_productive_stage_never_contributes_hours_or_contracts(tmp_path, productive_hours):
    _, catalog = configured_catalog(tmp_path, productive_days=14)
    # Simula un catálogo anterior con seguimiento productivo ya clasificado.
    productive = catalog["schedules"][0]["activities"][-1]
    productive.update(teaching_type="Transversal" if productive_hours is not None else None,
                      instructor_hours=productive_hours)
    _, execution = plan(catalog)
    assert execution["workload_scope"] == "lectiva"
    assert execution["center"]["demanda_total_horas_anuales"] == 60
    assert sum(row["Horas requeridas"] for row in execution["monthly"]) == 60
    assert execution["summary"]["pico_contratistas_total"] == 1
    assert all(row["Fase"] != "Etapa productiva" for row in execution["activity_hours"])
    assert all(row["Perfil"] != "Etapa productiva" for row in execution["staffing"])
    assert all(row["Fin"] <= "2027-01-21" for row in execution["contracts"])


def test_cohort_only_in_productive_stage_has_no_workload(tmp_path):
    _, catalog = configured_catalog(tmp_path, productive_days=14)
    catalog["schedules"][0]["activities"][-1].update(teaching_type="Técnico", instructor_hours=1000)
    _, execution = plan(catalog, cohorts=[{"Programa": "Software", "Fichas que pasan": 1, "Fecha inicio formación": "2026-12-11"}])
    assert execution["center"]["fichas_que_pasan"] == 1
    assert execution["center"]["fichas_nuevas"] == 0
    assert execution["center"]["demanda_total_horas_anuales"] == 0
    assert execution["summary"]["pico_contratistas_total"] == 0
    assert execution["contracts"] == []
    assert execution["activity_hours"] == []


def test_real_productive_hours_are_excluded_and_identified_in_export(tmp_path):
    path = tmp_path / "lectiva.sqlite3"
    catalog = import_virtual_schedules(path, [(REAL_SCHEDULE.name, REAL_SCHEDULE.read_bytes())])
    item = catalog["schedules"][0]
    # Solo se exige clasificar las 100 actividades lectivas; productiva queda sin diligenciar.
    catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"], [
        {"id": row["id"], "teaching_type": "Técnico", "instructor_hours": 0}
        for row in lective_activities(item)])
    assert catalog["schedules"][0]["activities"][-1]["instructor_hours"] is None
    catalog["schedules"][0]["activities"][-1].update(teaching_type="Técnico", instructor_hours=864)
    # En 2026 coinciden fin lectivo y etapa productiva del archivo real.
    staff, execution = plan(catalog, year=2026, offers=[None] * 4,
                            programs=[{"Programa": item["program"], "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1}],
                            cohorts=[{"Programa": item["program"], "Fichas que pasan": 1, "Fecha inicio formación": "2024-06-27"}])
    assert execution["center"]["demanda_total_horas_anuales"] == 0
    assert not execution["contracts"]
    save_planning(path, staff, execution)
    book = load_workbook(BytesIO(export_planning(*load_planning(path))), read_only=True)
    values = list(book["Actividades y clasificacion"].values)
    exported = [dict(zip(values[0], row)) for row in values[1:]]
    row = next(row for row in exported if row["phase"] == "Etapa productiva")
    assert row["instructor_hours"] == 864  # Se conserva como referencia histórica.
    assert row["Incluida en planeación"] is False
    assert row["Horas docentes por ficha para planeación"] == 0
    assert all("Etapa productiva" not in str(row) for row in book["Trazabilidad horas"].values)
    book.close()
