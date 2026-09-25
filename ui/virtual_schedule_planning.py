"""Interfaz de Titulada virtual: cronogramas, perfiles y ofertas por fecha."""
from datetime import date
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.database import database_reset_version, load_planning, save_planning
from core.export import export_planning
from core.virtual_schedule_planner import WORKLOAD_MODEL, VirtualRules, execute_virtual_schedule_plan
from core.virtual_staffing_reports import contract_reports, profile_peak_rows, schedule_activity_rows
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
        st.caption("Carga técnica: 2 horas diarias por ficha, equivalentes a 10 semanales. Carga transversal: 2 horas semanales por ficha y competencia, únicamente durante los bloques donde está activa. Las fases y su duración provienen del cronograma.")
        capacity_rules = VirtualRules(weekly_plant_direct_hours=plant, weekly_contractor_hours=contractor)
        st.dataframe(pd.DataFrame([{"Tipo": kind, "Horas semanales por ficha": capacity_rules.weekly_hours_for(kind),
                                    "Cupos por contratista": int(contractor // capacity_rules.weekly_hours_for(kind)),
                                    "Cupos por planta": int(plant // capacity_rules.weekly_hours_for(kind))}
                                   for kind in ("Técnico", "Transversal")]), hide_index=True, use_container_width=True)
        st.caption("En técnico, un cupo atiende una ficha. En transversal, un cupo atiende una competencia de una ficha durante la semana: dos competencias activas suman dos cupos. Las sesiones transversales se distribuyen dentro de la jornada, hasta 8 horas diarias por contratista de 40 horas semanales.")
        columns = st.columns(4)
        weights = tuple(columns[i].number_input(f"Ingresos en oferta {i + 1} (%)", min_value=0, max_value=100,
                                                 value=int(defaults.get("intake_weights", [50, 25, 15, 10])[i]),
                                                 key=widget_key(f"intake_weight_{i}")) for i in range(4))
        st.caption("Las cuatro ofertas se proyectan automáticamente al inicio de enero, abril, julio y octubre. Son fechas indicativas. Los porcentajes deben sumar 100 %.")
    return year, targets, VirtualRules(int(learners), plant, contractor, weights)


def render_virtual_summary(plan):
    summary = plan["summary"]
    st.subheader(f"Contratación requerida · Vigencia {plan['planning_year']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de contratistas requeridos", summary["pico_contratistas_total"])
    c2.metric("Trimestre del pico", f"T{summary['trimestre_pico']}" if summary["pico_contratistas_total"] else "Sin contratación")
    c3.metric("Inicio del pico", summary['inicio_pico'] if summary["pico_contratistas_total"] else "—")
    c1, c2 = st.columns(2)
    c1.metric("Técnicos en el pico", summary["tecnicos_en_pico"])
    c2.metric("Transversales en el pico", summary["transversales_en_pico"])
    st.caption("Los técnicos y transversales mostrados corresponden al mismo intervalo. La contratación se calcula cuando cambian las actividades; un promedio mensual no oculta los picos de carga.")
    st.markdown("**Picos por perfil docente**")
    st.dataframe(pd.DataFrame(profile_peak_rows(plan["staffing"], plan["rules"])), hide_index=True, use_container_width=True)
    st.caption("Cada fila muestra el máximo simultáneo de ese perfil. Sus picos pueden ocurrir en fechas distintas: el total superior se obtiene comparando los intervalos, no sumando estos máximos. Una atención transversal es una competencia activa de una ficha; sus distintos resultados no multiplican las horas.")
    st.bar_chart(pd.DataFrame(plan["quarterly"]).set_index("Trimestre")[["Pico simultáneo de contratistas"]])


def render_virtual_details(plan):
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de horas al año", f"{plan['center']['demanda_total_horas_anuales']:g}")
    c2.metric("Fichas nuevas proyectadas", plan["center"]["fichas_nuevas"])
    c3.metric("Fichas que pasan", plan["center"]["fichas_que_pasan"])
    st.caption("El total corresponde únicamente a horas de instructor de etapa lectiva dentro de la vigencia. La etapa productiva y su seguimiento están excluidos.")
    slots, periods = contract_reports(plan["contracts"])
    tables = {**plan, "contract_slots": slots, "contract_periods": periods}
    for key, label in [("contract_slots", "Contratistas requeridos y fechas"),
                       ("contract_periods", "Detalle de períodos de contratación"), ("offers_by_program", "Fichas nuevas por programa y oferta"),
                       ("quarterly", "Necesidad y excedentes de contratistas por trimestre"),
                       ("cohort_dates", "Fechas y fases de las fichas"), ("levels", "Metas por nivel"),
                       ("periods", "Contratación por intervalos del cronograma"), ("monthly", "Resumen mensual"),
                       ("monthly_fichas", "Horas y fases de cada ficha por mes"),
                       ("monthly_instructors", "Capacidad y horas disponibles de cada instructor"),
                       ("monthly_assignments", "Asignación mensual de fichas a instructores"),
                       ("staffing", "Cobertura de planta por tipo y perfil"), ("activity_hours", "Horas por fase y competencia")]:
        with st.expander(label):
            if key == "contract_slots":
                st.caption("Cada cupo aparece una sola vez, con todos sus períodos y pausas. N.º de cupo es un identificador: cupo 2 significa el segundo instructor de ese perfil, no dos instructores por fila. La última fecha no implica contratación continua durante las pausas.")
            if key == "contract_periods":
                st.caption("Un mismo cupo puede tener varios períodos; no se suman como instructores adicionales. El 31 de diciembre es el límite de esta vigencia, no el fin lectivo de las fichas que continúan.")
            if key == "monthly_assignments":
                st.caption("Asignación indicativa por capacidad y perfil; las fichas nuevas se identifican con un consecutivo de proyección, no con un código oficial.")
            st.dataframe(pd.DataFrame(tables[key]), hide_index=True, use_container_width=True)
    with st.expander("Resultados del cronograma por perfil"):
        activities = pd.DataFrame(schedule_activity_rows(plan["schedule_catalog"]))
        profile = st.selectbox("Perfil docente a revisar", sorted(activities["Perfil"].unique()), key=widget_key("audit_profile"))
        st.caption("Estas son todas las actividades identificadas en los Excel para el perfil. El código de competencia las vincula aunque cambie su redacción; varias actividades de una competencia generan una sola carga por ficha mientras esté activa. Las fechas de cada cohorte se consultan en Horas por fase y competencia.")
        st.dataframe(activities[activities["Perfil"] == profile], hide_index=True, use_container_width=True)
    with st.expander("Criterios utilizados"):
        st.write(plan["calculation_basis"])


def render_virtual_schedule_planning(path):
    st.caption("Planeación de etapa lectiva por competencias y duración de las fases. Las fechas originales del cronograma y la etapa productiva se excluyen del cálculo.")
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
    if saved and previous.get("planning_mode") != "virtual_schedule_v3":
        st.warning("La ejecución anterior se conserva para descargarla. Para actualizarla cargue los cronogramas, indique las fechas de fin lectiva de las fichas que pasan y complete los nombres y cédulas de planta.")
    elif saved and previous.get("workload_scope") != "lectiva":
        st.info("La ejecución guardada es anterior al cálculo solo lectivo. La vista previa excluye la etapa productiva; ejecute y guarde para actualizar su Excel.")
    elif saved and previous.get("workload_model") != WORKLOAD_MODEL:
        st.info("La vista previa identifica Bilingüismo y Cultura física por sus códigos, con perfiles exclusivos. Cada competencia transversal activa aporta 2 horas semanales por ficha, sin multiplicar por sus resultados. Ejecute y guarde para actualizar los resultados y el Excel; sus fichas, fechas y planta se conservan.")
    preview, staff, problem = None, None, None
    with settings:
        year, targets, rules = virtual_parameters(previous)
        for error in rules.validate():
            st.error(error)
        draft = manual_schedule_inputs(catalog, previous)
        if draft and ready and not rules.validate():
            try:
                staff, preview = execute_virtual_schedule_plan(catalog, **draft, rules=rules, targets=targets, year=year)
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
