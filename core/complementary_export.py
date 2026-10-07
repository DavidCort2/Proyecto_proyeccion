"""Exporta el escenario guardado de las dos modalidades y su capacidad compartida."""
from io import BytesIO
import pandas as pd


def export_complementary(plan):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([{"Vigencia": plan["planning_year"], "Guardado": plan["saved_at"], **plan["summary"]}]).to_excel(
            writer, sheet_name="Resumen conjunto", index=False)
        for key, sheet in [("modalities", "Metas y cobertura"), ("courses", "Cursos y fechas"),
                           ("monthly", "Resumen mensual"), ("contracts", "Contratacion adicional"),
                           ("monthly_instructors", "Carga de instructores"), ("instructor_intervals", "Control de capacidad"),
                           ("sources", "Fuentes de Titulada"), ("source_availability", "Disponibilidad de Titulada")]:
            pd.DataFrame(plan[key]).to_excel(writer, sheet_name=sheet, index=False)
        pd.DataFrame([{"Modalidad": mode, **person} for mode, settings in plan["inputs"].items()
                      for person in settings["plant"]]).to_excel(writer, sheet_name="Planta de Complementaria", index=False)
        pd.DataFrame([plan["rules"]]).to_excel(writer, sheet_name="Parametros de capacidad", index=False)
        pd.DataFrame([{"Criterio": plan["calculation_basis"]}]).to_excel(writer, sheet_name="Criterio de calculo", index=False)
    return output.getvalue()
