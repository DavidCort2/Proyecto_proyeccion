"""Entradas manuales virtuales adaptadas al motor curricular compartido."""
from collections import Counter
from hashlib import sha256
import json
import math

import pandas as pd

from core.curriculum import curriculum_key, curriculum_lookup, name_key
from core.curriculum_planner import execute_prepared_curriculum_plan
from core.ficha_projection import quarter_end_date

PROGRAM_COLUMNS = ["Programa", "Incluir", "Nivel", "Peso de oferta"]
COHORT_COLUMNS = ["Programa", "Fichas que pasan", "Trimestre al iniciar la vigencia"]
PLANT_COLUMNS = ["Área", "Perfil", "Instructores de planta"]
INSTRUCTOR_COLUMNS = ["Especialidad", "Área", "Nombre", "Documento", "Tipo Contrato", "Horas programadas actuales", "Es planta"]


def whole_number(value, label, minimum=0):
    try:
        number = float(value)
        if isinstance(value, bool) or not math.isfinite(number) or number < minimum or number % 1:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f"{label}: ingrese un entero mayor o igual a {minimum}.") from None
    return int(number)


def virtual_templates(catalog, previous):
    saved = previous.get("virtual_inputs", {})
    prior_programs = {name_key(row["Programa"]): row for row in saved.get("programs", [])}
    programs = []
    for item in catalog["curricula"]:
        prior = prior_programs.get(name_key(item["program"]), {})
        programs.append({"Programa": item["program"], "Incluir": prior.get("Incluir", True),
                         "Nivel": prior.get("Nivel"), "Peso de oferta": prior.get("Peso de oferta", 1)})
    prior_plant = {(row["Área"], name_key(row["Perfil"])): row["Instructores de planta"] for row in saved.get("plant", [])}
    profiles = [("Técnica", row["Programa"]) for row in programs] + [(area, area) for area in ("Bilingüismo", "Integralidad")]
    plant = [{"Área": area, "Perfil": profile, "Instructores de planta": prior_plant.get((area, name_key(profile)), 0)}
             for area, profile in profiles]
    cohort_frame = pd.DataFrame(saved.get("cohorts", []), columns=COHORT_COLUMNS)
    cohort_frame = cohort_frame.astype({column: "Int64" for column in COHORT_COLUMNS[1:]})
    return (pd.DataFrame(programs, columns=PROGRAM_COLUMNS), cohort_frame,
            pd.DataFrame(plant, columns=PLANT_COLUMNS))


def prepare_virtual_inputs(catalog, programs, cohorts, plant, year):
    year = whole_number(year, "Vigencia", 2000)
    if year > 2200:
        raise ValueError("La vigencia debe estar entre 2000 y 2200.")
    curricula = curriculum_lookup(catalog)
    if not curricula or any(item["schedule"] != "Virtual" for item in catalog["curricula"]):
        raise ValueError("Cargue las trimestralizaciones con el nombre PROGRAMA - VIRTUAL.xlsx.")
    selected, canonical_programs, seen_programs = {}, [], set()
    for row in programs:
        key = curriculum_key(row.get("Programa"), "Virtual")
        if key not in curricula:
            raise ValueError("Cada programa debe tener una trimestralización virtual guardada.")
        if key in seen_programs:
            raise ValueError("No repita programas en la oferta virtual.")
        seen_programs.add(key)
        if type(row.get("Incluir")) is not bool:
            raise ValueError("Indique qué programas incluir en la planeación.")
        canonical = {"Programa": curricula[key]["program"], "Incluir": row["Incluir"],
                     "Nivel": row.get("Nivel"), "Peso de oferta": whole_number(row.get("Peso de oferta"), "Peso de oferta", 1)}
        if row["Incluir"]:
            if row.get("Nivel") not in {"Técnico", "Tecnólogo"}:
                raise ValueError(f"Seleccione Técnico o Tecnólogo para {canonical['Programa']}.")
            selected[key] = canonical
        canonical_programs.append(canonical)
    if not selected:
        raise ValueError("Incluya al menos un programa virtual para planear.")
    details, canonical_cohorts, counts, endings = [], [], Counter(), Counter()
    for index, row in enumerate(cohorts, 1):
        key = curriculum_key(row.get("Programa"), "Virtual")
        if key not in selected:
            raise ValueError(f"Fichas que pasan, fila {index}: seleccione un programa incluido en la oferta.")
        count = whole_number(row.get("Fichas que pasan"), f"Fichas que pasan, fila {index}")
        age = whole_number(row.get("Trimestre al iniciar la vigencia"), f"Trimestre de formación, fila {index}", 1)
        item, program = curricula[key], selected[key]
        if age > item["duration"]:
            raise ValueError(f"{program['Programa']}: el trimestre inicial supera los {item['duration']} trimestres de la malla.")
        canonical_cohorts.append({"Programa": program["Programa"], "Fichas que pasan": count,
                                  "Trimestre al iniciar la vigencia": age})
        finish = year * 4 + item["duration"] - age
        ends = finish < (year + 1) * 4
        counts[key] += count
        endings[key] += count if ends else 0
        for number in range(1, count + 1):
            details.append({"Ficha": f"Virtual manual {index}.{number}", "Especialidad": program["Programa"],
                            "Nivel": program["Nivel"], "Jornada": "Virtual", "Jornada de planeación": "Virtual",
                            "Trimestre actual": age, "Trimestre al iniciar la vigencia": age,
                            "Duración (trimestres)": item["duration"], "Año fin estimado": finish // 4,
                            "Trimestre fin estimado": finish % 4 + 1, "Fecha fin estimada": quarter_end_date(finish),
                            "Pasa a la vigencia": True, "Termina en la vigencia": ends,
                            "Trimestres pendientes al iniciar la vigencia": item["duration"] - age + 1,
                            "Estado": "Pasa y termina durante la vigencia" if ends else "Pasa y continúa después de la vigencia",
                            "Archivo malla": item["source_name"]})
    canonical_plant, instructors, seen = [], [], set()
    for row in plant:
        area, profile = row.get("Área"), row.get("Perfil")
        if area == "Técnica":
            key = curriculum_key(profile, "Virtual")
            if key not in curricula:
                raise ValueError("El perfil de planta técnica debe corresponder a un programa virtual cargado.")
            profile = curricula[key]["program"]
        elif area in {"Bilingüismo", "Integralidad"}:
            profile = area
        else:
            raise ValueError("Área de planta no reconocida.")
        identity = (area, name_key(profile))
        if identity in seen:
            raise ValueError("No repita perfiles de planta; registre su cantidad en una sola fila.")
        seen.add(identity)
        count = whole_number(row.get("Instructores de planta"), "Instructores de planta")
        canonical_plant.append({"Área": area, "Perfil": profile, "Instructores de planta": count})
        for number in range(1, count + 1):
            instructors.append({"Especialidad": profile, "Área": area,
                                "Nombre": f"Cupo de planta virtual | {area} | {profile} | {number}", "Documento": "",
                                "Tipo Contrato": "Planta", "Horas programadas actuales": 0.0, "Es planta": True})
    inputs = {"programs": canonical_programs, "cohorts": canonical_cohorts, "plant": canonical_plant}
    digest = sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    staff = pd.DataFrame(instructors, columns=INSTRUCTOR_COLUMNS).astype({"Es planta": bool, "Horas programadas actuales": float})
    staff.attrs["specialties"] = [{"Especialidad": row["Programa"], "Área": "Técnica"} for row in selected.values()]
    imported = {"schema_version": 1, "input_mode": "virtual_manual", "source_name": "Fichas virtuales ingresadas manualmente",
                "source_digest": digest, "report_year": year, "report_quarter": 1, "planning_year": year,
                "rows": details, "detail": details, "summary": [], "profile_weights": []}
    for key, row in selected.items():
        profile = {"Especialidad": row["Programa"], "Nivel": row["Nivel"], "Jornada": "Virtual"}
        imported["summary"].append({**profile, "Fichas que pasan": counts[key], "Fichas que terminan": endings[key]})
        imported["profile_weights"].append({**profile, "Peso de oferta": row["Peso de oferta"]})
    return staff, imported, inputs, digest


def execute_virtual_plan(catalog, programs, cohorts, plant, rules, targets, year):
    errors = rules.validate_curricular()
    if errors:
        raise ValueError(" ".join(errors))
    staff, imported, inputs, digest = prepare_virtual_inputs(catalog, programs, cohorts, plant, year)
    plan = execute_prepared_curriculum_plan(staff, imported, catalog, rules, targets, year,
                                           "Planta virtual ingresada manualmente", digest)
    plan.update(input_mode="virtual_manual", planning_mode="virtual_curricula_v1", virtual_inputs=inputs,
                training_type="Titulada", modality="Virtual")
    plan["calculation_basis"] = (
        "La meta incluye las fichas que pasan y las nuevas. El saldo se divide por los aprendices por ficha, "
        "redondeando hacia arriba por nivel. Las fichas nuevas se reparten entre programas según sus pesos de oferta manuales "
        "y entre trimestres según los porcentajes configurados. Las horas provienen de la malla y la edad de cada ficha. "
        "Por perfil y período: máximo(horas requeridas − capacidad de planta, 0) / capacidad por contratista, "
        "redondeado hacia arriba. El pico es el máximo simultáneo de esos períodos."
    )
    plan["intake_basis"] = (
        "Las nuevas cubren únicamente el saldo de la meta después de descontar los aprendices que pasan. "
        "Se usa el mismo tamaño de ficha para ambos. Los pesos de oferta iniciales son 1: reparten por igual "
        "entre programas del mismo nivel. Puede editarlos. No se añade otro 5 % ni reposiciones fuera de la meta."
    )
    plan["offer_basis"] = (
        "Los pesos de oferta manuales determinan la participación de los programas de cada nivel. "
        "Los programas con menor peso reciben prioridad en las primeras ofertas, como en el cálculo presencial. "
        "Se conservan sus cuotas anuales y los porcentajes T1–T4, redondeados a fichas completas. "
        "Cada ingreso inicia en el trimestre 1 de su malla virtual."
    )
    for field in ("intake_allocation", "offers_by_program", "offers_by_profile"):
        for row in plan[field]:
            row["Peso de oferta"] = row.pop("Fichas del reporte")
    plan["duration_basis"] = (
        "Cada grupo manual indica el trimestre de formación que cursará al iniciar la vigencia. "
        "La malla virtual determina las horas pendientes y la fecha de terminación al final de su último trimestre. "
        "Los identificadores «Virtual manual» representan cantidades ingresadas, no códigos oficiales de ficha."
    )
    plan["plant_basis"] = "Los cupos de planta representan cantidades manuales por perfil, sin identificación personal."
    return staff, plan
