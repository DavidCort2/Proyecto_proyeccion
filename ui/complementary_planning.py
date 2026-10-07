"""Interfaz simple con planeación conjunta de Complementaria presencial y virtual."""
from copy import deepcopy
from datetime import datetime
import json
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from core.complementary_export import export_complementary
from core.complementary_inputs import default_settings, PLANT_WEEKLY_HOURS
from core.complementary_planner import execute_complementary_plan
from core.complementary_sources import load_support_sources, MODALITIES
from core.complementary_store import load_complementary, save_complementary
from core.planning_modules import complementary_database
from ui.planning_session import scoped_key, widget_key


def render_inputs(previous, modality):
    defaults = previous.get("inputs", {}).get(modality, default_settings())
    c1, c2, c3 = st.columns(3)
    target = c1.number_input("Meta de aprendices", min_value=0, value=defaults["target_learners"], step=1,
                             key=widget_key("target_learners"))
    learners = c2.number_input("Promedio de aprendices por curso", min_value=1, value=defaults["learners_per_course"], step=1,
                               key=widget_key("learners_per_course"))
    duration_key = widget_key("duration_hours")
    # Recuperar el borrador al navegar y la ejecución guardada al reabrir.
    # Un valor inicial vacío hacía que el control perdiera las horas al reconstruirse.
    duration_default = st.session_state.get(scoped_key("draft"), defaults)["duration_hours"]
    duration = c3.number_input("Duración promedio de los cursos (horas)", min_value=0.01,
                               value=float(duration_default) if duration_default is not None else None,
                               step=1.0, key=duration_key)
    st.caption("Cada curso ocupa 10 horas semanales. Con 40 horas libres, un contratista puede atender 4 cursos simultáneos. "
               "En los contratistas de Titulada se descuenta primero toda su formación ya programada.")
    st.subheader("Planta propia de Complementaria")
    st.caption("Registre únicamente la planta de esta modalidad de Complementaria. La planta de Titulada no se utiliza. "
               "Las 32 horas corresponden a capacidad de formación; no a la jornada laboral total.")
    frame = pd.DataFrame(defaults["plant"], columns=["Nombre completo", "Cédula", "Horas semanales"])
    for column in ("Nombre completo", "Cédula"):
        frame[column] = frame[column].astype("string")
    frame["Horas semanales"] = pd.to_numeric(frame["Horas semanales"], errors="coerce").astype(float)
    plant = st.data_editor(frame, hide_index=True, num_rows="dynamic", use_container_width=True,
        column_config={"Nombre completo": st.column_config.TextColumn(required=True),
                       "Cédula": st.column_config.TextColumn(required=True),
                       "Horas semanales": st.column_config.NumberColumn(min_value=0.01, max_value=PLANT_WEEKLY_HOURS,
                                                                         default=PLANT_WEEKLY_HOURS, required=True)},
        key=widget_key("plant_" + str(previous.get("revision", 0))))
    return {"target_learners": target, "learners_per_course": learners, "duration_hours": duration,
            "plant": plant.to_dict("records")}


def render_results(plan, modality):
    summary = next(row for row in plan["modalities"] if row["Modalidad"] == modality)
    st.subheader(f"Cobertura de Complementaria {modality.lower()} · {plan['planning_year']}")
    columns = st.columns(4)
    for col, label, value in zip(columns,
        ["Cursos necesarios", "Cursos con planta propia", "Cursos con apoyo de Titulada", "Contratistas adicionales estimados"],
        [summary["Cursos necesarios"], summary["Cursos con planta propia"], summary["Cursos con apoyo de Titulada"],
         summary["Pico de contratistas adicionales"]]):
        col.metric(label, value)
    c1, c2, c3 = st.columns(3)
    c1.metric("Cupos proyectados", summary["Cupos proyectados"])
    c2.metric("Horas de cursos", f"{summary['Horas requeridas']:g}")
    c3.metric("Inicio del pico adicional", summary["Inicio del pico adicional"] or "Sin contratación adicional")
    if summary["Cursos que requieren contratación adicional"]:
        st.info(f"La planta propia y las horas reutilizadas dejan {summary['Cursos que requieren contratación adicional']} cursos "
                "por cubrir. La contratación adicional mostrada es una propuesta para completar esa diferencia.")
    st.caption("Los cursos pueden comenzar durante todo el año según la disponibilidad. Las fechas son indicativas. "
               "Un curso se asigna solo si cabe completo en la disponibilidad del mismo instructor.")
    with st.expander("Resumen conjunto: capacidad compartida entre modalidades"):
        st.metric("Pico conjunto de contratistas adicionales", plan["summary"]["pico_contratistas_adicionales"])
        st.caption("Un mismo instructor puede atender ambas modalidades. El pico conjunto cuenta personas únicas; "
                   "no se deben sumar los picos separados.")
        st.dataframe(pd.DataFrame(plan["modalities"]), hide_index=True, use_container_width=True)
    for key, label in [("courses", "Cursos proyectados, instructor y fechas"), ("monthly", "Distribución mensual de cursos y horas")]:
        with st.expander(label):
            st.dataframe(pd.DataFrame([row for row in plan[key] if row["Modalidad"] == modality]), hide_index=True, use_container_width=True)
    with st.expander("Contratación adicional y fechas · ambas modalidades"):
        st.dataframe(pd.DataFrame(plan["contracts"]), hide_index=True, use_container_width=True)
    with st.expander("Carga compartida por instructor"):
        st.caption("Titulada y las dos modalidades de Complementaria consumen una sola capacidad. "
                   "La planta propia completa su capacidad restante con otras actividades.")
        st.dataframe(pd.DataFrame(plan["monthly_instructors"]), hide_index=True, use_container_width=True)
    with st.expander("Verificar capacidad por fechas"):
        st.caption("La reserva corresponde a jornadas de 2 horas por curso. En la última jornada solo se contabilizan "
                   "las horas restantes, aunque se conserva la reserva para no sobreprogramar al instructor.")
        st.dataframe(pd.DataFrame(plan["instructor_intervals"]), hide_index=True, use_container_width=True)


def render_complementary_planning(base_path, modality):
    path = complementary_database(base_path)
    try:
        saved = load_complementary(path)
    except (OSError, sqlite3.Error, ValueError) as exc:
        st.error(f"No fue posible abrir Complementaria: {exc}")
        return
    previous = saved or {}
    st.caption("Las dos modalidades comparten las horas libres de contratistas de Titulada. Guardar recalcula Complementaria "
               "presencial y virtual juntas; las planeaciones de Titulada se consultan y se conservan.")
    planning, settings_tab, sources_tab = st.tabs(["Planeación", "Meta y planta", "Fuentes y criterios"])
    with settings_tab:
        year_key = "complementaria:shared:planning_year"
        st.session_state.setdefault("_planning_widget_keys", set()).add(year_key)
        year = st.number_input("Vigencia de Complementaria · ambas modalidades", min_value=2000, max_value=2200,
            value=previous.get("planning_year", datetime.now(ZoneInfo("America/Bogota")).year + 1), step=1, key=year_key)
        draft = render_inputs(previous, modality)
        st.session_state[scoped_key("draft")] = draft
    inputs = {m: deepcopy(previous.get("inputs", {}).get(m, default_settings())) for m in MODALITIES}
    for mode in MODALITIES:
        key = f"complementaria:{mode.lower()}:draft"
        if key in st.session_state:
            inputs[mode] = deepcopy(st.session_state[key])
    preview, sources, problem = None, [], None
    try:
        sources = load_support_sources(base_path, year)
        preview = execute_complementary_plan(inputs, sources, year)
    except (ValueError, OSError, sqlite3.Error) as exc:
        problem = str(exc)
    with sources_tab:
        st.dataframe(pd.DataFrame([source["metadata"] for source in sources]), hide_index=True, use_container_width=True)
        st.caption("Se usan las últimas ejecuciones guardadas de Titulada de la misma vigencia. "
                   "Si una modalidad no tiene ejecución, no aporta capacidad. Al guardar cambios en Titulada, "
                   "la siguiente vista previa de Complementaria toma la nueva disponibilidad.")
        if preview:
            st.caption(preview["calculation_basis"])
        st.markdown("**Referencias oficiales SENA**")
        st.markdown("[Resolución 1-02206 de 2025](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_2206_2025.htm) "
                    "y [modificación 1-01041 de 2026](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_1041_2026.htm): "
                    "clasificación, modalidades y duración de los programas según su diseño.")
        st.markdown("[Resolución 642 de 2004](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_0642_2004.htm): "
                    "distingue la jornada de planta de 42,5 horas y sus 32 horas de formación directa.")
        st.caption("Las 10 horas semanales por curso y las 40 por contratista son parámetros operativos indicados por el centro. "
                   "Este escenario usa duración promedio; no reemplaza el diseño de cada curso ni verifica el perfil temático del instructor.")
    with planning:
        message = st.session_state.pop(scoped_key("saved_message"), None)
        if message:
            st.success(message)
        if problem:
            st.info(problem)
        current = {key: value for key, value in previous.items() if key not in {"saved_at", "revision"}}
        pending = preview is None or json.dumps(preview, sort_keys=True) != json.dumps(current, sort_keys=True)
        if preview:
            render_results(preview, modality)
            if any(source["metadata"]["Estado"] != "Disponible" for source in sources):
                st.info("Hay modalidades de Titulada sin planeación guardada para esta vigencia. Consulte Fuentes y criterios; "
                        "la estimación adicional podría bajar al guardar esas planeaciones.")
        if st.button("Ejecutar y guardar Complementaria", type="primary", disabled=preview is None, key=widget_key("save")):
            try:
                save_complementary(path, preview, expected_revision=previous.get("revision", 0))
            except (OSError, ValueError, sqlite3.Error) as exc:
                st.error(f"No fue posible guardar Complementaria: {exc}")
            else:
                st.session_state[scoped_key("saved_message")] = "Complementaria presencial y virtual recalculadas y guardadas."
                st.rerun()
        if saved and pending:
            st.caption("La vista previa tiene cambios. Guarde para actualizar el Excel conjunto.")
        st.download_button("Descargar Complementaria en Excel", data=export_complementary(saved) if saved and not pending else b"",
            file_name=f"planeacion_complementaria_{year}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=not saved or pending, key=widget_key("download"))
