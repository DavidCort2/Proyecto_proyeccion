"""La carga diaria y el apoyo comparten una única capacidad por instructor."""
from collections import defaultdict
from copy import deepcopy
from io import BytesIO

from openpyxl import load_workbook
import pytest

from core.database import load_planning, save_planning
from core.export import export_planning
from core.virtual_schedule_planner import VirtualRules
from test_virtual_schedules import configured_catalog, person, plan, real_catalog


def mixed_catalog(tmp_path, transversal_profile="Transversal general", technical_days=7, transversal_days=7):
    path, catalog = configured_catalog(tmp_path, durations=(technical_days,))
    item = catalog["schedules"][0]
    transversal = deepcopy(item["activities"][0])
    transversal.update(id="transversal", competency="123456789", teaching_type="Transversal",
                       teaching_profile=transversal_profile, duration=transversal_days)
    item["activities"].append(transversal)
    item["lective_duration"] = max(technical_days, transversal_days)
    return path, catalog


def high(result, kind, profile=None):
    return max((r for r in result["staffing"] if r["Tipo"] == kind and (profile is None or r["Perfil"] == profile)),
               key=lambda r: r["Fichas activas"])


def assert_single_capacity(result):
    rows = result["monthly_instructors"]
    assert len(rows) == len({(row["Mes"], row["Instructor"]) for row in rows})
    for row in rows:
        assert row["Horas asignadas"] <= row["Capacidad en horas"] + 1e-8
        assert row["Horas asignadas"] == pytest.approx(row["Horas técnicas asignadas"] + row["Horas transversales asignadas"])
        assigned = [a for a in result["monthly_assignments"] if a["Mes"] == row["Mes"] and a["Instructor"] == row["Instructor"]]
        assert sum(a["Horas asignadas"] for a in assigned) == pytest.approx(row["Horas asignadas"])
    for month in result["monthly"]:
        assert month["Horas requeridas"] == pytest.approx(sum(r["Horas asignadas"] for r in rows if r["Mes"] == month["Mes"]))
        assert month["Horas cubiertas por planta"] == pytest.approx(sum(r["Horas asignadas"] for r in rows if r["Mes"] == month["Mes"] and r["Vinculación"] == "Planta"))
        assert month["Horas a contratar"] == pytest.approx(sum(r["Horas asignadas"] for r in rows if r["Mes"] == month["Mes"] and r["Vinculación"] == "Contratista"))
    for row in result["technical_support"]:
        assert row["Horas técnicas (h/sem)"] + row["Apoyo transversal (h/sem)"] <= row["Capacidad (h/sem)"]
        assert row["Perfil apoyado"] == "Transversal general"


@pytest.mark.parametrize("fichas,tech,helped,general", [
    (1, 1, 1, 0), (2, 1, 2, 0), (3, 1, 2, 1), (4, 1, 0, 1),
    (5, 2, 5, 0), (6, 2, 4, 1), (7, 2, 2, 1), (8, 2, 0, 1), (9, 3, 6, 1),
])
def test_technical_contractors_use_only_their_actual_spare_capacity(tmp_path, fichas, tech, helped, general):
    _, catalog = mixed_catalog(tmp_path)
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": fichas * 25})
    technical = high(result, "Técnico")
    transversal = high(result, "Transversal")
    assert technical["Contratistas requeridos"] == tech
    assert transversal["Contratistas requeridos"] == general
    assert transversal["Atenciones cubiertas por apoyo técnico"] == helped
    assert transversal["Apoyo técnico contratado (h/sem)"] == helped * 5
    assert transversal["Horas de contratistas propios del perfil"] == (fichas - helped) * 5
    assert result["center"]["demanda_total_horas_anuales"] == fichas * 15
    assert result["summary"]["pico_contratistas_total"] == tech + general
    assert_single_capacity(result)


@pytest.mark.parametrize("fichas,helped,technical_contracts,general_contracts", [
    (1, 1, 0, 0), (2, 2, 0, 0), (3, 0, 0, 1), (4, 4, 1, 0), (5, 4, 1, 1),
])
def test_technical_plant_support_is_counted_once_and_respects_whole_daily_attention(tmp_path, fichas, helped, technical_contracts, general_contracts):
    _, catalog = mixed_catalog(tmp_path)
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": fichas * 25}, plant=[person()])
    transversal = high(result, "Transversal")
    assert transversal["Atenciones cubiertas por apoyo técnico"] == helped
    assert high(result, "Técnico")["Contratistas requeridos"] == technical_contracts
    assert transversal["Contratistas requeridos"] == general_contracts
    assert_single_capacity(result)
    if fichas == 3:
        instructor = next(r for r in result["monthly_instructors"] if r["Vinculación"] == "Planta" and r["Mes"] == 1)
        assert instructor["Horas técnicas asignadas"] == 30
        assert instructor["Horas transversales asignadas"] == 0  # Sus 2 h restantes no cubren 1 h cada día.


@pytest.mark.parametrize("profile", ["Bilingüismo", "Cultura física", "Otro perfil especializado"])
def test_technical_spare_hours_never_cover_exclusive_or_unapproved_profiles(tmp_path, profile):
    _, catalog = mixed_catalog(tmp_path, transversal_profile=profile)
    _, result = plan(catalog, plant=[person()])
    assert high(result, "Transversal")["Contratistas requeridos"] == 1
    assert result["technical_support"] == []
    assert high(result, "Transversal")["Horas requeridas (h/sem)"] == 5
    assert_single_capacity(result)


def test_support_stops_when_technical_contract_stops_even_though_general_continues(tmp_path):
    _, catalog = mixed_catalog(tmp_path, transversal_days=21)
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 125})
    assert [(r["Inicio"], r["Fin"]) for r in result["contracts"] if r["Tipo"] == "Técnico"] == [("2027-01-01", "2027-01-07")] * 2
    assert [(r["Inicio"], r["Fin"]) for r in result["contracts"] if r["Tipo"] == "Transversal"] == [("2027-01-08", "2027-01-21")]
    assert {r["Fin"] for r in result["technical_support"]} == {"2027-01-07"}
    assert_single_capacity(result)


def test_own_transversal_plant_has_priority_over_technical_support(tmp_path):
    _, catalog = mixed_catalog(tmp_path)
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 50},
                     plant=[person(), person("456", "Transversal", "Transversal general")])
    assert result["summary"]["pico_contratistas_total"] == 0
    assert result["technical_support"] == []
    assert high(result, "Transversal")["Horas cubiertas por planta"] == 10
    assert_single_capacity(result)


def test_idle_technical_plant_can_help_without_creating_a_technical_contract(tmp_path):
    _, catalog = mixed_catalog(tmp_path)
    catalog["schedules"][0]["activities"] = catalog["schedules"][0]["activities"][1:]
    _, result = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 150}, plant=[person()])
    assert result["contracts"] == []
    assert high(result, "Transversal")["Apoyo técnico de planta (h/sem)"] == 30
    assert result["center"]["demanda_total_horas_anuales"] == 30
    assert_single_capacity(result)


def test_support_is_visible_in_assignments_capacity_and_excel(tmp_path):
    path, catalog = mixed_catalog(tmp_path)
    staff, result = plan(catalog, plant=[person()], targets={"Técnico": 0, "Tecnólogo": 50})
    support = [row for row in result["monthly_assignments"] if row["Apoyo técnico"]]
    assert len(support) == 2
    assert all(r["Tipo del instructor"] == "Técnico" and r["Tipo"] == "Transversal" for r in support)
    assert sum(r["Horas asignadas"] for r in support) == 10
    save_planning(path, staff, result)
    book = load_workbook(BytesIO(export_planning(*load_planning(path))), read_only=True)
    assert book["Apoyo tecnico transversal"].max_row == 2
    book.close()
    assert_single_capacity(result)


def test_real_schedules_keep_dates_technical_load_and_daily_capacity_with_support(tmp_path):
    catalog = real_catalog(tmp_path)
    _, result = plan(catalog, targets={"Técnico": 500, "Tecnólogo": 700}, rules=VirtualRules(),
                     programs=[{"Programa": item["program"], "Incluir": True, "Nivel": level, "Peso de oferta": 1}
                               for item, level in zip(catalog["schedules"], ["Tecnólogo", "Técnico"])],
                     plant=[person(profile=catalog["schedules"][0]["program"])])
    assert result["technical_support"]
    assert_single_capacity(result)
    for interval in result["periods"]:
        # Recalcular por persona a partir de todas las tareas activas, sin reunir capacidad entre personas.
        support = [r for r in result["technical_support"] if r["Inicio"] == interval["Inicio"]]
        assert all((r["Horas técnicas (h/sem)"] + r["Apoyo transversal (h/sem)"]) / 5 <= r["Capacidad (h/sem)"] / 5 for r in support)
    monthly = defaultdict(float)
    for row in result["monthly_assignments"]:
        monthly[row["Mes"], row["Ficha proyectada"]] += row["Horas asignadas"]
    for row in result["monthly_fichas"]:
        assert row["Horas requeridas"] == pytest.approx(monthly[row["Mes"], row["Ficha proyectada"]])
