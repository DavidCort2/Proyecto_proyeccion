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
from core.planner import fichas_from_target, suggested_ficha_distribution
from core.workflow import DISTRIBUTION_COLUMNS, execute_plan, validate_distribution
from ui.results import render_results

BASE_DIR = Path(__file__).resolve().parent
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

        c1, c2, c3 = st.columns(3)
        year = c1.number_input("Vigencia a planear", min_value=2000, max_value=2200, value=previous.get("planning_year", date.today().year + 1), step=1, key="planning_year")
        target = c2.number_input("Meta de aprendices nuevos", min_value=0, value=previous.get("target_learners", 500), step=25, key="target_learners")
        continuing = c3.number_input("Fichas que continúan el siguiente año", min_value=0, value=previous.get("continuing_fichas", 0), step=1, key="continuing_fichas")
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
        st.markdown("**2. Distribuir las fichas por especialidad técnica**")
        st.caption(f"Distribuya {expected_new} fichas nuevas y {continuing} que continúan. Total: {expected_new + continuing} fichas activas. Horas técnicas por ficha: {rules.weekly_technical_hours:g} h/semana.")
        if instructors is not None:
            if st.session_state.get("distribution_source") != source_digest:
                st.session_state.distribution_source = source_digest
                if source_digest == previous.get("source_digest"):
                    base = pd.DataFrame(previous["distribution"], columns=DISTRIBUTION_COLUMNS)
                else:
                    base = suggested_ficha_distribution(instructors, expected_new, int(continuing))
                st.session_state.distribution_base = base
                st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
            if st.button("Generar distribución proporcional", help="Reemplaza las ediciones de la tabla con una propuesta según la planta técnica disponible."):
                st.session_state.distribution_base = suggested_ficha_distribution(instructors, expected_new, int(continuing))
                st.session_state.editor_revision += 1
            st.caption("Edite la propuesta según la oferta real. Puede agregar especialidades sin planta. Cambiar la meta conserva sus ediciones; el botón anterior genera una nueva propuesta.")
            distribution = st.data_editor(
                st.session_state.distribution_base, use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    "Especialidad": st.column_config.TextColumn(required=True),
                    "Fichas nuevas": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                    "Fichas que pasan": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                },
                key=f"distribution_{source_digest}_{st.session_state.editor_revision}",
            )
            try:
                distribution = validate_distribution(distribution, instructors, expected_new, int(continuing))
                draft_valid = not errors
                st.success("La distribución coincide con los totales de la planeación.")
            except ValueError as exc:
                st.warning(str(exc))

        st.markdown("**3. Ejecutar y guardar**")
        st.caption("La carga anterior se elimina únicamente cuando la nueva planeación es válida y se guarda correctamente.")
        execute = st.button("Ejecutar y guardar planeación", type="primary", use_container_width=True, disabled=not draft_valid)
        if execute:
            try:
                with st.spinner("Calculando y guardando en SQLite…"):
                    execution = execute_plan(instructors, distribution, rules, int(target), int(continuing), int(year), source_name, source_digest)
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
