from collections import defaultdict
from copy import deepcopy
from io import BytesIO
import json
import math

from openpyxl import load_workbook
import pandas as pd
import pytest

from core.config import PlanningRules
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from core.teaching_lines import prepare_teaching_lines, teaching_profile
from scripts.validate_curricula import verify
from test_curriculum_automation import malla

ADSO = "ANALISIS Y DESARROLLO DE SOFTWARE"
PROGRAMMING = "PROGRAMACION DE SOFTWARE"
SECURITY = "CONTROL DE LA SEGURIDAD DIGITAL"
METROLOGY = "ASEGURAMIENTO METROLOGICO INDUSTRIAL"
MEASUREMENTS = "MEDICIONES FISICAS"
COMPONENTS = "DESARROLLO DE COMPONENTES MECANICOS"
DRAWING = "DIBUJO MECANICO"


def scenario(tmp_path, programs, plant, *, weeks=11, transversal=False):
    files = []
    for name, level, hours in programs:
        content = malla(hours)
        if transversal:
            book = load_workbook(BytesIO(content))
            for sheet in book:
                sheet.append(["INGLES", "Resultado inglés", 20, "Bilingüismo"])
                sheet.append(["ÉTICA", "Resultado ética", 10, "Integralidad"])
            stream = BytesIO()
            book.save(stream)
            content = stream.getvalue()
        files.append((name + " - DIURNA.xlsx", content))
    catalog = import_curricula(tmp_path / "mallas.sqlite3", files)
    rows = [[name, area, "Planta " + str(i), str(i), "Planta", 0.0, True]
            for i, (name, area) in enumerate(plant, 1)]
    # Un contratista del reporte nunca aporta capacidad al cálculo proyectado.
    rows.append([programs[0][0], "Técnica", "Contrato del reporte", "999", "Contratista", 200, False])
    staff = pd.DataFrame(rows, columns=["Especialidad", "Área", "Nombre", "Documento", "Tipo Contrato", "Horas programadas actuales", "Es planta"])
    staff.attrs["specialties"] = staff[["Especialidad", "Área"]].drop_duplicates().to_dict("records")
    source = pd.DataFrame([{"Ficha": str(i), "Especialidad": name, "Nivel": level, "Jornada": "Diurna", "Trimestre actual": 1}
                           for i, (name, level, _) in enumerate(programs, 1)])
    targets = {level: sum(program[1] == level for program in programs) * 25 for level in ("Técnico", "Tecnólogo")}
    imported = prepare_ficha_import(source, staff, catalog, 2027, "fichas.xlsx", "f", 2026, 4)
    rules = PlanningRules(weeks_per_quarter=weeks)
    plan = execute_curriculum_plan(staff, imported, catalog, rules, targets, 2027, "planta.xlsx", "p")
    verify(plan)
    return staff, catalog, plan


@pytest.mark.parametrize("technician,technologist,line", [
    (PROGRAMMING, ADSO, "Software"), (SECURITY, ADSO, "Software"),
    (MEASUREMENTS, METROLOGY, "Metrología"), (DRAWING, COMPONENTS, "Mecánica")])
def test_plant_is_shared_between_compatible_technical_and_technologist_programs(tmp_path, technician, technologist, line):
    staff, _, plan = scenario(tmp_path, [(technician, "Técnico", [15] * 5), (technologist, "Tecnólogo", [15] * 5)],
                              [(technician, "Técnica")])
    assert plan["summary"]["pico_contratistas_total"] == 0
    assert {r["Especialidad"] for r in plan["technical_quarterly"]} == {"Línea · " + line}
    assert all(r["Instructores planta"] == 1 and r["Capacidad planta (h/sem)"] == 32 for r in plan["technical_quarterly"])
    assert all(math.isclose(r["Horas descontadas de planta (h/sem)"], 30) for r in plan["plant_balance"])
    january = [r for r in plan["monthly_assignments"] if r["Mes número"] == 1]
    assert {r["Programa"] for r in january} == {technician, technologist}
    assert {r["Instructor ID"] for r in january} == {"Planta 1"}
    assert staff.iloc[0]["Especialidad"] == technician  # El reporte original se conserva.


def test_contractor_capacity_and_rounding_are_shared_by_line_before_counting(tmp_path):
    _, _, plan = scenario(tmp_path, [(ADSO, "Tecnólogo", [15] * 5), (PROGRAMMING, "Técnico", [15] * 5)], [])
    assert all(r["Contratistas técnicos"] == 1 for r in plan["monthly"])
    january = [r for r in plan["monthly_assignments"] if r["Mes número"] == 1]
    assert len({r["Instructor ID"] for r in january}) == 1
    assert {r["Programa"] for r in january} == {ADSO, PROGRAMMING}
    assert math.isclose(sum(r["Horas asignadas (h/sem)"] for r in january), 30)


def test_software_security_and_both_levels_share_one_pool(tmp_path):
    _, _, plan = scenario(tmp_path, [(ADSO, "Tecnólogo", [15] * 5), (PROGRAMMING, "Técnico", [15] * 5),
                                     (SECURITY, "Técnico", [15] * 5)], [(ADSO, "Técnica")])
    assert len(plan["technical_quarterly"]) == 4
    assert all(r["Demanda técnica (h/sem)"] == 45 and r["Déficit antes de contratar (h/sem)"] == 13
               and r["Contratistas requeridos"] == 1 for r in plan["technical_quarterly"])


def test_plant_without_own_cohorts_covers_a_compatible_program(tmp_path):
    _, _, plan = scenario(tmp_path, [(METROLOGY, "Tecnólogo", [30] * 5)], [(MEASUREMENTS, "Técnica")])
    assert all(r["Capacidad planta (h/sem)"] == 32 and r["Contratistas requeridos"] == 0 for r in plan["technical_quarterly"])
    assert all(r["Horas libres de planta (h/sem)"] == pytest.approx(2) for r in plan["plant_balance"])


def test_unrelated_lines_do_not_exchange_hours_and_transversals_cover_all_programs(tmp_path):
    _, _, plan = scenario(tmp_path, [(ADSO, "Tecnólogo", [10] * 5), (PROGRAMMING, "Técnico", [10] * 5)],
        [(ADSO, "Técnica"), (DRAWING, "Técnica"), ("Bilingüismo", "Bilingüismo"), ("Integralidad", "Integralidad")], transversal=True)
    for row in plan["monthly_staffing"]:
        if row["Perfil"] == "Bilingüismo":
            assert row["Horas requeridas (h/sem)"] == pytest.approx(40)
            assert row["Horas a contratar (h/mes)"] == pytest.approx(8 * 11 / 3)
            assert row["Contratistas requeridos"] == 1
        elif row["Perfil"] == "Integralidad":
            assert row["Horas requeridas (h/sem)"] == pytest.approx(20)
            assert row["Contratistas requeridos"] == 0
    assert not any(row["Instructor ID"] == "Planta 2" for row in plan["monthly_assignments"])
    assert all(row["Contratistas transversales"] == 1 for row in plan["monthly"])


def test_line_contract_dates_follow_the_cohorts_curricular_quarters(tmp_path):
    _, _, plan = scenario(tmp_path, [(ADSO, "Tecnólogo", [1, 30, 20, 10, 0]),
                                    (PROGRAMMING, "Técnico", [1, 30, 20, 10, 0])], [(ADSO, "Técnica")])
    assert [r["Contratistas requeridos"] for r in plan["contracting_quarterly"]] == [1, 1, 0, 0]
    assert len(plan["contract_windows"]) == 1
    assert plan["contract_windows"][0]["Inicio"] == "2027-01-01"
    assert plan["contract_windows"][0]["Fin"] == "2027-06-30"
    assert plan["contract_windows"][0]["Perfil"] == "Línea · Software"


def test_shared_line_survives_manual_offer_edit_save_reopen_and_export(tmp_path):
    staff, catalog, before = scenario(tmp_path, [(ADSO, "Tecnólogo", [10] * 5), (PROGRAMMING, "Técnico", [10] * 5)], [(ADSO, "Técnica")])
    offers = {"planning_year": 2027, "programs": [{"Programa": row["Programa"], "Nivel": row["Nivel"],
        "Oferta T1": 0, "Oferta T2": 0, "Oferta T3": 0, "Oferta T4": 4} for row in before["offers_by_program"]]}
    after = execute_curriculum_plan(staff, before["ficha_import"], catalog, PlanningRules(**before["rules"]),
        before["targets_by_level"], 2027, "planta.xlsx", "p", manual_offers=offers)
    verify(after)
    assert [r["Contratistas requeridos"] for r in after["contracting_quarterly"]] == [0, 0, 0, 2]
    assert after["center"]["fichas_nuevas"] == 8
    assert {row["Programa"] for row in after["offers_by_program"]} == {ADSO, PROGRAMMING}
    path = tmp_path / "saved.sqlite3"
    save_planning(path, staff, after)
    stored_staff, stored = load_planning(path)
    assert stored["teaching_lines"] == after["teaching_lines"]
    replay = execute_curriculum_plan(stored_staff, stored["ficha_import"], catalog, PlanningRules(**stored["rules"]),
        stored["targets_by_level"], 2027, stored["source_name"], stored["source_digest"], manual_offers=stored["manual_offers"])
    assert replay == after
    book = BytesIO(export_planning(stored_staff, stored))
    assert set(pd.read_excel(book, sheet_name="Lineas docentes compatibles")["Programa compatible"]) == {ADSO, PROGRAMMING, SECURITY}
    assert set(pd.read_excel(book, sheet_name="Contratistas y fechas")["Perfil"]) == {"Línea · Software"}


def test_no_instructor_exceeds_capacity_across_fichas_programs_or_levels(tmp_path):
    _, _, plan = scenario(tmp_path, [(ADSO, "Tecnólogo", [30] * 5), (PROGRAMMING, "Técnico", [26] * 5),
                                     (SECURITY, "Técnico", [26] * 5)], [(ADSO, "Técnica"), (PROGRAMMING, "Técnica")])
    assigned = defaultdict(float)
    for row in plan["monthly_assignments"]:
        assigned[row["Mes número"], row["Instructor ID"]] += row["Horas asignadas (h/mes)"]
    for row in plan["monthly_instructors"]:
        amount = assigned[row["Mes número"], row["Instructor ID"]]
        assert amount == pytest.approx(row["Horas asignadas (h/mes)"])
        assert amount <= row["Capacidad (h/mes)"] + 1e-8
    assert all(row["Capacidad total de planta (h/sem)"] == pytest.approx(64) for row in plan["plant_balance"])


def test_conflicting_line_memberships_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"teaching_lines": [{"name": "Primera", "programs": [ADSO, PROGRAMMING]},
                                                 {"name": "Segunda", "programs": [ADSO, SECURITY]}]}), encoding="utf-8")
    monkeypatch.setattr("core.teaching_lines.POLICY_PATH", path)
    with pytest.raises(ValueError, match="una sola línea"):
        prepare_teaching_lines([], pd.DataFrame(), [])


def test_similar_names_are_not_assumed_compatible_and_aliases_keep_identity():
    lines = [{"name": "Software", "programs": [ADSO, PROGRAMMING, SECURITY]}]
    assert teaching_profile(" Análisis y desarrollo de software ", lines=lines) == "Software"
    assert teaching_profile("Otro programa de software", lines=lines) == "Otro programa de software"
