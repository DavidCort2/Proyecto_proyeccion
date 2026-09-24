"""Carga de cronogramas y clasificación técnica/transversal de sus actividades."""
from hashlib import sha256
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.virtual_schedule import is_lective_activity, lective_activities, parse_virtual_schedule
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules, save_virtual_activity_settings
from core.virtual_schedule_planner import staff_options, virtual_schedule_templates
from ui.curriculum_input import resettable_upload_key
from ui.planning_session import module_file_uploader, scoped_key, widget_key


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def schedule_inputs(path):
    catalog = load_virtual_schedules(path)
    st.subheader("Cronogramas de programas virtuales")
    st.caption("Cargue el Cronograma General en Excel: fases, actividades del proyecto, actividades de aprendizaje, horas estimadas y fechas. Se leen las celdas combinadas. El programa se identifica dentro del archivo.")
    files = module_file_uploader("Cronogramas virtuales (.xlsx)", type=["xlsx"], accept_multiple_files=True,
                                 key=resettable_upload_key("schedules_upload"))
    ready = True
    if files:
        try:
            payload = [(item.name, item.getvalue()) for item in files]
            parsed = [parse_virtual_schedule(content, name) for name, content in payload]
            known = {item["program_key"]: item["source_digest"] for item in catalog["schedules"]}
            ready = all(known.get(item["program_key"]) == item["source_digest"] for item in parsed)
            st.dataframe(pd.DataFrame([{"Programa": item["program"], "Actividades lectivas": len(lective_activities(item)),
                                        "Inicio de referencia": item["reference_start"], "Fin de referencia": item["reference_end"]} for item in parsed]),
                         hide_index=True, use_container_width=True)
            if st.button("Importar y guardar cronogramas", disabled=ready, type="primary"):
                catalog = import_virtual_schedules(path, payload)
                ready = True
                st.success("Cronogramas guardados. Revise la clasificación y la carga docente de las actividades.")
            elif not ready:
                st.info("Guarde los cronogramas cargados para utilizarlos en la planeación.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
            ready = False
    if not catalog["schedules"]:
        st.info("Cargue al menos un cronograma para comenzar.")
        return catalog, False
    st.caption("Solo se planean horas de etapa lectiva. La etapa productiva y su seguimiento se conservan como referencia del archivo, pero no suman horas ni generan contratación. Ingrese las horas totales de instructor por actividad lectiva y ficha; use 0 explícito donde no corresponda carga docente.")
    for item in catalog["schedules"]:
        with st.expander(item["program"], expanded=len(catalog["schedules"]) == 1):
            for warning in item["warnings"]:
                st.warning(warning)
            st.markdown("**Fases y actividades del proyecto**")
            st.dataframe(pd.DataFrame([{"Fase": row["phase"], "Actividad del proyecto": row["project_activity"],
                                        "Inicio": row["start"], "Fin": row["end"], "Horas estimadas del bloque": row["source_hours"],
                                        "Uso": "Etapa lectiva" if is_lective_activity(row) else "Excluida de la planeación"}
                                       for row in item["blocks"]]), hide_index=True, use_container_width=True)
            st.markdown("**Actividades lectivas: clasificación y horas de instructor**")
            activities = lective_activities(item)
            base = pd.DataFrame([{"Fase": row["phase"], "Competencia": row["competency"], "Resultado / actividad": row["activity"],
                                  "Tipo": row["teaching_type"], "Horas instructor por ficha": row["instructor_hours"]}
                                 for row in activities]).astype({"Horas instructor por ficha": "Float64"})
            edited = st.data_editor(base, hide_index=True, use_container_width=True,
                                    disabled=["Fase", "Competencia", "Resultado / actividad"],
                                    column_config={"Tipo": st.column_config.SelectboxColumn(options=["Técnico", "Transversal"]),
                                                   "Horas instructor por ficha": st.column_config.NumberColumn(min_value=0.0, step=0.5)},
                                    key=widget_key("schedule_activities_lectiva_" + digest(item)))
            settings = [{"id": original["id"], "teaching_type": values["Tipo"] if pd.notna(values["Tipo"]) else None,
                         "instructor_hours": float(values["Horas instructor por ficha"]) if pd.notna(values["Horas instructor por ficha"]) else None}
                        for original, values in zip(activities, edited.to_dict("records"))]
            changed = any(row["teaching_type"] != old["teaching_type"] or row["instructor_hours"] != old["instructor_hours"]
                          for row, old in zip(settings, activities))
            if st.button("Guardar clasificación y horas", key=scoped_key("save_schedule_" + item["program_key"]), disabled=not changed):
                try:
                    catalog = save_virtual_activity_settings(path, item["program_key"], item["source_digest"], settings)
                    changed = False
                    st.success("Clasificación y horas guardadas.")
                except (ValueError, OSError, sqlite3.Error) as exc:
                    st.error(str(exc))
            if changed:
                ready = False
                st.info("Guarde la clasificación y las horas para aplicarlas al cálculo.")
    return catalog, ready


def manual_schedule_inputs(catalog, previous):
    if not catalog["schedules"]:
        return None
    signature = digest(catalog)
    key = scoped_key("schedule_manual_base")
    if st.session_state.get(scoped_key("schedule_manual_digest")) != signature:
        prior = st.session_state.get(scoped_key("schedule_manual_draft"))
        st.session_state[key] = virtual_schedule_templates(catalog, {"virtual_inputs": prior} if prior else previous)
        st.session_state[scoped_key("schedule_manual_digest")] = signature
        st.session_state[scoped_key("schedule_manual_revision")] = st.session_state.get(scoped_key("schedule_manual_revision"), 0) + 1
    revision = str(st.session_state[scoped_key("schedule_manual_revision")])
    programs, cohorts, plant = st.session_state[key]
    st.subheader("Programas a planear")
    st.caption("Seleccione el nivel y la participación de cada programa en las fichas nuevas. Con pesos iguales se reparten por igual dentro del nivel.")
    programs = st.data_editor(pd.DataFrame(programs), hide_index=True, use_container_width=True, disabled=["Programa"],
                             column_config={"Incluir": st.column_config.CheckboxColumn(required=True),
                                            "Nivel": st.column_config.SelectboxColumn(options=["Técnico", "Tecnólogo"], required=True),
                                            "Peso de oferta": st.column_config.NumberColumn(min_value=1, step=1, required=True)},
                             key=widget_key("virtual_programs_" + revision))
    st.subheader("Fichas que pasan")
    st.caption("Registre la cantidad y la fecha de inicio de cada grupo. Las fases pendientes se calculan con las fechas del cronograma; grupos con fechas de inicio distintas van en filas separadas. Deje la tabla vacía si no hay continuaciones.")
    frame = pd.DataFrame(cohorts, columns=["Programa", "Fichas que pasan", "Fecha inicio formación"])
    frame = frame.astype({"Fichas que pasan": "Int64"})
    frame["Fecha inicio formación"] = pd.to_datetime(frame["Fecha inicio formación"])
    cohorts = st.data_editor(frame, num_rows="dynamic", hide_index=True, use_container_width=True,
                            column_config={"Programa": st.column_config.SelectboxColumn(options=programs["Programa"].tolist(), required=True),
                                           "Fichas que pasan": st.column_config.NumberColumn(min_value=1, step=1, required=True),
                                           "Fecha inicio formación": st.column_config.DateColumn(format="DD/MM/YYYY", required=True)},
                            key=widget_key("virtual_cohorts_" + revision))
    st.subheader("Instructores de planta")
    st.caption("Elija Técnico y el programa que atiende, o Transversal y su código de competencia. La capacidad transversal se comparte entre programas que usan esa competencia. Deje vacío si no hay planta.")
    options = staff_options(catalog)
    frame = pd.DataFrame(plant, columns=["Tipo", "Perfil", "Instructores de planta"]).astype({"Instructores de planta": "Int64"})
    plant = st.data_editor(frame, num_rows="dynamic", hide_index=True, use_container_width=True,
                          column_config={"Tipo": st.column_config.SelectboxColumn(options=["Técnico", "Transversal"], required=True),
                                         "Perfil": st.column_config.SelectboxColumn(options=options["Técnico"] + options["Transversal"], required=True),
                                         "Instructores de planta": st.column_config.NumberColumn(min_value=0, step=1, required=True)},
                          key=widget_key("virtual_plant_" + revision))
    cohort_rows = cohorts.to_dict("records")
    for row in cohort_rows:
        value = row["Fecha inicio formación"]
        row["Fecha inicio formación"] = value.date().isoformat() if pd.notna(value) else None
    draft = {"programs": programs.to_dict("records"), "cohorts": cohort_rows, "plant": plant.to_dict("records")}
    st.session_state[scoped_key("schedule_manual_draft")] = draft
    return draft
