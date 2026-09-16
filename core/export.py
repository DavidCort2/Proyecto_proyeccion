from io import BytesIO

import pandas as pd

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
        pd.DataFrame([metadata]).to_excel(writer, sheet_name="Resumen planeacion", index=False)
        pd.DataFrame([execution["rules"]]).to_excel(writer, sheet_name="Reglas", index=False)
        pd.DataFrame(execution["distribution"]).to_excel(writer, sheet_name="Distribucion", index=False)
        if "levels" in execution:
            pd.DataFrame(execution["levels"]).to_excel(writer, sheet_name="Metas por nivel", index=False)
            pd.DataFrame(execution["hours"]).to_excel(writer, sheet_name="Horas por nivel y jornada", index=False)
        if "calendar" in execution:
            for key, sheet in [("calendar", "Calendario de fichas"), ("quarterly", "Resumen trimestral"),
                               ("quarter_endings", "Terminaciones por trimestre"),
                               ("technical_quarterly", "Planta tecnica por trimestre"),
                               ("transversal_quarterly", "Transversales por trimestre")]:
                pd.DataFrame(execution[key]).to_excel(writer, sheet_name=sheet, index=False)
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
