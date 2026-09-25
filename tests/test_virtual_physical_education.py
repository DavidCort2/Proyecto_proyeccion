"""Perfil exclusivo compartido entre programas, con sus propios períodos lectivos."""
from copy import deepcopy
from datetime import date, timedelta
import json
import sqlite3

import pytest

from core.virtual_competencies import assign_teaching_profiles, competency_rows
from core.virtual_schedule_planner import VirtualRules, staff_options, virtual_schedule_templates
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules
from core.virtual_staffing import workdays
from test_virtual_schedules import FIXTURES, person, plan, real_catalog, save_choices

CODE = "230101507"
PROFILE = "Cultura física"


def program_rows(catalog):
    return [{"Programa": item["program"], "Incluir": True,
             "Nivel": "Tecnólogo" if index == 0 else "Técnico", "Peso de oferta": 1}
            for index, item in enumerate(catalog["schedules"])]


def physical_rows(result, table="activity_hours"):
    return [row for row in result[table] if row["Perfil"] == PROFILE]


def test_shared_identity_does_not_depend_on_result_wording_or_program_level(tmp_path):
    catalog = real_catalog(tmp_path)
    activities = [[row for row in item["activities"] if row["competency"] == CODE] for item in catalog["schedules"]]
    assert [len(rows) for rows in activities] == [4, 4]
    assert {r["activity"] for r in activities[0]} != {r["activity"] for r in activities[1]}
    assert all(r["teaching_profile"] == PROFILE and r["teaching_type"] == "Transversal" for rows in activities for r in rows)
    assert len([row for row in competency_rows(catalog) if row["Competencia"] == CODE]) == 1
    assert staff_options(catalog)["Transversal"].count(PROFILE) == 1
    # Aun sin palabras clave en los resultados, el código mantiene su identidad.
    for rows in activities:
        for i, row in enumerate(rows):
            row.update(activity=f"Resultado reformulado {i}", teaching_type="Técnico",
                       teaching_profile="Transversal general", profile_source="manual")
        assign_teaching_profiles(rows)
        assert all(row["teaching_type"] == "Transversal" and row["teaching_profile"] == PROFILE for row in rows)
    # Física de ciencias naturales no es educación física.
    assert {row["teaching_profile"] for item in catalog["schedules"] for row in item["activities"]
            if row["competency"] == "220201501"} == {"Transversal general"}


@pytest.mark.parametrize("index,offer,start,finish", [
    (0, 0, "2027-10-01", "2027-12-08"),
    (1, 0, "2027-05-17", "2027-08-16"),
    (1, 1, "2027-08-17", "2027-11-15"),
])
def test_new_fichas_use_the_program_block_and_offer_date(tmp_path, index, offer, start, finish):
    catalog = real_catalog(tmp_path)
    program = program_rows(catalog)[index]
    targets = {"Técnico": 0, "Tecnólogo": 0, program["Nivel"]: 250}
    weights = tuple(100 if i == offer else 0 for i in range(4))
    _, result = plan(catalog, programs=[program], targets=targets, rules=VirtualRules(intake_weights=weights))
    activity, = physical_rows(result)
    assert (activity["Inicio"], activity["Fin"]) == (start, finish)
    assert activity["Competencias"] == CODE
    assert activity["Fichas"] == 10
    assert activity["Horas semanales por ficha"] == 2
    expected = 10 * 2 * workdays(date.fromisoformat(start), date.fromisoformat(finish) + timedelta(days=1)) / 5
    assert activity["Horas instructor en vigencia"] == pytest.approx(expected)
    assert sum(r["Horas requeridas"] for r in physical_rows(result, "staffing")) == pytest.approx(expected)
    contract, = physical_rows(result, "contracts")
    assert (contract["Inicio"], contract["Fin"]) == (start, finish)
    assert contract["Cupo"] == 1
    assert all(r["Contratistas requeridos"] == 0 for r in physical_rows(result, "staffing")
               if r["Fin"] < start or r["Inicio"] > finish)


@pytest.mark.parametrize("index,end,start,finish", [
    (0, "2028-06-30", "2027-07-01", "2027-09-08"),
    (1, "2027-06-30", "2027-02-15", "2027-05-16"),
])
def test_continuing_fichas_reconstruct_only_their_pending_physical_block(tmp_path, index, end, start, finish):
    catalog = real_catalog(tmp_path)
    program = program_rows(catalog)[index]
    _, result = plan(catalog, programs=[program], targets={"Técnico": 0, "Tecnólogo": 0},
                     cohorts=[{"Programa": program["Programa"], "Fichas que pasan": 10, "Fecha fin lectiva": end}])
    activity, = physical_rows(result)
    assert (activity["Inicio"], activity["Fin"]) == (start, finish)
    assert result["center"]["fichas_nuevas"] == 0
    assert max(r["Horas requeridas (h/sem)"] for r in physical_rows(result, "staffing")) == 20
    assert max(r["Contratistas requeridos"] for r in physical_rows(result, "staffing")) == 1


def test_already_completed_physical_block_is_not_repeated_and_later_offers_wait(tmp_path):
    catalog = real_catalog(tmp_path)
    programs = program_rows(catalog)
    _, result = plan(catalog, programs=programs, targets={"Técnico": 250, "Tecnólogo": 250},
                     rules=VirtualRules(intake_weights=(0, 0, 0, 100)),
                     cohorts=[{"Programa": programs[0]["Programa"], "Fichas que pasan": 1,
                               "Fecha fin lectiva": "2027-09-30"}])
    assert result["center"]["fichas_nuevas"] == 19
    assert physical_rows(result) == []
    assert physical_rows(result, "contracts") == []


@pytest.mark.parametrize("adso,cyber,plant_profile,expected", [
    (10, 10, None, 1), (11, 10, None, 2),
    (10, 10, "Transversal general", 1),
    (8, 8, PROFILE, 0), (9, 8, PROFILE, 1), (10, 10, PROFILE, 1),
])
def test_one_specialist_shares_capacity_between_new_and_continuing_programs(tmp_path, adso, cyber, plant_profile, expected):
    catalog = real_catalog(tmp_path)
    programs = program_rows(catalog)
    _, result = plan(catalog, programs=programs,
                     cohorts=[{"Programa": programs[0]["Programa"], "Fichas que pasan": adso,
                               "Fecha fin lectiva": "2028-04-30"}],
                     targets={"Técnico": cyber * 25, "Tecnólogo": adso * 25},
                     plant=[person(kind="Transversal", profile=plant_profile)] if plant_profile else [])
    rows = physical_rows(result, "staffing")
    peak = max(rows, key=lambda r: r["Fichas activas"])
    assert peak["Fichas activas"] == adso + cyber
    assert peak["Atenciones activas"] == adso + cyber  # Cuatro resultados por ficha, una sola atención.
    assert peak["Horas requeridas (h/sem)"] == 2 * (adso + cyber)
    assert peak["Contratistas requeridos"] == expected
    assert peak["Capacidad planta (h/sem)"] == (32 if plant_profile == PROFILE else 0)
    assert peak["Atenciones cubiertas por planta"] == (16 if plant_profile == PROFILE else 0)
    assert peak["Máximo fichas por contratista"] == 20
    for row in physical_rows(result, "monthly_instructors"):
        assert row["Horas asignadas"] <= row["Capacidad en horas"]
        assert row["Pico atenciones asignadas"] <= (16 if row["Vinculación"] == "Planta" else 20)
    # Las fechas de contratación y cada intervalo deben coincidir exactamente.
    for row in rows:
        active = [contract for contract in physical_rows(result, "contracts")
                  if contract["Inicio"] <= row["Inicio"] <= contract["Fin"]]
        assert len(active) == row["Contratistas requeridos"]


def test_existing_catalog_migrates_exclusive_profile_without_reupload_or_database_write(tmp_path):
    catalog = real_catalog(tmp_path)
    path = tmp_path / "real.sqlite3"
    for item in catalog["schedules"]:
        for row in item["activities"]:
            if row["competency"] == CODE:
                row.update(teaching_type="Técnico", classification_source="manual",
                           teaching_profile="Transversal general", profile_source="manual")
                row.pop("required_teaching_profile", None)
    with sqlite3.connect(path) as db:
        db.executemany("UPDATE virtual_schedules SET payload=? WHERE program_key=?",
                       [(json.dumps(item), item["program_key"]) for item in catalog["schedules"]])
    before = path.read_bytes()
    loaded = load_virtual_schedules(path)
    assert path.read_bytes() == before
    row, = [r for r in competency_rows(loaded) if r["Competencia"] == CODE]
    assert row["Perfil docente"] == PROFILE and row["Tipo"] == "Transversal"
    # Tampoco vuelve al perfil manual antiguo al reimportar uno de los programas.
    reimported = import_virtual_schedules(path, [("adso_fases.xlsx", (FIXTURES / "adso_fases.xlsx").read_bytes())])
    assert competency_rows(reimported) == competency_rows(loaded)
    # Un instructor que ya tenía el código de esta competencia conserva su especialidad.
    previous = {"virtual_inputs": {"plant": [person(kind="Transversal", profile=CODE)]}}
    assert virtual_schedule_templates(loaded, previous)[2][0]["Perfil"] == PROFILE


@pytest.mark.parametrize("field,value", [("Tipo", "Técnico"), ("Perfil docente", "Transversal general"), ("Perfil docente", "Bilingüismo")])
def test_editor_rejects_mixing_exclusive_profile_and_rolls_back(tmp_path, field, value):
    catalog = real_catalog(tmp_path)
    path = tmp_path / "real.sqlite3"
    before = path.read_bytes()
    choices = competency_rows(catalog)
    next(row for row in choices if row["Competencia"] == CODE)[field] = value
    with pytest.raises(ValueError, match="perfil exclusivo Cultura física"):
        save_choices(path, catalog, choices)
    assert path.read_bytes() == before


def test_separating_physical_profile_preserves_hours_technical_bilingual_and_intakes(tmp_path):
    catalog = real_catalog(tmp_path)
    old_catalog = deepcopy(catalog)
    for item in old_catalog["schedules"]:
        for row in item["activities"]:
            if row["competency"] == CODE:
                row["teaching_profile"] = "Transversal general"
    kwargs = dict(programs=program_rows(catalog), targets={"Técnico": 400, "Tecnólogo": 600},
                  rules=VirtualRules(), plant=[person(profile=catalog["schedules"][0]["program"])])
    _, old = plan(old_catalog, **kwargs)
    _, new = plan(catalog, **kwargs)
    assert old["center"] == new["center"]
    assert old["cohort_dates"] == new["cohort_dates"]
    assert old["offers_by_program"] == new["offers_by_program"]
    for key in ("staffing", "contracts", "activity_hours", "monthly_assignments", "monthly_instructors"):
        for keep in (lambda row: row["Tipo"] == "Técnico", lambda row: row["Perfil"] == "Bilingüismo"):
            assert [r for r in old[key] if keep(r)] == [r for r in new[key] if keep(r)]
    for key in ("monthly_fichas", "monthly"):
        assert sum(r["Horas requeridas"] for r in old[key]) == pytest.approx(sum(r["Horas requeridas"] for r in new[key]))
