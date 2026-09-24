"""Un programa actualizado comparte oferta/planta, pero conserva las mallas por ficha."""
from copy import deepcopy
from io import BytesIO

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.config import PlanningRules
from core.curriculum import curriculum_key
from core.curriculum_planner import execute_curriculum_plan, prepare_ficha_import
from core.curriculum_store import import_curricula
from core.database import load_planning, save_planning
from core.export import export_planning
from core.program_transitions import load_presencial_transitions, program_key
from core.virtual_planning import execute_virtual_plan
from scripts.validate_curricula import verify
from test_curriculum_automation import malla
from test_curriculum_app import automatic_app_for_test, button


OLD = "DISEÑO E INTEGRACIÓN DE AUTOMATISMOS MECATRÓNICOS"
NEW = "AUTOMATIZACION DE SISTEMAS MECATRONICOS"


def staff_frame():
    staff = pd.DataFrame([
        {"Especialidad": name, "Área": "Técnica", "Nombre": f"Planta {number}", "Documento": str(number),
         "Tipo Contrato": "Planta", "Horas programadas actuales": 10.0, "Es planta": True}
        for number, name in enumerate([OLD, NEW], 1)
    ])
    staff.attrs["specialties"] = staff[["Especialidad", "Área"]].to_dict("records")
    return staff


def fichas_frame():
    return pd.DataFrame([
        {"Ficha": "anterior-diurna", "Especialidad": " diseno e integracion de automatismos mecatronicos. ",
         "Nivel": "Tecnólogo", "Jornada": "Diurna", "Trimestre actual": 1},
        {"Ficha": "anterior-mixta", "Especialidad": OLD,
         "Nivel": "Tecnólogo", "Jornada": "Mixta", "Trimestre actual": 3},
        {"Ficha": "vigente", "Especialidad": NEW,
         "Nivel": "Tecnólogo", "Jornada": "Diurna", "Trimestre actual": 1},
    ])


@pytest.fixture
def transition_catalog(tmp_path):
    path = tmp_path / "presencial.sqlite3"
    catalog = import_curricula(path, [
        (OLD + " - DIURNA.xlsx", malla([8, 16, 24])),
        (OLD + " - MIXTA.xlsx", malla([5, 10, 15, 20, 25])),
        (NEW + " - DIURNA.xlsx", malla([10, 30, 50, 70])),
    ])
    return path, catalog


def execute(catalog, *, frame=None, target=150, rules=None, staff=None):
    staff = staff if staff is not None else staff_frame()
    frame = frame if frame is not None else fichas_frame()
    imported = prepare_ficha_import(frame, staff, catalog, 2027, "fichas.xlsx", "f", 2026, 4)
    plan = execute_curriculum_plan(staff, imported, catalog, rules or PlanningRules(intake_weights=(100, 0, 0, 0)),
                                   {"Técnico": 0, "Tecnólogo": target}, 2027, "planta.xlsx", "p")
    return staff, plan


def test_original_curricula_are_not_merged_and_old_fichas_keep_their_end_dates(transition_catalog):
    _, catalog = transition_catalog
    staff, plan = execute(catalog)
    assert len(catalog["curricula"]) == 3
    assert curriculum_key(OLD, "Diurna") != curriculum_key(NEW, "Diurna")
    assert plan["center"]["fichas_que_pasan"] == 3
    assert plan["center"]["fichas_nuevas"] == 3
    assert all(row["Fichas nuevas"] == 0 for row in plan["distribution"] if program_key(row["Especialidad"]) == program_key(OLD))
    assert {row["Programa"] for row in plan["offers_by_program"]} == {NEW}
    assert plan["offers_by_program"][0]["Fichas del reporte"] == 3
    assert plan["offers_by_program"][0]["Total anual"] == 3
    old = [row for row in plan["ficha_import"]["detail"] if row["Ficha"].startswith("anterior")]
    assert {row["Duración (trimestres)"] for row in old} == {3, 5}
    assert {row["Fecha fin estimada"] for row in old} == {"2027-06-30"}
    assert {row["Programa de planeación"] for row in old} == {NEW}
    new = [row for row in plan["monthly_fichas"] if row["Tipo ficha"] == "Nueva proyectada"]
    assert {row["Programa"] for row in new} == {NEW}
    assert {row["Duración (trimestres)"] for row in new} == {4}
    assert {row["Fecha fin estimada"] for row in new} == {"2027-12-31"}
    assert plan["ficha_import"]["rows"] == fichas_frame().to_dict("records")
    assert staff["Especialidad"].tolist() == [OLD, NEW]


def test_shared_plant_is_counted_once_and_covers_both_versions(transition_catalog):
    _, plan = execute(transition_catalog[1])
    # T1: continuaciones 16+20+30, nuevas 3*10. T2: 24+25+50+3*30.
    # T3: continuación vigente 70 + 3*50. T4: solo las tres nuevas, 3*70.
    assert [row["Horas requeridas"] for row in plan["quarterly"]] == [1152, 2268, 2640, 2520]
    assert [row["contratistas_totales"] for row in plan["quarterly"]] == [1, 4, 4, 4]
    assert len(plan["technical_quarterly"]) == 4
    assert {row["Especialidad"] for row in plan["technical_quarterly"]} == {NEW}
    assert all(row["Instructores planta"] == 2 and row["Capacidad planta (h/sem)"] == 64 for row in plan["technical_quarterly"])
    assert len(plan["resources"]) == 1
    assert plan["resources"][0]["Instructores planta"] == 2
    assert len(plan["monthly_staffing"]) == 12 * 3  # Un perfil técnico y las dos áreas transversales.
    assert {row["Perfil"] for row in plan["monthly_assignments"]} == {NEW}
    assert any(row["Programa"].strip().lower().startswith("diseno") or row["Programa"] == OLD for row in plan["monthly_assignments"])
    assert len([row for row in plan["monthly_instructors"] if row["Tipo"] == "Planta" and row["Mes número"] == 1]) == 2
    verify(plan)


def test_popularity_changes_only_offer_order_and_family_is_apportioned_once(tmp_path, transition_catalog, monkeypatch):
    path, _ = transition_catalog
    catalog = import_curricula(path, [("Otro programa - DIURNA.xlsx", malla([10, 10, 10, 10]))])
    frame = pd.concat([fichas_frame(), pd.DataFrame([
        {"Ficha": f"otro-{i}", "Especialidad": "Otro programa", "Nivel": "Tecnólogo", "Jornada": "Diurna", "Trimestre actual": 1}
        for i in range(3)
    ])], ignore_index=True)
    rules = PlanningRules(intake_weights=(50, 0, 0, 50))
    _, popular = execute(catalog, frame=frame, target=300, rules=rules)
    offers = {row["Programa"]: row for row in popular["offers_by_program"]}
    assert [offers[NEW][f"Oferta T{q}"] for q in range(1, 5)] == [0, 0, 0, 3]
    assert [offers["Otro programa"][f"Oferta T{q}"] for q in range(1, 5)] == [3, 0, 0, 0]
    assert offers[NEW]["Fichas del reporte"] == offers["Otro programa"]["Fichas del reporte"] == 3
    normal = [{**row, "popular": False} for row in load_presencial_transitions()]
    monkeypatch.setattr("core.program_transitions.load_presencial_transitions", lambda: normal)
    _, by_report = execute(catalog, frame=frame, target=300, rules=rules)
    assert [(row["Programa"], row["Total anual"]) for row in by_report["offers_by_program"]] == [(row["Programa"], row["Total anual"]) for row in popular["offers_by_program"]]
    assert by_report["offers_by_program"][0]["Oferta T1"] > 0
    assert [row["Fichas nuevas"] for row in by_report["quarterly"]] == [row["Fichas nuevas"] for row in popular["quarterly"]]
    verify(popular)


@pytest.mark.parametrize("indices", [[0, 1], [1]])
def test_successor_can_receive_new_intakes_even_if_only_old_program_is_in_report(transition_catalog, indices):
    frame = fichas_frame().iloc[indices].copy()
    _, plan = execute(transition_catalog[1], frame=frame, target=(len(frame) + 2) * 25)
    assert plan["center"]["fichas_nuevas"] == 2
    assert len(plan["offers_by_program"]) == 1
    assert plan["offers_by_program"][0]["Fichas del reporte"] == len(frame)
    new = [row for row in plan["distribution"] if row["Fichas nuevas"]]
    assert len(new) == 1 and new[0]["Especialidad"] == NEW and new[0]["Jornada"] == "Diurna"
    assert new[0]["Fichas que pasan"] == 0
    verify(plan)


def test_missing_successor_malla_blocks_new_intakes_but_not_old_continuations(transition_catalog):
    catalog = deepcopy(transition_catalog[1])
    catalog["curricula"] = [item for item in catalog["curricula"] if item["program"] != NEW]
    frame = fichas_frame().iloc[:2]
    _, continuing = execute(catalog, frame=frame, target=50)
    assert continuing["center"]["fichas_nuevas"] == 0
    assert continuing["center"]["demanda_total_horas_anuales"] == (16 + 20 + 24 + 25) * 12
    with pytest.raises(ValueError, match="Cargue la malla de AUTOMATIZACION"):
        execute(catalog, frame=frame, target=75)


def test_successor_with_both_curricula_inherits_combined_shift_participation(transition_catalog):
    path, _ = transition_catalog
    catalog = import_curricula(path, [(NEW + " - MIXTA.xlsx", malla([12, 13]))])
    _, plan = execute(catalog)
    new = {row["Jornada"]: row["Fichas nuevas"] for row in plan["distribution"] if row["Especialidad"] == NEW}
    # Reporte combinado: dos diurnas y una mixta; las antiguas siguen con 0 ingresos.
    assert new == {"Diurna": 2, "Mixta": 1}
    mixed = [row for row in plan["monthly_fichas"] if row["Tipo ficha"] == "Nueva proyectada" and row["Jornada"] == "Mixta"]
    assert {row["Duración (trimestres)"] for row in mixed} == {2}
    assert {row["Fecha fin estimada"] for row in mixed} == {"2027-06-30"}
    assert {row["Horas requeridas (h/sem)"] for row in mixed} == {12, 13}
    verify(plan)


def test_missing_original_malla_cannot_be_substituted_with_successor_malla(transition_catalog):
    catalog = deepcopy(transition_catalog[1])
    catalog["curricula"] = [item for item in catalog["curricula"] if item["program"] == NEW]
    with pytest.raises(ValueError, match="Faltan mallas"):
        execute(catalog)


def test_duplicate_instructor_identification_is_not_counted_twice(transition_catalog):
    staff = staff_frame()
    staff.loc[1, "Documento"] = staff.loc[0, "Documento"]
    with pytest.raises(ValueError, match="documentos de instructores repetidos"):
        execute(transition_catalog[1], staff=staff)


def test_transition_policy_and_tables_survive_save_export_and_app_reopen(transition_catalog):
    path, catalog = transition_catalog
    staff, plan = execute(catalog)
    save_planning(path, staff, plan)
    reopened_staff, saved = load_planning(path)
    assert saved["program_transitions"] == plan["program_transitions"]
    output = BytesIO(export_planning(reopened_staff, saved))
    offers = pd.read_excel(output, sheet_name="Fichas por oferta")
    assert offers["Programa"].tolist() == [NEW]
    assert offers.iloc[0]["Total anual"] == 3
    transitions = pd.read_excel(output, sheet_name="Actualizacion de programas")
    assert transitions.iloc[0]["Programa vigente · nuevas ofertas"] == NEW
    app = AppTest.from_function(automatic_app_for_test, args=(str(path), "", "", []), default_timeout=30).run()
    assert not app.exception and not app.error
    assert not button(app, "Ejecutar y guardar planeación").disabled
    section = next(node for node in app.expander if node.label == "Programas actualizados y planta compartida")
    assert not section.proto.expanded
    assert section.dataframe[0].value.iloc[0]["Programa vigente · nuevas ofertas"] == NEW
    section = next(node for node in app.expander if node.label == "Fichas nuevas por programa y oferta")
    assert section.dataframe[0].value["Programa"].tolist() == [NEW]
    button(app, "Ejecutar y guardar planeación").click().run()
    assert not app.exception and not app.error
    saved_staff, saved_plan = load_planning(path)
    assert saved_staff["Especialidad"].tolist() == [OLD, NEW]
    assert saved_plan["ficha_import"]["rows"] == fichas_frame().to_dict("records")
    assert saved_plan["offers_by_program"] == plan["offers_by_program"]
    app = AppTest.from_function(automatic_app_for_test, args=(str(path), "", "", []), default_timeout=30).run()
    assert not app.exception
    assert not any("pendientes de ejecutar" in row.value for row in app.warning)


def test_presencial_replacement_and_popularity_do_not_change_virtual_programs(tmp_path):
    catalog = import_curricula(tmp_path / "virtual.sqlite3", [
        (name + " - VIRTUAL.xlsx", malla([10, 20])) for name in [OLD, NEW]
    ])
    _, plan = execute_virtual_plan(catalog,
        programs=[{"Programa": name, "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1} for name in [OLD, NEW]],
        cohorts=[], plant=[], rules=PlanningRules(), targets={"Técnico": 0, "Tecnólogo": 100}, year=2027)
    assert "program_transitions" not in plan
    assert {row["Programa"] for row in plan["offers_by_program"]} == {OLD, NEW}
    assert all(row["Total anual"] == 2 for row in plan["offers_by_program"])
