from io import BytesIO

import pandas as pd

from core.workflow import DISTRIBUTION_COLUMNS


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
        pd.DataFrame(execution["distribution"], columns=DISTRIBUTION_COLUMNS).to_excel(writer, sheet_name="Distribucion", index=False)
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
