from copy import deepcopy
from io import BytesIO

import pandas as pd
import pytest

from core.complementary_export import export_complementary
from core.complementary_inputs import default_settings
from core.complementary_planner import execute_complementary_plan
from core.complementary_sources import source_availability
from core.complementary_store import load_complementary, save_complementary
from test_virtual_schedules import configured_catalog, plan, person
from test_virtual_technical_support import mixed_catalog


def settings(presencial=0, virtual=0, duration=40):
    return {m: {**default_settings(), "target_learners": target, "duration_hours": duration}
            for m, target in [("Presencial", presencial), ("Virtual", virtual)]}


def support(periods, *, modality="Virtual", identifier="Contrato 1", capacity=40):
    return {"metadata": {"Modalidad": modality, "Vigencia": 2027, "Estado": "Disponible"}, "plant_documents": [],
            "intervals": [{"Instructor ID": modality + " | " + identifier, "Instructor": identifier,
                "Modalidad de origen": modality, "Perfil": "Software", "Inicio": start, "Fin": end,
                "Capacidad (h/sem)": capacity, "Titulada (h/sem)": used, "Disponible (h/sem)": capacity - used}
                for start, end, used in periods]}


def assert_capacity(result):
    for row in result["instructor_intervals"]:
        assert row["Titulada (h/sem)"] + row["Reserva complementaria (h/sem)"] <= row["Capacidad (h/sem)"] + 1e-7
        assert row["Total programado (h/sem)"] <= row["Capacidad (h/sem)"] + 1e-7
    assert sum(r["Horas requeridas"] for r in result["monthly"]) == pytest.approx(result["summary"]["horas_requeridas"])
    assert sum(r["Duración (horas)"] for r in result["courses"]) == pytest.approx(result["summary"]["horas_requeridas"])
    assert len(result["courses"]) == len({row["Curso"] for row in result["courses"]}) == result["summary"]["cursos_necesarios"]


def test_same_support_capacity_is_shared_between_both_modalities_without_double_booking():
    source = support([("2027-01-01", "2027-01-14", 30)])
    result = execute_complementary_plan(settings(25, 25, duration=10), [source], 2027)
    assert result["summary"]["cursos_con_apoyo_titulada"] == 2
    assert result["summary"]["pico_contratistas_adicionales"] == 0
    assert len({r["Instructor ID"] for r in result["courses"]}) == 1
    assert [r["Inicio"] for r in result["courses"]] == ["2027-01-01", "2027-01-08"]
    assert_capacity(result)
    # Un tercer curso no puede tomar otra vez las mismas diez horas libres.
    expanded = execute_complementary_plan(settings(50, 25, duration=10), [source], 2027)
    assert expanded["summary"]["cursos_con_apoyo_titulada"] == 2
    assert expanded["summary"]["cursos_que_requieren_contratacion"] == 1
    assert expanded["summary"]["pico_contratistas_adicionales"] == 1
    assert_capacity(expanded)


def test_a_course_cannot_hide_a_busy_phase_with_average_monthly_availability():
    source = support([("2027-01-01", "2027-01-07", 30), ("2027-01-08", "2027-01-14", 40),
                      ("2027-01-15", "2027-01-21", 30)])
    result = execute_complementary_plan(settings(25, duration=20), [source], 2027)
    assert result["summary"]["cursos_con_apoyo_titulada"] == 0
    assert result["summary"]["pico_contratistas_adicionales"] == 1
    assert_capacity(result)


def test_support_does_not_extend_the_contract_to_finish_a_course():
    source = support([("2027-01-01", "2027-01-14", 0)])
    result = execute_complementary_plan(settings(25, duration=30), [source], 2027)
    assert result["summary"]["cursos_con_apoyo_titulada"] == 0
    assert all(row["Tipo de recurso"] == "Contratista adicional" for row in result["courses"])


def test_four_courses_share_one_additional_contractor_across_modalities():
    result = execute_complementary_plan(settings(50, 50, duration=520), [], 2027)
    assert result["summary"]["pico_contratistas_adicionales"] == 1
    assert result["summary"]["horas_requeridas"] == 2080
    assert len(result["contracts"]) == 1
    assert [r["Pico de contratistas adicionales"] for r in result["modalities"]] == [1, 1]
    assert result["contracts"][0]["Modalidades atendidas"] == "Presencial, Virtual"
    assert_capacity(result)


def test_courses_rotate_instead_of_hiring_one_instructor_for_every_four_annual_courses():
    result = execute_complementary_plan(settings(250, duration=40), [], 2027)
    assert result["summary"]["cursos_necesarios"] == 10
    assert result["summary"]["pico_contratistas_adicionales"] == 1
    assert result["summary"]["horas_requeridas"] == 400
    assert max(r["Fin"] for r in result["courses"]) < "2027-04-01"
    assert_capacity(result)


def test_own_plant_is_prioritized_and_never_copied_into_the_other_modality():
    inputs = settings(100, 25, duration=520)
    inputs["Presencial"]["plant"] = [{"Nombre completo": "Ana", "Cédula": "001"}]
    source = support([("2027-01-01", "2027-12-31", 30)])
    result = execute_complementary_plan(inputs, [source], 2027)
    assert result["summary"]["cursos_con_planta"] == 3
    assert result["summary"]["cursos_con_apoyo_titulada"] == 1
    assert result["summary"]["cursos_que_requieren_contratacion"] == 1
    assert all(r["Modalidad"] == "Presencial" for r in result["courses"] if r["Tipo de recurso"] == "Planta de Complementaria")
    own = [r for r in result["monthly_instructors"] if r["Tipo de recurso"] == "Planta de Complementaria"]
    assert len(own) == 12
    assert all(r["Total programado (h/mes)"] == pytest.approx(r["Capacidad (h/mes)"]) for r in own)
    assert_capacity(result)


def test_rounding_and_fractional_last_day_count_exact_course_hours():
    result = execute_complementary_plan(settings(51, duration=45.5), [], 2027)
    assert result["summary"]["cursos_necesarios"] == 3
    assert result["summary"]["horas_requeridas"] == 136.5
    assert result["modalities"][0]["Cupos proyectados"] == 75
    assert_capacity(result)


def test_virtual_source_counts_technical_support_and_excludes_titulada_plant(tmp_path):
    _, catalog = mixed_catalog(tmp_path)
    _, execution = plan(catalog, targets={"Técnico": 0, "Tecnólogo": 50})
    source = source_availability("Virtual", execution, 2027)
    assert {row["Disponible (h/sem)"] for row in source["intervals"]} == {10}
    assert execute_complementary_plan(settings(25, duration=10), [source], 2027)["summary"]["cursos_con_apoyo_titulada"] == 1
    _, execution = plan(catalog, plant=[person()])
    assert source_availability("Virtual", execution, 2027)["intervals"] == []


def test_previous_virtual_snapshots_are_reconstructed_without_changing_them(tmp_path):
    _, catalog = configured_catalog(tmp_path)
    _, execution = plan(catalog)
    current = source_availability("Virtual", execution, 2027)
    execution.pop("instructor_intervals")
    original = deepcopy(execution)
    legacy = source_availability("Virtual", execution, 2027)
    assert legacy["intervals"] == current["intervals"]
    assert original == execution
    assert source_availability("Virtual", execution, 2028)["intervals"] == []
    assert source_availability("Presencial", None, 2027)["intervals"] == []


def test_presencial_source_recovers_weekly_intensity_and_excludes_plant():
    execution = {"planning_year": 2027, "monthly_instructors": [
        {"Tipo": "Planta", "Capacidad (h/sem)": 32},
        {"Tipo": "Contratista proyectado", "Instructor ID": "Contrato Software 1", "Instructor": "Contrato 1",
         "Perfil": "Software", "Mes número": 2, "Capacidad (h/sem)": 40,
         "Capacidad (h/mes)": 160, "Horas asignadas (h/mes)": 120},
        {"Tipo": "Contratista proyectado", "Instructor ID": "Contrato Software 1", "Instructor": "Contrato 1",
         "Perfil": "Software", "Mes número": 3, "Capacidad (h/sem)": 40,
         "Capacidad (h/mes)": 160, "Horas asignadas (h/mes)": 160}]}
    source = source_availability("Presencial", execution, 2027)
    assert [(r["Inicio"], r["Fin"], r["Disponible (h/sem)"]) for r in source["intervals"]] == [
        ("2027-02-01", "2027-02-28", 10), ("2027-03-01", "2027-03-31", 0)]
    result = execute_complementary_plan(settings(25, 25, duration=40), [source], 2027)
    assert result["summary"]["cursos_con_apoyo_titulada"] == 1
    assert result["summary"]["cursos_que_requieren_contratacion"] == 1
    assert_capacity(result)


def test_valid_presencial_plan_without_instructors_provides_zero_capacity():
    source = source_availability("Presencial", {"planning_year": 2027, "monthly_instructors": []}, 2027)
    assert source["metadata"]["Estado"] == "Disponible"
    assert source["intervals"] == []
    result = execute_complementary_plan(settings(25), [source], 2027)
    assert result["summary"]["cursos_con_apoyo_titulada"] == 0
    assert result["summary"]["pico_contratistas_adicionales"] == 1


@pytest.mark.parametrize("change", ["negative", "fractional_meta", "zero_size", "no_duration", "long_course", "duplicate_plant", "titulada_plant"])
def test_invalid_inputs_never_silently_change_the_demand(change):
    inputs, sources = settings(25), []
    if change == "negative":
        inputs["Presencial"]["duration_hours"] = -1
    elif change == "fractional_meta":
        inputs["Presencial"]["target_learners"] = 1.5
    elif change == "zero_size":
        inputs["Presencial"]["learners_per_course"] = 0
    elif change == "no_duration":
        inputs["Presencial"]["duration_hours"] = None
    elif change == "long_course":
        inputs["Presencial"]["duration_hours"] = 1000
    else:
        row = {"Nombre completo": "Ana", "Cédula": "001"}
        inputs["Presencial"]["plant"] = [row]
        if change == "duplicate_plant":
            inputs["Virtual"]["plant"] = [row]
        else:
            sources = [{"metadata": {}, "intervals": [], "plant_documents": ["001"]}]
    with pytest.raises(ValueError):
        execute_complementary_plan(inputs, sources, 2027)


def test_duplicate_support_intervals_are_rejected():
    source = support([("2027-01-01", "2027-01-14", 30)] * 2)
    with pytest.raises(ValueError, match="duplicada"):
        execute_complementary_plan(settings(25), [source], 2027)


def test_joint_save_is_atomic_checks_revision_and_exports_coverage(tmp_path):
    path = tmp_path / "complementaria.sqlite3"
    execution = execute_complementary_plan(settings(51, 25, duration=40), [], 2027)
    saved = save_complementary(path, execution)
    assert saved["revision"] == 1
    with pytest.raises(ValueError, match="otra sesión"):
        save_complementary(path, execute_complementary_plan(settings(100), [], 2027), expected_revision=0)
    assert load_complementary(path) == saved
    book = pd.ExcelFile(BytesIO(export_complementary(saved)))
    assert len(book.parse("Cursos y fechas")) == 4
    assert book.parse("Resumen mensual")["Horas requeridas"].sum() == 160
    assert book.parse("Resumen conjunto")["pico_contratistas_adicionales"].iloc[0] == 1
