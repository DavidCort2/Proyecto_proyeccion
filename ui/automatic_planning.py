"""Flujo principal: dos reportes, mallas y parámetros; cantidades derivadas."""
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.config import PlanningRules
from core.curriculum_planner import curriculum_coverage, execute_curriculum_plan, prepare_ficha_import
from core.database import load_planning, save_planning
from core.excel_parser import parse_instructors_excel
from core.fichas_parser import parse_fichas_excel
from ui.curriculum_input import curriculum_inputs
from ui.results import render_results
from ui.contracting_results import render_contracting


@st.cache_data(show_spinner=False, max_entries=8)
def read_instructors(content):
    return parse_instructors_excel(BytesIO(content))


@st.cache_data(show_spinner=False, max_entries=8)
def read_fichas(content):
    return parse_fichas_excel(BytesIO(content))


def parameters(previous):
    defaults = {**asdict(PlanningRules()), **previous.get("rules", {})}
    c1, c2, c3 = st.columns(3)
    year = c1.number_input("Vigencia a planear", min_value=2000, max_value=2200,
                           value=previous.get("planning_year", date.today().year + 1), step=1, key="planning_year")
    saved_targets = previous.get("targets_by_level", {})
    targets = {
        "Técnico": c2.number_input("Meta de aprendices · Técnico", min_value=0,
                                   value=saved_targets.get("Técnico", previous.get("target_learners", 500)), step=25, key="target_technical"),
        "Tecnólogo": c3.number_input("Meta de aprendices · Tecnólogo", min_value=0,
                                     value=saved_targets.get("Tecnólogo", 0), step=25, key="target_technologist"),
    }
    with st.expander("Parámetros de cálculo", expanded=True):
        c1, c2, c3 = st.columns(3)
        learners = c1.number_input("Aprendices por ficha", min_value=1, value=int(defaults["learners_per_ficha"]), key="learners_per_ficha")
        plant = c2.number_input("Horas semanales por instructor de planta", min_value=1.0,
                                value=float(defaults["weekly_plant_direct_hours"]), key="weekly_plant_direct_hours")
        contract = c3.number_input("Horas semanales por contratista", min_value=1.0,
                                   value=float(defaults["weekly_contractor_hours"]), key="weekly_contractor_hours")
        weeks = c1.number_input("Semanas efectivas por trimestre", min_value=1, max_value=13,
                                value=int(defaults["weeks_per_quarter"]), key="weeks_per_quarter")
        weekly = c2.number_input("Horas semanales por ficha diurna (referencia)", min_value=1.0,
                                 value=float(defaults["weekly_hours_per_ficha"]), key="weekly_hours_per_ficha")
        mixed = c3.number_input("Horas semanales por ficha mixta (referencia)", min_value=1.0,
                                value=float(defaults["mixed_weekly_hours_per_ficha"]), key="mixed_weekly_hours_per_ficha")
        st.caption("Las horas de formación provienen de cada resultado de la malla. Las jornadas de referencia permiten revisar diferencias; no rellenan ni sustituyen horas curriculares. Horas trimestrales = horas semanales de la malla × semanas efectivas.")
        offers = st.columns(4)
        weights = tuple(int(offers[q].number_input(f"Oferta adicional T{q + 1} (%)", min_value=0, max_value=100,
                            value=int(defaults["intake_weights"][q]), key=f"intake_weight_{q}")) for q in range(4))
        st.caption("Los porcentajes deben sumar 100 %. Distribuyen el saldo de la meta y el crecimiento mínimo del 5 %. Las reposiciones se abren en el trimestre siguiente a la terminación.")
    # Los campos históricos de horas transversales no participan en el modelo curricular.
    rules = PlanningRules(int(learners), weekly, 0.0, 0.0, plant, contract, mixed, 0.0, 0.0, int(weeks), weights)
    return int(year), {level: int(value) for level, value in targets.items()}, rules


def instructor_source(saved):
    previous = saved[1] if saved else {}
    options = (["Usar datos guardados"] if saved else []) + ["Cargar un archivo Excel"]
    if st.session_state.get("source_mode") not in options:
        st.session_state.source_mode = options[0]
    mode = st.radio("Origen de los instructores", options, horizontal=True, key="source_mode")
    if mode == "Usar datos guardados":
        return saved[0], previous["source_name"], previous["source_digest"]
    upload = st.file_uploader("Reporte de instructores (.xlsx)", type=["xlsx"], key="report_upload")
    if upload is None:
        return None, "", ""
    content = upload.getvalue()
    return read_instructors(content), upload.name, sha256(content).hexdigest()


def ficha_source(previous):
    stored = previous.get("ficha_import")
    options = (["Usar reporte de fichas guardado"] if stored else []) + ["Cargar reporte de fichas"]
    if st.session_state.get("fichas_mode") not in options:
        st.session_state.fichas_mode = options[0]
    mode = st.radio("Origen de las fichas", options, horizontal=True, key="fichas_mode")
    if mode == "Usar reporte de fichas guardado":
        return pd.DataFrame(stored["rows"]), stored["source_name"], stored["source_digest"], stored["report_year"], stored["report_quarter"]
    upload = st.file_uploader("Reporte de fichas (.xlsx)", type=["xlsx"], key="fichas_upload")
    if upload is None:
        return None
    content = upload.getvalue()
    frame = read_fichas(content)
    if "report_year" not in frame.attrs or "report_quarter" not in frame.attrs:
        raise ValueError("El reporte de fichas debe indicar año y trimestre en su encabezado, por ejemplo: 2026 - Trimestre 4.")
    return frame, upload.name, sha256(content).hexdigest(), frame.attrs["report_year"], frame.attrs["report_quarter"]


def render_automatic_planning(path):
    st.set_page_config(page_title="Planeación Indicativa SENA", page_icon="📊", layout="wide")
    st.title("Planeación Indicativa")
    st.caption("Cargue los reportes y las mallas. Configure metas, ofertas y competencias transversales para calcular las horas e instructores por trimestre.")
    try:
        saved = load_planning(path)
        planning_tab, curriculum_tab = st.tabs(["Planeación", "Mallas y competencias"])
        with curriculum_tab:
            catalog, catalog_ready = curriculum_inputs(path)
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f"No fue posible abrir los datos: {exc}")
        return
    previous = saved[1] if saved else {}
    preview = None
    with planning_tab:
        with st.container(border=True):
            st.subheader("1. Reportes de origen")
            try:
                instructors, source_name, source_digest = instructor_source(saved)
                fichas = ficha_source(previous)
            except Exception as exc:
                st.error(f"No fue posible leer los reportes: {exc}")
                instructors, fichas = None, None
            if instructors is not None:
                st.info(f"{source_name} · {int(instructors['Es planta'].sum())} instructores de planta para cubrir la demanda.")
                with st.expander("Revisar los instructores del archivo antes de ejecutar"):
                    st.dataframe(instructors.loc[instructors['Es planta']], hide_index=True, use_container_width=True)
            st.subheader("2. Metas y parámetros")
            year, targets, rules = parameters(previous)
            for error in rules.validate():
                st.error(error)
            if previous and previous.get("planning_mode") != "curricula_v3":
                st.info("La ejecución guardada usa el método anterior. Al ejecutar se calculará la contratación completa descontando solo planta, con sus períodos y reducciones según las mallas.")
            st.subheader("3. Proyección automática")
            if not catalog_ready:
                st.info("Complete y guarde las mallas y su clasificación en la pestaña «Mallas y competencias».")
            if instructors is None or fichas is None:
                st.info("Se necesitan ambos reportes: instructores y fichas actuales.")
            elif not rules.validate():
                try:
                    frame, name, digest, report_year, report_quarter = fichas
                    imported = prepare_ficha_import(frame, instructors, catalog, year, name, digest, report_year, report_quarter)
                    st.caption(f"{name} · {report_year}-T{report_quarter} · {len(frame)} fichas. Las duraciones disponibles se toman de las mallas; el trimestre cursado determina las horas pendientes.")
                    st.dataframe(pd.DataFrame(imported["summary"]), hide_index=True, use_container_width=True)
                    coverage = curriculum_coverage(pd.DataFrame(imported["summary"]), catalog)
                    missing = coverage.loc[coverage["Estado"] == "Falta malla"]
                    if not missing.empty:
                        st.warning("Hay programas o jornadas del reporte sin malla. Cargue las mallas indicadas para cubrir toda la planeación.")
                        st.dataframe(missing, hide_index=True, use_container_width=True)
                    with st.expander("Detalle de las fichas y cobertura curricular"):
                        st.dataframe(coverage, hide_index=True, use_container_width=True)
                        st.dataframe(pd.DataFrame(imported["detail"]), hide_index=True, use_container_width=True)
                    if catalog_ready:
                        preview = execute_curriculum_plan(instructors, imported, catalog, rules, targets, year, source_name, source_digest)
                        center, summary = preview["center"], preview["summary"]
                        st.dataframe(pd.DataFrame(preview["levels"]), hide_index=True, use_container_width=True)
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total de horas al año", f"{center['demanda_total_horas_anuales']:g}")
                        c2.metric("Fichas nuevas proyectadas", center["fichas_nuevas"])
                        c3.metric("Fichas que pasan", center["fichas_que_pasan"])
                        render_contracting(preview)
                        st.markdown("**Demanda y contratación por mes**")
                        st.caption(preview["monthly_basis"])
                        st.dataframe(pd.DataFrame(preview["monthly"]), hide_index=True, use_container_width=True)
                        with st.expander("Horas mensuales de cada ficha"):
                            st.dataframe(pd.DataFrame(preview["monthly_fichas"]), hide_index=True, use_container_width=True)
                        with st.expander("Capacidad mensual por perfil e instructor"):
                            st.dataframe(pd.DataFrame(preview["monthly_staffing"]), hide_index=True, use_container_width=True)
                            st.dataframe(pd.DataFrame(preview["monthly_instructors"]), hide_index=True, use_container_width=True)
                        with st.expander("Propuesta de distribución de horas entre instructores y fichas"):
                            st.dataframe(pd.DataFrame(preview["monthly_assignments"]), hide_index=True, use_container_width=True)
                        with st.expander("Ofertas, fichas activas y horas por programa"):
                            st.dataframe(pd.DataFrame(preview["calendar"]), hide_index=True, use_container_width=True)
                        with st.expander("Comprobar las horas por competencia y resultado"):
                            st.dataframe(pd.DataFrame(preview["curriculum_hours"]), hide_index=True, use_container_width=True)
                        st.success("Planeación lista: horas calculadas con las mallas de cada programa y jornada.")
                except ValueError as exc:
                    st.warning(str(exc))
            if st.button("Ejecutar y guardar planeación", type="primary", use_container_width=True, disabled=preview is None):
                try:
                    save_planning(path, instructors, preview)
                    saved = load_planning(path)
                    st.success("Planeación guardada. Las mallas y las competencias permanecen disponibles para las próximas vigencias.")
                except (ValueError, OSError, sqlite3.Error) as exc:
                    st.error(f"No fue posible guardar la planeación: {exc}")
        if saved:
            current = {k: v for k, v in saved[1].items() if k != "saved_at"}
            if preview is None or json.dumps(preview, sort_keys=True) != json.dumps(current, sort_keys=True):
                st.warning("Hay datos pendientes de ejecutar. Los resultados y la descarga corresponden a la última ejecución guardada.")
            if saved[1].get("planning_mode") == "curricula_v3":
                render_results(*saved)
