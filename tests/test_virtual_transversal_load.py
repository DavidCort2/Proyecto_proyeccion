from copy import deepcopy

import pytest

from core.virtual_schedule_planner import VirtualRules
from core.virtual_competencies import competency_rows
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules
from test_virtual_schedules import configured_catalog, person, plan, real_catalog, save_choices, schedule_bytes


@pytest.mark.parametrize("code", ["111111111", "987654321"])
@pytest.mark.parametrize("fichas,plants,contracts", [(10, 0, 1), (20, 0, 1), (21, 0, 2), (16, 1, 0), (17, 1, 1), (36, 1, 1)])
def test_weekly_load_uses_active_fichas_and_capacity_for_any_competency(tmp_path, code, fichas, plants, contracts):
    _, catalog = configured_catalog(tmp_path, durations=(7,))
    activity = catalog["schedules"][0]["activities"][0]
    activity.update(competency=code, teaching_type="Transversal")
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": fichas * 25},
                     plant=[person(kind="Transversal", profile=code)] if plants else [])
    active = next(r for r in result["staffing"] if r["Fichas activas"])
    assert active["Horas requeridas (h/sem)"] == fichas * 2
    assert active["Contratistas requeridos"] == contracts
    assert active["Máximo fichas por contratista"] == 20  # Sale de 40/2; no depende del código.
    assert active["Máximo fichas por planta"] == 16
    assert result["center"]["demanda_total_horas_anuales"] == fichas * 2
    for row in result["monthly_instructors"]:
        assert row["Horas asignadas"] <= row["Capacidad en horas"]
        if row["Vinculación"] == "Contratista":
            assert row["Pico fichas asignadas"] <= 20


def test_capacity_is_derived_not_fixed_to_twenty(tmp_path):
    _, catalog = configured_catalog(tmp_path, durations=(7,))
    catalog["schedules"][0]["activities"][0].update(competency="111111111", teaching_type="Transversal")
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 11 * 25},
                     rules=VirtualRules(weekly_transversal_hours_per_ficha=4, intake_weights=(100, 0, 0, 0)))
    assert result["summary"]["pico_contratistas_total"] == 2
    active = next(r for r in result["staffing"] if r["Fichas activas"])
    assert active["Máximo fichas por contratista"] == 10
    assert active["Horas requeridas (h/sem)"] == 44


def test_transversal_stops_at_its_block_and_duplicate_results_do_not_add_hours(tmp_path):
    _, catalog = configured_catalog(tmp_path)
    item = catalog["schedules"][0]
    activity = next(a for a in item["activities"] if a["teaching_type"] == "Transversal")
    activity["competency"] = "111111111"
    duplicate = deepcopy(activity)
    duplicate.update(id="otra-actividad", activity="Otro resultado de la misma competencia")
    item["activities"].append(duplicate)
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 10 * 25})
    rows = [r for r in result["staffing"] if r["Tipo"] == "Transversal" and r["Fichas activas"]]
    assert [(r["Inicio"], r["Fin"]) for r in rows] == [("2027-01-08", "2027-01-14")]
    assert sum(r["Horas requeridas"] for r in rows) == 20
    assert sum(r["Horas transversales"] for r in result["monthly_fichas"]) == 20
    assert [(r["Inicio"], r["Fin"]) for r in result["contracts"] if r["Tipo"] == "Transversal"] == [("2027-01-08", "2027-01-14")]


def test_real_schedules_technical_results_do_not_change_when_transversal_rate_changes(tmp_path):
    catalog = real_catalog(tmp_path)
    programs = [{"Programa": i["program"], "Incluir": True, "Nivel": "Tecnólogo", "Peso de oferta": 1} for i in catalog["schedules"]]
    arguments = dict(programs=programs, targets={"Técnico": 0, "Tecnólogo": 1000},
                     plant=[person(profile=catalog["schedules"][0]["program"])])
    _, old = plan(catalog, **arguments, rules=VirtualRules(weekly_transversal_hours_per_ficha=10))
    _, new = plan(catalog, **arguments, rules=VirtualRules())
    for key in ("staffing", "activity_hours", "contracts", "monthly_instructors", "monthly_assignments"):
        assert [row for row in old[key] if row["Tipo"] == "Técnico"] == [row for row in new[key] if row["Tipo"] == "Técnico"]
    assert old["cohort_dates"] == new["cohort_dates"]
    assert old["offers_by_program"] == new["offers_by_program"]
    old_months = {(r["Mes"], r["Ficha proyectada"]): r for r in old["monthly_fichas"]}
    new_months = {(r["Mes"], r["Ficha proyectada"]): r for r in new["monthly_fichas"]}
    assert old_months.keys() == new_months.keys()
    for key, old_month in old_months.items():
        new_month = new_months[key]
        assert old_month["Horas técnicas"] == new_month["Horas técnicas"]
        assert new_month["Horas transversales"] == pytest.approx(old_month["Horas transversales"] / 5)


def test_shared_profile_adds_distinct_competencies_but_not_repeated_results(tmp_path):
    _, catalog = configured_catalog(tmp_path, durations=(7,))
    item = catalog["schedules"][0]
    first = item["activities"][0]
    first.update(competency="111111111", teaching_type="Transversal", teaching_profile="Perfil compartido")
    second = deepcopy(first)
    second.update(id="segunda", competency="222222222")
    duplicate = deepcopy(first)
    duplicate.update(id="otra-evidencia", activity="Otro resultado de la misma competencia")
    item["activities"].extend([second, duplicate])
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 10 * 25})
    active = next(row for row in result["staffing"] if row["Fichas activas"])
    assert active["Fichas activas"] == 10
    assert active["Atenciones activas"] == 20
    assert active["Horas requeridas (h/sem)"] == 40
    assert active["Contratistas requeridos"] == 1
    assert sum(row["Horas requeridas"] for row in result["monthly_fichas"]) == 40
    instructor = next(row for row in result["monthly_instructors"] if row["Horas asignadas"])
    assert instructor["Pico fichas asignadas"] == 10
    assert instructor["Pico atenciones asignadas"] == 20
    assert all(row["Horas asignadas"] == 4 for row in result["monthly_assignments"])
    assert all(row["Competencias"] == "111111111, 222222222" for row in result["monthly_assignments"])
    _, with_plant = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 10 * 25},
                         plant=[person(kind="Transversal", profile="Perfil compartido")])
    covered = next(row for row in with_plant["staffing"] if row["Fichas activas"])
    assert covered["Atenciones cubiertas por planta"] == 16
    assert covered["Fichas cubiertas por planta"] == 8
    assert covered["Horas cubiertas por planta"] == 32
    assert covered["Horas a contratar"] == 8


def test_profile_policy_keeps_bilingualism_separate_using_authoritative_identity(tmp_path):
    catalog = real_catalog(tmp_path)
    rows = {row["Competencia"]: row for row in competency_rows(catalog) if row["Tipo"] == "Transversal"}
    assert rows["240202501"]["Perfil docente"] == "Bilingüismo"
    assert {row["Perfil docente"] for code, row in rows.items() if code != "240202501"} == {"Transversal general"}
    assert all(row["profile_reference"].startswith("https://normograma.sena.edu.co/")
               for item in catalog["schedules"] for row in item["activities"] if row["competency"] == "240202501")


def test_manual_profile_is_global_persistent_and_reimportable(tmp_path):
    path, catalog = configured_catalog(tmp_path)
    catalog = import_virtual_schedules(path, [("Redes.xlsx", schedule_bytes(program="Redes"))])
    choices = competency_rows(catalog)
    for row in choices:
        if row["Tipo"] == "Transversal":
            row["Perfil docente"] = "Perfil revisado por el centro"
    save_choices(path, catalog, choices)
    catalog = import_virtual_schedules(path, [("Redes.xlsx", schedule_bytes(program="Redes", durations=(14, 7, 7)))])
    assert {row["Perfil docente"] for row in competency_rows(catalog) if row["Tipo"] == "Transversal"} == {"Perfil revisado por el centro"}
    assert load_virtual_schedules(path) == catalog
