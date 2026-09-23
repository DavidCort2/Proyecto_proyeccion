from io import BytesIO

import pandas as pd

from core.contracting_periods import contracting_headline, individual_contract_periods

def export_planning(instructors: pd.DataFrame, execution: dict) -> bytes:
    """Exporta únicamente la instantánea ejecutada y guardada."""
    output = BytesIO()
    metadata = {
        "Vigencia": execution["planning_year"],
        "Archivo": execution["source_name"],
        "Guardado (UTC)": execution["saved_at"],
        **execution["center"],
        **execution["summary"],
    }
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if "contract_windows" in execution:
            pd.DataFrame([contracting_headline(execution)]).to_excel(writer, sheet_name="Contratacion requerida", index=False)
            pd.DataFrame(individual_contract_periods(execution), columns=[
                "Instructor proyectado", "Tipo", "Perfil", "Requerido desde", "Requerido hasta", "Meses",
                "Capacidad (h/sem)", "Instructor ID"]).to_excel(writer, sheet_name="Contratistas y fechas", index=False)
        pd.DataFrame([metadata]).to_excel(writer, sheet_name="Resumen planeacion", index=False)
        pd.DataFrame([execution["rules"]]).to_excel(writer, sheet_name="Reglas", index=False)
        pd.DataFrame(execution["distribution"]).to_excel(writer, sheet_name="Distribucion", index=False)
        if execution.get("target_basis"):
            pd.DataFrame(execution["intake_allocation"]).to_excel(writer, sheet_name="Asignacion de fichas nuevas", index=False)
            pd.DataFrame([{"Criterio de meta y oferta": execution["intake_basis"]}]).to_excel(writer, sheet_name="Criterio de la meta", index=False)
        if "levels" in execution:
            pd.DataFrame(execution["levels"]).to_excel(writer, sheet_name="Metas por nivel", index=False)
            pd.DataFrame(execution["hours"]).to_excel(writer, sheet_name="Horas por nivel y jornada", index=False)
        if "calendar" in execution:
            for key, sheet in [("calendar", "Calendario de fichas"), ("quarterly", "Resumen trimestral"),
                               ("quarter_endings", "Terminaciones por trimestre"),
                               ("technical_quarterly", "Planta tecnica por trimestre"),
                               ("transversal_quarterly", "Transversales por trimestre")]:
                pd.DataFrame(execution[key]).to_excel(writer, sheet_name=sheet, index=False)
        for key, sheet in [("transversal_current", "Capacidad transversal actual"),
                           ("transversal_continuity", "Continuidad transversal"),
                           ("transversal_modules", "Modulos transversales"),
                           ("continuing_transversal_hours", "Horas pendientes transversales")]:
            if key in execution:
                pd.DataFrame(execution[key]).to_excel(writer, sheet_name=sheet, index=False)
        pd.DataFrame([{"Modelo transversal": execution.get("transversal_demand_model", "weekly")}]).to_excel(writer, sheet_name="Modelo de demanda", index=False)
        if "monthly" in execution:
            for key, sheet in [("monthly", "Resumen mensual"), ("monthly_fichas", "Horas mensuales por ficha"),
                               ("monthly_staffing", "Dotacion mensual por perfil"), ("monthly_instructors", "Capacidad mensual instructores"),
                               ("monthly_assignments", "Asignacion mensual de horas")]:
                pd.DataFrame(execution[key]).to_excel(writer, sheet_name=sheet, index=False)
            pd.DataFrame([{"Distribución mensual": execution["monthly_basis"],
                           "Base de contratación": execution.get("contracting_basis", execution.get("continuity_assumption", ""))}]).to_excel(writer, sheet_name="Supuestos mensuales", index=False)
        if "contract_windows" in execution:
            for key, sheet in [("contract_windows", "Periodos de contratacion"),
                               ("contracting_quarterly", "Contratacion por trimestre"),
                               ("contracting_profiles", "Picos por perfil"),
                               ("contracting_profile_quarterly", "Excesos y reducciones")]:
                pd.DataFrame(execution[key]).to_excel(writer, sheet_name=sheet, index=False)
            pd.DataFrame([{"Criterio de períodos": execution["contracting_periods_basis"]}]).to_excel(writer, sheet_name="Criterio de contratacion", index=False)
        if execution.get("curriculum_catalog"):
            catalog = execution["curriculum_catalog"]
            pd.DataFrame([{key: value for key, value in item.items() if key != "outcomes"}
                          for item in catalog["curricula"]]).to_excel(writer, sheet_name="Mallas curriculares", index=False)
            pd.DataFrame(catalog["competencies"]).to_excel(writer, sheet_name="Competencias", index=False)
            pd.DataFrame([{"Programa": item["program"], "Jornada": item["schedule"], **row}
                          for item in catalog["curricula"] for row in item["outcomes"]]).to_excel(writer, sheet_name="Resultados curriculares", index=False)
            pd.DataFrame(execution["curriculum_hours"]).to_excel(writer, sheet_name="Trazabilidad horas", index=False)
        if execution.get("ficha_import"):
            imported = execution["ficha_import"]
            pd.DataFrame([{
                "Archivo": imported["source_name"], "Año reporte": imported["report_year"],
                "Trimestre reporte": imported["report_quarter"], "Vigencia": imported["planning_year"],
            }]).to_excel(writer, sheet_name="Origen fichas", index=False)
            pd.DataFrame(imported["detail"]).to_excel(writer, sheet_name="Detalle fichas importadas", index=False)
            pd.DataFrame(imported["summary"]).to_excel(writer, sheet_name="Continuaciones calculadas", index=False)
        if "growth_rule" in execution:
            pd.DataFrame(execution["growth_rule"]["rows"]).to_excel(writer, sheet_name="Regla reposicion y crecimiento", index=False)
        if "growth_guide" in execution:
            pd.DataFrame(execution["growth_guide"]["rows"]).to_excel(writer, sheet_name="Guia reposicion y crecimiento", index=False)
        pd.DataFrame(execution["technical"]).to_excel(writer, sheet_name="Tecnicos", index=False)
        pd.DataFrame(execution["transversal"]).to_excel(writer, sheet_name="Transversales", index=False)
        pd.DataFrame(execution["resources"]).to_excel(writer, sheet_name="Capacidad planta", index=False)
        instructors.loc[instructors["Es planta"]].to_excel(writer, sheet_name="Instructores planta", index=False)
        pd.DataFrame(instructors.attrs.get("specialties", [])).to_excel(writer, sheet_name="Especialidades", index=False)
    return output.getvalue()
