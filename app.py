from __future__ import annotations

from dataclasses import asdict
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.excel_parser import parse_instructors_excel
from core.planner import (
    fichas_from_target, growth_requirements,
    technical_specialty_catalog,
)
from core.workflow import MANUAL_COLUMNS, execute_plan, project_distribution
from ui.results import render_results

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EXCEL = BASE_DIR / "reporteInstructores_2026_4.xlsx"
if not DEFAULT_EXCEL.exists():
    DEFAULT_EXCEL = BASE_DIR / "data" / "reporteInstructores_2026_4.xlsx"
DATABASE_PATH = BASE_DIR / "data" / "planeacion.sqlite3"


@st.cache_data(show_spinner=False, max_entries=4)
def read_report(content: bytes) -> pd.DataFrame:
    return parse_instructors_excel(BytesIO(content))


def main() -> None:
    st.set_page_config(page_title="Planeación Indicativa SENA", page_icon="📊", layout="wide")
    st.title("Planeación Indicativa")
    st.caption("Centro de Formación SENA · Prepare los datos, distribuya las fichas y ejecute la planeación de la próxima vigencia.")
    try:
        saved = load_planning(DATABASE_PATH)
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"No fue posible abrir la base de datos: {exc}")
        st.stop()
    previous = saved[1] if saved else {}
    defaults = previous.get("rules", asdict(PlanningRules()))
    instructors = None
    source_name = source_digest = ""
    draft_valid = False
    continuing = 0
    # La meta ingresada se conserva; la proyección puede superarla.
    st.session_state.pop("suggested_target", None)

    with st.container(border=True):
        st.subheader("1. Preparar la planeación")
        st.caption("Todos los datos se ingresan aquí. Al ejecutar se reemplazan la carga y los resultados anteriores; no se acumulan archivos.")
        options = ["Cargar un archivo Excel", "Usar reporte incluido"]
        if saved:
            options.insert(0, "Usar datos guardados")
        if "source_mode" not in st.session_state:
            st.session_state.source_mode = options[0]
        source_mode = st.radio("Origen de los instructores", options, key="source_mode", horizontal=True)
        content = None
        if source_mode == "Cargar un archivo Excel":
            uploaded = st.file_uploader("Reporte de instructores (.xlsx)", type=["xlsx"], key="report_upload")
            st.caption("Primera hoja: Nombre, Documento, Tipo Contrato y Total Horas, con las especialidades como títulos de sección.")
            if uploaded is not None:
                source_name, content = uploaded.name, uploaded.getvalue()
        elif source_mode == "Usar reporte incluido":
            source_name = DEFAULT_EXCEL.name
            try:
                content = DEFAULT_EXCEL.read_bytes()
            except OSError as exc:
                st.error(f"No fue posible leer el reporte incluido: {exc}")
        elif saved:
            instructors = saved[0]
            source_name, source_digest = previous["source_name"], previous["source_digest"]
        if content is not None:
            source_digest = sha256(content).hexdigest()
            try:
                instructors = read_report(content)
            except Exception as exc:
                st.error(f"No fue posible leer el reporte: {exc}")

        if instructors is not None:
            st.info(
                f"{source_name} · {len(instructors.attrs.get('specialties', []))} especialidades · "
                f"{int(instructors['Es planta'].sum())} instructores de planta · "
                f"{int((~instructors['Es planta']).sum())} contratistas actuales."
            )
            with st.expander("Revisar los instructores del archivo antes de ejecutar"):
                st.dataframe(instructors, hide_index=True, use_container_width=True)
        else:
            st.info("Seleccione un archivo válido o el reporte incluido para preparar la distribución.")

        c1, c2 = st.columns(2)
        year = c1.number_input("Vigencia a planear", min_value=2000, max_value=2200, value=previous.get("planning_year", date.today().year + 1), step=1, key="planning_year")
        target = c2.number_input("Meta de aprendices nuevos", min_value=0, value=previous.get("target_learners", 500), step=25, key="target_learners")
        with st.expander("Parámetros de cálculo", expanded=True):
            c1, c2, c3 = st.columns(3)
            learners = c1.number_input("Aprendices por ficha", min_value=1, value=int(defaults["learners_per_ficha"]), key="learners_per_ficha")
            weekly = c2.number_input("Horas semanales por ficha", min_value=1.0, value=float(defaults["weekly_hours_per_ficha"]), step=1.0, key="weekly_hours_per_ficha")
            plant_hours = c3.number_input("Horas semanales por instructor de planta", min_value=1.0, value=float(defaults["weekly_plant_direct_hours"]), step=0.5, key="weekly_plant_direct_hours")
            bilingual = c1.number_input("Horas de bilingüismo por ficha", min_value=0.0, value=float(defaults["weekly_bilingual_hours"]), step=1.0, key="weekly_bilingual_hours")
            integrality = c2.number_input("Horas de integralidad por ficha", min_value=0.0, value=float(defaults["weekly_integrality_hours"]), step=1.0, key="weekly_integrality_hours")
            contractor_hours = c3.number_input("Horas semanales por contratista", min_value=1.0, value=float(defaults["weekly_contractor_hours"]), step=1.0, key="weekly_contractor_hours")
        rules = PlanningRules(int(learners), weekly, bilingual, integrality, plant_hours, contractor_hours)
        errors = rules.validate()
        for error in errors:
            st.error(error)
        expected_new = fichas_from_target(int(target), int(learners))
        st.markdown("**2. Ingresar las fichas por especialidad técnica**")
        st.caption(
            "Ingrese manualmente las fichas que pasan en cada especialidad (0 si no hay). "
            "Indique cuántas de esas fichas terminan durante la vigencia y se prevé reemplazar. "
            "El total se suma automáticamente; estas cantidades nunca se reparten ni se cambian por una sugerencia."
        )
        st.caption(f"La meta actual equivale a {expected_new} fichas nuevas. Horas técnicas por ficha: {rules.weekly_technical_hours:g} h/semana.")
        if instructors is not None:
            if st.session_state.get("distribution_source") != source_digest:
                st.session_state.distribution_source = source_digest
                if source_digest == previous.get("source_digest"):
                    base = pd.DataFrame(previous["distribution"])
                    if "Fichas que terminan" not in base:
                        base["Fichas que terminan"] = 0
                    base = base.reindex(columns=MANUAL_COLUMNS)
                else:
                    catalog = technical_specialty_catalog(instructors)
                    base = pd.DataFrame({
                        "Especialidad": catalog["Especialidad"],
                        "Fichas que pasan": pd.Series(pd.NA, index=catalog.index, dtype="Int64"),
                        "Fichas que terminan": 0,
                    })
                st.session_state.distribution_base = base
                st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
            if list(st.session_state.distribution_base.columns) != MANUAL_COLUMNS:
                if "Fichas que terminan" not in st.session_state.distribution_base:
                    st.session_state.distribution_base["Fichas que terminan"] = 0
                st.session_state.distribution_base = st.session_state.distribution_base.reindex(columns=MANUAL_COLUMNS)
                st.session_state.editor_revision += 1
            if source_digest == previous.get("source_digest") and previous.get("distribution_basis") != "automatic_growth_v1":
                st.info("Esta planeación se guardó con el método anterior. Se conservan sus cantidades manuales; las nuevas se proyectan ahora con reposición y crecimiento mínimo del 5 %. Ejecute para guardar el nuevo cálculo.")
            manual = st.data_editor(
                st.session_state.distribution_base, use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    "Especialidad": st.column_config.TextColumn(required=True),
                    "Fichas que pasan": st.column_config.NumberColumn("Fichas que pasan (manual)", min_value=0, step=1, required=True),
                    "Fichas que terminan": st.column_config.NumberColumn("De esas, terminan en la vigencia", min_value=0, step=1, required=True, help="Solo cuente fichas incluidas en las que pasan. Sirven de referencia para las reposiciones."),
                },
                key=f"distribution_{source_digest}_{st.session_state.editor_revision}",
            )
            try:
                distribution = project_distribution(manual, instructors, int(target), int(learners))
                continuing = int(distribution["Fichas que pasan"].sum())
                projected_new = int(distribution["Fichas nuevas"].sum())
                rule = growth_requirements(distribution)
                st.markdown("**Proyección automática de fichas nuevas**")
                st.write(
                    f"Fichas según la meta: **{expected_new}** · Reposiciones: **{rule['replacement_fichas']}** · "
                    f"Crecimiento mínimo: **{rule['growth_fichas']}** · Nuevas proyectadas: **{projected_new}**."
                )
                projection = pd.DataFrame(rule["rows"], columns=[
                    "Especialidad", "Fichas que pasan", "Fichas que terminan",
                    "Crecimiento mínimo (5 %)", "Mínimo de fichas nuevas",
                ])
                projection["Adicionales para completar la meta"] = distribution["Fichas nuevas"] - projection["Mínimo de fichas nuevas"]
                projection["Fichas nuevas"] = distribution["Fichas nuevas"]
                projection["Fichas al cierre"] = distribution["Fichas que pasan"] - distribution["Fichas que terminan"] + distribution["Fichas nuevas"]
                st.dataframe(projection, hide_index=True, use_container_width=True)
                st.caption(
                    "Cada especialidad recibe sus reposiciones + el 5 % de las fichas que pasan, redondeado hacia arriba. "
                    "Las fichas restantes de la meta se reparten proporcionalmente a las que pasan. "
                    "La proyección se actualiza al cambiar cualquier dato, sin modificar las cantidades manuales."
                )
                if projected_new > expected_new:
                    st.warning(
                        f"La regla requiere {projected_new - expected_new} fichas adicionales sobre la meta. "
                        f"Se proyectan {projected_new} fichas nuevas, equivalentes a {projected_new * int(learners)} "
                        f"cupos, frente a la meta ingresada de {int(target)} aprendices. Puede ejecutar y guardar esta proyección."
                    )
                if continuing == 0 and expected_new > 0:
                    st.info("Todas las continuaciones son cero: la meta se reparte equitativamente entre las especialidades registradas.")
                draft_valid = not errors
                if draft_valid:
                    st.success("Proyección lista para ejecutar: reposiciones y crecimiento del 5 % cubiertos.")
            except ValueError as exc:
                st.warning(str(exc))

        st.markdown("**3. Ejecutar y guardar**")
        st.caption("La carga anterior se elimina únicamente cuando la nueva planeación es válida y se guarda correctamente.")
        execute = st.button("Ejecutar y guardar planeación", type="primary", use_container_width=True, disabled=not draft_valid)
        if execute:
            try:
                with st.spinner("Calculando y guardando en SQLite…"):
                    execution = execute_plan(instructors, distribution, rules, int(target), int(year), source_name, source_digest)
                    save_planning(DATABASE_PATH, instructors, execution)
                    saved = load_planning(DATABASE_PATH)
                st.success("Planeación ejecutada y guardada. La base de datos contiene únicamente esta carga y su última ejecución.")
            except (ValueError, sqlite3.Error, OSError) as exc:
                st.error(f"No fue posible ejecutar y guardar la planeación: {exc}")

    st.divider()
    if saved:
        current = saved[1]
        pending = (
            not draft_valid or source_digest != current["source_digest"]
            or source_name != current["source_name"] or int(year) != current["planning_year"]
            or int(target) != current["target_learners"] or int(continuing) != current["continuing_fichas"]
            or asdict(rules) != current["rules"]
            or current.get("distribution_basis") != "automatic_growth_v1"
        )
        if draft_valid:
            pending = pending or distribution.to_dict("records") != current["distribution"]
        if pending:
            st.warning("Hay datos pendientes de ejecutar. Los resultados y la descarga corresponden a la última ejecución guardada indicada abajo.")
        render_results(*saved)
    else:
        st.info("Aún no hay una planeación guardada. Complete los datos y pulse «Ejecutar y guardar planeación» para obtener los resultados.")


if __name__ == "__main__":
    main()
