"""Interfaz de Titulada virtual: cronogramas, perfiles y ofertas por fecha."""
from datetime import date
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.database import database_reset_version, load_planning, save_planning
from core.export import export_planning
from core.virtual_schedule import read_date
from core.virtual_schedule_planner import VirtualRules, execute_virtual_schedule_plan
from ui.planning_session import clear_module_session, scoped_key, widget_key
from ui.system_reset import render_system_reset
from ui.virtual_schedule_input import manual_schedule_inputs, schedule_inputs


def virtual_parameters(previous):
    defaults = previous.get("rules", {})
    columns = st.columns(3)
    year = int(columns[0].number_input("Vigencia a planear", min_value=2000, max_value=2200,
                                      value=previous.get("planning_year", date.today().year + 1), key=widget_key("planning_year")))
    targets = {level: int(columns[i].number_input("Meta de aprendices · " + level, min_value=0, step=25,
                                                  value=previous.get("targets_by_level", {}).get(level, 0), key=widget_key(key)))
               for i, (level, key) in enumerate([("Técnico", "target_technical"), ("Tecnólogo", "target_technologist")], 1)}
    st.caption("La meta incluye los aprendices de las fichas que pasan y de las nuevas; el cálculo cubre únicamente el saldo pendiente.")
    with st.expander("Parámetros de cálculo", expanded=True):
        c1, c2, c3 = st.columns(3)
        learners = c1.number_input("Aprendices por ficha", min_value=1, value=int(defaults.get("learners_per_ficha", 25)), key=widget_key("learners_per_ficha"))
        plant = c2.number_input("Horas semanales por instructor de planta", min_value=1.0,
                               value=float(defaults.get("weekly_plant_direct_hours", 32)), key=widget_key("weekly_plant_direct_hours"))
        contractor = c3.number_input("Horas semanales por contratista", min_value=1.0,
                                    value=float(defaults.get("weekly_contractor_hours", 40)), key=widget_key("weekly_contractor_hours"))
        st.caption("Las fases y su duración provienen del cronograma. Las horas docentes se completan por actividad y ficha en «Cronogramas y competencias».")
        columns = st.columns(4)
        weights = tuple(columns[i].number_input(f"Ingresos en oferta {i + 1} (%)", min_value=0, max_value=100,
                                                 value=int(defaults.get("intake_weights", [50, 25, 15, 10])[i]),
                                                 key=widget_key(f"intake_weight_{i}")) for i in range(4))
        previous_dates = previous.get("virtual_inputs", {}).get("offers", [None] * 4)
        offers = []
        for i, column in enumerate(columns):
            prior = previous_dates[i] if len(previous_dates) == 4 else None
            value = read_date(prior, "Oferta") if prior else None
            if value and value.year != year:
                value = None
            chosen = column.date_input(f"Inicio de oferta {i + 1}", value=value, min_value=date(year, 1, 1), max_value=date(year, 12, 31),
                                       format="DD/MM/YYYY", key=widget_key(f"offer_date_{i}_{year}"))
            offers.append(chosen.isoformat() if chosen else None)
        st.caption("Configure las fechas de inicio de las cuatro ofertas según la vigencia. Los porcentajes deben sumar 100 %. Las ofertas son ingresos de fichas, independientes de las fases de los programas.")
    return year, targets, VirtualRules(int(learners), plant, contractor, weights), offers


def render_virtual_summary(plan):
    summary = plan["summary"]
    st.subheader(f"Contratación requerida · Vigencia {plan['planning_year']}")
    c1, c2 = st.columns(2)
    c1.metric("Total de contratistas requeridos", summary["pico_contratistas_total"])
    c2.metric("Intervalo del pico", f"{summary['inicio_pico']} → {summary['fin_pico']}" if summary["pico_contratistas_total"] else "Sin contratación")
    c1, c2 = st.columns(2)
    c1.metric("Técnicos en el pico", summary["tecnicos_en_pico"])
    c2.metric("Transversales en el pico", summary["transversales_en_pico"])
    st.caption("Los técnicos y transversales mostrados corresponden al mismo intervalo. La contratación se calcula cuando cambian las actividades; un promedio mensual no oculta los picos de carga.")


def render_virtual_details(plan):
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de horas al año", f"{plan['center']['demanda_total_horas_anuales']:g}")
    c2.metric("Fichas nuevas proyectadas", plan["center"]["fichas_nuevas"])
    c3.metric("Fichas que pasan", plan["center"]["fichas_que_pasan"])
    st.caption("El total corresponde únicamente a horas de instructor de etapa lectiva dentro de la vigencia. La etapa productiva y su seguimiento están excluidos.")
    for key, label in [("contracts", "Contratistas requeridos y fechas"), ("offers_by_program", "Fichas nuevas por programa y oferta"),
                       ("cohort_dates", "Fechas y fases de las fichas"), ("levels", "Metas por nivel"),
                       ("periods", "Contratación por intervalos del cronograma"), ("monthly", "Resumen mensual"),
                       ("staffing", "Cobertura de planta por tipo y perfil"), ("activity_hours", "Horas por fase, competencia y actividad")]:
        with st.expander(label):
            st.dataframe(pd.DataFrame(plan[key]), hide_index=True, use_container_width=True)
    with st.expander("Criterios utilizados"):
        st.write(plan["calculation_basis"])
        st.markdown("Referencia: [Manual ZAJUNA del instructor, cronograma y fases](https://zajuna.sena.edu.co/pdfs/titulada/manuales/MANUAL%20ZAJUNA%20INSTRUCTOR_compressed.pdf).")


def render_virtual_schedule_planning(path):
    st.caption("Planeación de horas de etapa lectiva por fases y fechas de los cronogramas Excel. La etapa productiva no genera horas ni contratación.")
    try:
        revision = database_reset_version(path)
        completed = st.session_state.pop(scoped_key("_system_reset_complete"), False)
        if st.session_state.get(scoped_key("_database_reset_version"), 0) != revision:
            clear_module_session()
        st.session_state[scoped_key("_database_reset_version")] = revision
        if completed:
            st.success("Sistema limpio en Titulada virtual. Puede cargar cronogramas e ingresar una nueva planeación.")
        saved = load_planning(path)
        previous = saved[1] if saved else {}
        planning, settings, schedules = st.tabs(["Planeación", "Datos manuales y parámetros", "Cronogramas y competencias"])
        with schedules:
            catalog, ready = schedule_inputs(path)
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(f"No fue posible abrir los datos virtuales: {exc}")
        return
    if saved and previous.get("planning_mode") != "virtual_schedule_v2":
        st.warning("La ejecución anterior se conserva para descargarla. Para la planeación por fases cargue los cronogramas y revise fechas de las fichas, perfiles de planta y carga docente.")
    elif saved and previous.get("workload_scope") != "lectiva":
        st.info("La ejecución guardada es anterior al cálculo solo lectivo. La vista previa excluye la etapa productiva; ejecute y guarde para actualizar su Excel.")
    preview, staff, problem = None, None, None
    with settings:
        year, targets, rules, offers = virtual_parameters(previous)
        for error in rules.validate():
            st.error(error)
        draft = manual_schedule_inputs(catalog, previous)
        if draft and ready and not rules.validate():
            try:
                staff, preview = execute_virtual_schedule_plan(catalog, **draft, rules=rules, targets=targets, year=year, offers=offers)
            except ValueError as exc:
                problem = str(exc)
                st.warning(problem)
        render_system_reset(path)
    with planning:
        if preview:
            render_virtual_summary(preview)
        else:
            st.info(problem or "Cargue los cronogramas, clasifique las actividades y complete los datos manuales para obtener la planeación.")
        current = {key: value for key, value in previous.items() if key != "saved_at"}
        pending = preview is None or json.dumps(preview, sort_keys=True) != json.dumps(current, sort_keys=True)
        if pending and preview:
            st.caption("Vista previa. Ejecute y guarde para actualizar la planeación y su descarga.")
        c1, c2 = st.columns(2)
        if c1.button("Ejecutar y guardar planeación", type="primary", disabled=preview is None):
            try:
                save_planning(path, staff, preview)
                saved = load_planning(path)
                pending = False
                st.success("Planeación virtual guardada.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f"No fue posible guardar: {exc}")
        downloadable = saved is not None and not pending
        c2.download_button("Descargar planeación guardada en Excel", data=export_planning(*saved) if downloadable else b"",
                           file_name=f"planeacion_titulada_virtual_{year}.xlsx", disabled=not downloadable,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if preview:
            render_virtual_details(preview)
        if saved and pending:
            with st.expander("Descargar la ejecución anterior"):
                st.caption(f"Guardada (UTC): {saved[1]['saved_at']} · Vigencia {saved[1]['planning_year']}.")
                st.download_button("Descargar Excel anterior", data=export_planning(*saved), file_name=f"planeacion_virtual_anterior_{saved[1]['planning_year']}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
