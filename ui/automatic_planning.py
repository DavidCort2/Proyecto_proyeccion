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
from core.database import database_reset_version, load_planning, save_planning
from core.excel_parser import parse_instructors_excel
from core.fichas_parser import parse_fichas_excel
from ui.curriculum_input import curriculum_inputs, resettable_upload_key
from core.export import export_planning
from ui.contracting_results import render_contracting_summary, render_contracting_details, render_planning_details
from ui.system_reset import render_system_reset


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
                                   value=saved_targets.get("Técnico", previous.get("target_learners", 0)), step=25, key="target_technical"),
        "Tecnólogo": c3.number_input("Meta de aprendices · Tecnólogo", min_value=0,
                                     value=saved_targets.get("Tecnólogo", 0), step=25, key="target_technologist"),
    }
    st.caption("La meta es el total de aprendices de la vigencia: incluye fichas que pasan y nuevas. Ingrese la meta final con su crecimiento incluido. Las nuevas cubren únicamente el saldo pendiente.")
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
        weights = tuple(int(offers[q].number_input(f"Ingresos en oferta T{q + 1} (%)", min_value=0, max_value=100,
                            value=int(defaults["intake_weights"][q]), key=f"intake_weight_{q}")) for q in range(4))
        st.caption("Los porcentajes deben sumar 100 %. Distribuyen todas las fichas nuevas calculadas para la meta, incluidas las que reemplazan salidas. No se agregan fichas ni otro 5 % por fuera de ese total.")
    # Los campos históricos de horas transversales no participan en el modelo curricular.
    rules = PlanningRules(int(learners), weekly, 0.0, 0.0, plant, contract, mixed, 0.0, 0.0, int(weeks), weights)
    return int(year), {level: int(value) for level, value in targets.items()}, rules


def instructor_source(saved):
    previous = saved[1] if saved else {}
    options = (["Usar datos guardados"] if saved else []) + ["Cargar un archivo Excel"]
    if st.session_state.get("source_mode") not in options:
        st.session_state.source_mode = options[0]
    mode = st.radio("Origen del reporte de planta", options, horizontal=True, key="source_mode")
    if mode == "Usar datos guardados":
        return saved[0], previous["source_name"], previous["source_digest"]
    upload = st.file_uploader("Reporte para identificar la planta (.xlsx)", type=["xlsx"], key=resettable_upload_key("report_upload"))
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
    upload = st.file_uploader("Reporte de fichas (.xlsx)", type=["xlsx"], key=resettable_upload_key("fichas_upload"))
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
    st.caption("Contratación requerida a partir de las horas de las mallas y la cobertura de planta.")
    try:
        revision = database_reset_version(path)
        reset_complete = st.session_state.pop("_system_reset_complete", False)
        if st.session_state.get("_database_reset_version", 0) != revision:
            st.session_state.clear()
            read_instructors.clear()
            read_fichas.clear()
        st.session_state["_database_reset_version"] = revision
        if reset_complete:
            st.success("Sistema limpio. Las metas están en cero y los parámetros recuperaron sus valores iniciales. Puede cargar los reportes y las mallas para comenzar de nuevo.")
        saved = load_planning(path)
        planning_tab, settings_tab, curriculum_tab = st.tabs(["Planeación", "Reportes y parámetros", "Mallas y competencias"])
        with curriculum_tab:
            catalog, catalog_ready = curriculum_inputs(path)
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f"No fue posible abrir los datos: {exc}")
        return
    previous = saved[1] if saved else {}
    preview, problem = None, None
    with settings_tab:
        st.subheader("Reportes de origen")
        try:
            instructors, source_name, source_digest = instructor_source(saved)
            fichas = ficha_source(previous)
        except Exception as exc:
            problem = f"No fue posible leer los reportes: {exc}"
            st.error(problem)
            instructors, fichas = None, None
        if instructors is not None:
            st.info(f"{source_name} · {int(instructors['Es planta'].sum())} instructores de planta para cubrir la demanda.")
            with st.expander("Revisar la planta del reporte"):
                st.dataframe(instructors.loc[instructors["Es planta"], ["Área", "Especialidad", "Nombre", "Documento"]],
                             hide_index=True, use_container_width=True)
        st.subheader("Metas y parámetros")
        year, targets, rules = parameters(previous)
        for error in rules.validate_curricular():
            st.error(error)
        if instructors is not None and fichas is not None and not rules.validate_curricular():
            try:
                frame, name, digest, report_year, report_quarter = fichas
                imported = prepare_ficha_import(frame, instructors, catalog, year, name, digest, report_year, report_quarter)
                coverage = curriculum_coverage(pd.DataFrame(imported["summary"]), catalog)
                with st.expander("Fichas de origen y cobertura curricular"):
                    st.caption(f"{name} · {report_year}-T{report_quarter} · {len(frame)} fichas.")
                    st.dataframe(pd.DataFrame(imported["summary"]), hide_index=True, use_container_width=True)
                    st.dataframe(coverage, hide_index=True, use_container_width=True)
                    st.dataframe(pd.DataFrame(imported["detail"]), hide_index=True, use_container_width=True)
                if catalog_ready:
                    preview = execute_curriculum_plan(instructors, imported, catalog, rules, targets, year, source_name, source_digest)
            except ValueError as exc:
                problem = str(exc)

        render_system_reset(path)

    with planning_tab:
        if preview is not None:
            render_contracting_summary(preview)
        else:
            st.subheader(f"Contratación requerida · Vigencia {year}")
            if problem:
                st.warning(problem)
            if not catalog_ready:
                st.info("Complete y guarde las mallas y su clasificación en «Mallas y competencias».")
            if instructors is None or fichas is None:
                st.info("Cargue los reportes de planta y fichas en «Reportes y parámetros» para obtener el total de contratistas.")
            if rules.validate_curricular():
                st.warning("Revise los parámetros de cálculo en «Reportes y parámetros»: " + " ".join(rules.validate_curricular()))

        current = {k: v for k, v in previous.items() if k != "saved_at"}
        pending = preview is None or json.dumps(preview, sort_keys=True) != json.dumps(current, sort_keys=True)
        if preview is not None:
            if pending:
                st.caption("Vista previa con la configuración visible. Pulse «Ejecutar y guardar planeación» para guardar este resultado.")
            else:
                st.caption(f"Resultado guardado · Vigencia {year}.")
        save_column, download_column = st.columns(2)
        if save_column.button("Ejecutar y guardar planeación", type="primary", use_container_width=True, disabled=preview is None):
            try:
                save_planning(path, instructors, preview)
                saved = load_planning(path)
                pending = False
                st.success("Planeación guardada. El Excel contiene el total requerido y las fechas de cada contratista proyectado.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f"No fue posible guardar la planeación: {exc}")
        can_download = saved is not None and not pending
        download_column.download_button(
            "Descargar planeación guardada en Excel",
            data=export_planning(*saved) if can_download else b"",
            file_name=f"planeacion_indicativa_{year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, disabled=not can_download,
        )
        if saved and pending:
            st.warning("Hay datos pendientes de ejecutar. Guarde la nueva planeación para actualizar los resultados y su descarga.")
        if preview is not None:
            center = preview["center"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de horas al año", f"{center['demanda_total_horas_anuales']:g}")
            c2.metric("Fichas nuevas proyectadas", center["fichas_nuevas"])
            c3.metric("Fichas que pasan", center["fichas_que_pasan"])
            st.subheader("Detalle de la planeación")
            render_contracting_details(preview)
            render_planning_details(preview, instructors)
        if saved and pending:
            with st.expander("Descargar la ejecución anterior"):
                st.caption(f"Vigencia {saved[1]['planning_year']} · Guardada (UTC): {saved[1]['saved_at']}.")
                st.download_button(
                    "Descargar Excel anterior", data=export_planning(*saved),
                    file_name=f"planeacion_anterior_{saved[1]['planning_year']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
