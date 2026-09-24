"""Exportación de cronogramas, fases y carga docente sin jornadas."""
from io import BytesIO
import pandas as pd
from core.virtual_schedule import is_lective_activity


def export_virtual_schedule(instructors, plan):
    output = BytesIO()
    lective_only = plan.get("workload_scope") == "lectiva"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([{"Formación": "Titulada", "Modalidad": "Virtual", "Vigencia": plan["planning_year"],
                       "Alcance de horas": "Solo etapa lectiva" if lective_only else "Según ejecución anterior",
                       "Guardado (UTC)": plan["saved_at"], **plan["center"], **plan["summary"]}]).to_excel(writer, sheet_name="Resumen planeacion", index=False)
        pd.DataFrame([plan["rules"]]).to_excel(writer, sheet_name="Parametros", index=False)
        for key, sheet in [("programs", "Programas virtuales"), ("cohorts", "Fichas virtuales manuales"), ("plant", "Planta virtual manual")]:
            pd.DataFrame(plan["virtual_inputs"][key]).to_excel(writer, sheet_name=sheet, index=False)
        pd.DataFrame([{"Oferta": i + 1, "Inicio": value, "Porcentaje": plan["rules"]["intake_weights"][i]}
                      for i, value in enumerate(plan["virtual_inputs"]["offers"])]).to_excel(writer, sheet_name="Fechas de ofertas", index=False)
        for key, sheet in [("levels", "Metas por nivel"), ("distribution", "Distribucion"), ("offers_by_program", "Fichas por oferta"),
                           ("cohort_dates", "Fechas y fases de fichas"), ("periods", "Contratacion por fechas"), ("contracts", "Contratistas y fechas"),
                           ("monthly", "Resumen mensual"), ("staffing", "Cobertura por perfil"), ("activity_hours", "Trazabilidad horas")]:
            pd.DataFrame(plan[key]).to_excel(writer, sheet_name=sheet, index=False)
        catalog = plan["schedule_catalog"]["schedules"]
        pd.DataFrame([{"Programa": item["program"], **row,
                       "Incluida en planeación": not lective_only or is_lective_activity(row)}
                      for item in catalog for row in item["blocks"]]).to_excel(writer, sheet_name="Cronogramas y fases", index=False)
        pd.DataFrame([{"Programa": item["program"], **row,
                       "Incluida en planeación": not lective_only or is_lective_activity(row),
                       "Horas docentes por ficha para planeación": row["instructor_hours"] if not lective_only or is_lective_activity(row) else 0}
                      for item in catalog for row in item["activities"]]).to_excel(writer, sheet_name="Actividades y clasificacion", index=False)
        pd.DataFrame([{"Programa": item["program"], "Observación": warning} for item in catalog for warning in item["warnings"]]).to_excel(writer, sheet_name="Observaciones del origen", index=False)
        pd.DataFrame([{"Criterio": plan["calculation_basis"]}]).to_excel(writer, sheet_name="Criterio de calculo", index=False)
        instructors.to_excel(writer, sheet_name="Instructores planta", index=False)
    return output.getvalue()
