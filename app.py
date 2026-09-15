from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from core.config import PlanningRules
from core.excel_parser import parse_instructors_excel
from core.planner import (
    calculate_center_plan,
    plant_resource_summary,
    staffing_summary,
    suggested_ficha_distribution,
    technical_staffing_plan,
    transversal_staffing_plan,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EXCEL = BASE_DIR / "data" / "reporteInstructores_2026_4.xlsx"

st.set_page_config(
    page_title="Planeación Indicativa SENA · V2",
    page_icon="📊",
    layout="wide",
)

st.title("Planeación Indicativa · Centro de Formación SENA")
st.caption(
    "Versión 2 · Meta, fichas que continúan, capacidad de planta y proyección de contratistas por especialidad."
)

with st.sidebar:
    st.header("Reglas del escenario")
    learners_per_ficha = st.number_input(
        "Aprendices por ficha", min_value=1, value=25, step=1
    )
    weekly_hours_per_ficha = st.number_input(
        "Horas semanales por ficha", min_value=1.0, value=30.0, step=1.0
    )
    weekly_bilingual_hours = st.number_input(
        "Bilingüismo por ficha", min_value=0.0, value=6.0, step=1.0
    )
    weekly_integrality_hours = st.number_input(
        "Integralidad por ficha", min_value=0.0, value=6.0, step=1.0
    )
    weekly_plant_direct_hours = st.number_input(
        "Horas semanales instructor de planta",
        min_value=1.0,
        value=32.0,
        step=0.5,
        help="Capacidad directa semanal usada para el cálculo de planta.",
    )
    weekly_contractor_hours = st.number_input(
        "Horas semanales por contratista",
        min_value=1.0,
        value=40.0,
        step=1.0,
        help="Parámetro operativo de esta versión para proyectar la contratación requerida.",
    )

rules = PlanningRules(
    learners_per_ficha=int(learners_per_ficha),
    weekly_hours_per_ficha=float(weekly_hours_per_ficha),
    weekly_bilingual_hours=float(weekly_bilingual_hours),
    weekly_integrality_hours=float(weekly_integrality_hours),
    weekly_plant_direct_hours=float(weekly_plant_direct_hours),
    weekly_contractor_hours=float(weekly_contractor_hours),
)

validation_errors = rules.validate()
if validation_errors:
    for error in validation_errors:
        st.error(error)
    st.stop()

uploaded = st.file_uploader(
    "Reporte de instructores",
    type=["xlsx"],
    help="Si no carga un archivo, se utiliza el reporte incluido en el proyecto.",
)

try:
    instructors = parse_instructors_excel(uploaded if uploaded is not None else DEFAULT_EXCEL)
except Exception as exc:
    st.error(f"No fue posible leer el archivo de instructores: {exc}")
    st.stop()

plant_detected = int(instructors["Es planta"].sum())
contractors_detected = int((~instructors["Es planta"]).sum())
plant_capacity = plant_detected * rules.weekly_plant_direct_hours

st.subheader("1. Datos de la planeación")
input_col1, input_col2 = st.columns(2)
with input_col1:
    target_learners = st.number_input(
        "Meta proyectada de aprendices a matricular",
        min_value=0,
        value=500,
        step=25,
    )
with input_col2:
    continuing_fichas = st.number_input(
        "Fichas que pasan y continúan el siguiente año",
        min_value=0,
        value=0,
        step=1,
    )

plan = calculate_center_plan(
    int(target_learners),
    int(continuing_fichas),
    plant_detected,
    rules,
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Meta de aprendices", f"{plan['meta_aprendices']:,}".replace(",", "."))
m2.metric("Fichas nuevas", plan["fichas_nuevas"])
m3.metric("Fichas que pasan", plan["fichas_que_pasan"])
m4.metric("Total fichas activas", plan["fichas_activas"])

st.info(
    f"Cada ficha se modela con **{rules.weekly_hours_per_ficha:.0f} h/semana**: "
    f"**{rules.weekly_technical_hours:.0f} h técnicas + {rules.weekly_bilingual_hours:.0f} h de bilingüismo + "
    f"{rules.weekly_integrality_hours:.0f} h de integralidad**. "
    f"El reporte identifica **{plant_detected} instructores de planta**, equivalentes a "
    f"**{plant_capacity:.0f} h/semana** de capacidad base."
)

st.subheader("2. Distribución de fichas por especialidad")
st.caption(
    "El sistema propone una distribución inicial proporcional a la planta técnica disponible. "
    "Edite la tabla para reflejar la oferta real. Puede agregar una especialidad nueva; si no existe planta para ella, "
    "su capacidad de planta será cero."
)

suggested = suggested_ficha_distribution(
    instructors,
    int(plan["fichas_nuevas"]),
    int(plan["fichas_que_pasan"]),
)

editor_key = (
    f"distribution_{int(plan['fichas_nuevas'])}_{int(plan['fichas_que_pasan'])}_"
    f"{int(rules.weekly_technical_hours)}"
)

edited_distribution = st.data_editor(
    suggested,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Especialidad": st.column_config.TextColumn(required=True),
        "Fichas nuevas": st.column_config.NumberColumn(min_value=0, step=1, required=True),
        "Fichas que pasan": st.column_config.NumberColumn(min_value=0, step=1, required=True),
    },
    key=editor_key,
)

technical_plan = technical_staffing_plan(instructors, edited_distribution, rules)
assigned_new = int(technical_plan["Fichas nuevas"].sum()) if not technical_plan.empty else 0
assigned_continuing = int(technical_plan["Fichas que pasan"].sum()) if not technical_plan.empty else 0
expected_new = int(plan["fichas_nuevas"])
expected_continuing = int(plan["fichas_que_pasan"])
distribution_ok = assigned_new == expected_new and assigned_continuing == expected_continuing

v1, v2 = st.columns(2)
v1.metric(
    "Nuevas distribuidas",
    f"{assigned_new} / {expected_new}",
    delta=assigned_new - expected_new,
    delta_color="off",
)
v2.metric(
    "Continuaciones distribuidas",
    f"{assigned_continuing} / {expected_continuing}",
    delta=assigned_continuing - expected_continuing,
    delta_color="off",
)

if distribution_ok:
    st.success("La distribución coincide con los totales de la planeación.")
else:
    st.error(
        "La distribución todavía no coincide con los totales. Ajuste las columnas antes de tomar como definitivo "
        "el número de contratistas."
    )

transversal_plan = transversal_staffing_plan(
    instructors,
    int(plan["fichas_activas"]),
    rules,
)
summary = staffing_summary(technical_plan, transversal_plan, rules)

summary_tab, technical_tab, transversal_tab, instructors_tab, methodology_tab = st.tabs(
    [
        "Resumen de contratación",
        "Especialidades técnicas",
        "Bilingüismo e integralidad",
        "Planta detectada",
        "Metodología",
    ]
)

with summary_tab:
    st.markdown("### 3. Resultado de la planeación")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Instructores de planta", plant_detected)
    s2.metric("Déficit a cubrir", f"{summary['deficit_total_horas_semana']:.0f} h/sem")
    s3.metric("Contratistas técnicos", summary["contratistas_tecnicos"])
    s4.metric("Contratistas transversales", summary["contratistas_transversales"])

    if distribution_ok:
        st.metric(
            "TOTAL DE INSTRUCTORES DE CONTRATO REQUERIDOS",
            summary["contratistas_totales"],
            help=(
                "Suma de los contratistas requeridos por especialidad técnica, bilingüismo e integralidad. "
                "Cada déficit se redondea hacia arriba según la capacidad semanal del contratista."
            ),
        )
    else:
        st.warning(
            f"Cálculo provisional con la distribución actual: {summary['contratistas_totales']} contratistas. "
            "No se considera definitivo hasta cuadrar la distribución de fichas."
        )

    summary_rows = pd.DataFrame(
        [
            {
                "Componente": "Técnicos por especialidad",
                "Déficit (h/sem)": summary["deficit_tecnico_horas_semana"],
                "Contratistas requeridos": summary["contratistas_tecnicos"],
            },
            {
                "Componente": "Bilingüismo + Integralidad",
                "Déficit (h/sem)": summary["deficit_transversal_horas_semana"],
                "Contratistas requeridos": summary["contratistas_transversales"],
            },
            {
                "Componente": "TOTAL",
                "Déficit (h/sem)": summary["deficit_total_horas_semana"],
                "Contratistas requeridos": summary["contratistas_totales"],
            },
        ]
    )
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    st.caption(
        f"El archivo cargado contiene actualmente {contractors_detected} registros de contratistas. "
        "Ese número se muestra como referencia, pero no se descuenta del cálculo: la proyección determina primero "
        "la necesidad a partir de la planta disponible."
    )

with technical_tab:
    st.markdown("### Necesidad de contratación por especialidad técnica")
    st.dataframe(technical_plan, use_container_width=True, hide_index=True)

    if not technical_plan.empty:
        chart = technical_plan.set_index("Especialidad")[[
            "Capacidad planta (h/sem)",
            "Demanda técnica (h/sem)",
            "Capacidad contrato proyectada (h/sem)",
        ]]
        st.bar_chart(chart)

with transversal_tab:
    st.markdown("### Necesidad transversal")
    st.dataframe(transversal_plan, use_container_width=True, hide_index=True)
    if not transversal_plan.empty:
        st.bar_chart(
            transversal_plan.set_index("Área")[[
                "Capacidad planta (h/sem)",
                "Demanda (h/sem)",
                "Capacidad contrato proyectada (h/sem)",
            ]]
        )

with instructors_tab:
    st.markdown("### Capacidad de los instructores de planta del reporte")
    resources = plant_resource_summary(instructors, rules)
    st.dataframe(resources, use_container_width=True, hide_index=True)

    detail = instructors.loc[instructors["Es planta"]].copy()
    detail["Capacidad base (h/sem)"] = rules.weekly_plant_direct_hours
    st.dataframe(
        detail[
            [
                "Área",
                "Especialidad",
                "Nombre",
                "Horas programadas actuales",
                "Capacidad base (h/sem)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

with methodology_tab:
    st.markdown(
        f"""
### Lógica usada en esta versión

1. **Fichas nuevas** = redondeo hacia arriba de `meta / {rules.learners_per_ficha}`.
2. **Fichas activas** = fichas nuevas + fichas que pasan.
3. Cada ficha demanda **{rules.weekly_hours_per_ficha:.0f} h/semana**.
4. De esas horas, **{rules.weekly_bilingual_hours:.0f} h** corresponden a bilingüismo y **{rules.weekly_integrality_hours:.0f} h** a integralidad.
5. La demanda técnica resultante es **{rules.weekly_technical_hours:.0f} h por ficha**.
6. Cada instructor de planta aporta **{rules.weekly_plant_direct_hours:.0f} h/semana** de capacidad para el modelo.
7. Para cada especialidad se calcula:  
   `déficit = max(demanda - capacidad de planta, 0)`
8. Cada contratista aporta **{rules.weekly_contractor_hours:.0f} h/semana**. Por tanto:  
   `contratistas = redondeo hacia arriba(déficit / {rules.weekly_contractor_hours:.0f})`
9. El redondeo se realiza por especialidad para evitar compensar déficits entre perfiles que no son intercambiables.

**Importante:** las fichas nuevas y las que continúan se distribuyen de forma inicial según la planta técnica detectada, pero la tabla es editable porque la oferta real del Centro es la fuente correcta para asignar las fichas por especialidad.
"""
    )

# Exportación consolidada
output = BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    pd.DataFrame([plan]).to_excel(writer, sheet_name="Resumen planeacion", index=False)
    technical_plan.to_excel(writer, sheet_name="Tecnicos", index=False)
    transversal_plan.to_excel(writer, sheet_name="Transversales", index=False)
    plant_resource_summary(instructors, rules).to_excel(writer, sheet_name="Planta", index=False)
output.seek(0)

st.divider()
st.download_button(
    "Descargar resultado de la planeación en Excel",
    data=output.getvalue(),
    file_name="planeacion_indicativa_v2.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
