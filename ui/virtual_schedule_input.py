"""Carga de cronogramas y clasificación técnica/transversal de sus actividades."""
from hashlib import sha256
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.virtual_schedule import is_lective_activity, lective_activities, parse_virtual_schedule, require_program_template
from core.virtual_competencies import competency_rows
from core.virtual_schedule_store import import_virtual_schedules, load_virtual_schedules, save_virtual_competencies
from core.virtual_schedule_planner import staff_options, virtual_schedule_templates
from ui.curriculum_input import resettable_upload_key
from ui.planning_session import module_file_uploader, scoped_key, widget_key
from ui.virtual_cohort_input import continuing_ficha_inputs


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def schedule_inputs(path):
    catalog = load_virtual_schedules(path)
    st.subheader("Cronogramas de programas virtuales")
    st.caption("Cargue el Cronograma General en Excel. Se extraen competencias, fases y duraciones; las fechas de la ficha del archivo se ignoran. El programa se identifica dentro del documento.")
    files = module_file_uploader("Cronogramas virtuales (.xlsx)", type=["xlsx"], accept_multiple_files=True,
                                 key=resettable_upload_key("schedules_upload"))
    ready = True
    if files:
        try:
            payload = [(item.name, item.getvalue()) for item in files]
            parsed = [parse_virtual_schedule(content, name) for name, content in payload]
            known = {item["program_key"]: item["source_digest"] for item in catalog["schedules"]}
            versions = {item["program_key"]: item.get("schema_version") for item in catalog["schedules"]}
            ready = all(known.get(item["program_key"]) == item["source_digest"] and versions.get(item["program_key"]) == item["schema_version"] for item in parsed)
            st.dataframe(pd.DataFrame([{"Programa": item["program"], "Actividades lectivas": len(lective_activities(item)),
                                        "Duración lectiva": item["lective_duration"], "Unidad": item["duration_unit"]} for item in parsed]),
                         hide_index=True, use_container_width=True)
            if st.button("Importar y guardar cronogramas", disabled=ready, type="primary"):
                catalog = import_virtual_schedules(path, payload)
                ready = True
                st.success("Cronogramas guardados. Revise las competencias transversales sugeridas.")
            elif not ready:
                st.info("Guarde los cronogramas cargados para utilizarlos en la planeación.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
            ready = False
    if not catalog["schedules"]:
        st.info("Cargue al menos un cronograma para comenzar.")
        return catalog, False
    try:
        for item in catalog["schedules"]:
            require_program_template(item)
    except ValueError as exc:
        st.warning(str(exc))
        return catalog, False
    st.subheader("Clasificar competencias únicas")
    st.caption("En la columna Tipo puede elegir Técnico o Transversal para cada competencia y pulsar Guardar clasificación de competencias. La decisión se aplica a todas sus actividades y programas. Cada código aparece una sola vez; la carga se calcula solo en los bloques donde se cursa esa competencia.")
    st.caption("La clasificación inicial es una sugerencia del texto del Excel. Técnico comparte las 10 horas semanales del programa; cada competencia Transversal activa tiene 2 horas semanales por ficha.")
    st.caption("Según la configuración del centro, las transversales comparten el perfil Transversal general, excepto Bilingüismo y Cultura física. Estas dos competencias conservan su tipo Transversal y su perfil exclusivo por código, aunque los resultados se redacten distinto o no mencionen el idioma. Cultura física requiere un instructor de educación física. Puede corregir los demás perfiles. Las competencias del mismo perfil suman su carga dentro de una sola capacidad; este campo no modifica la carga técnica.")
    base = pd.DataFrame(competency_rows(catalog))
    edited = st.data_editor(base, hide_index=True, use_container_width=True,
                            disabled=["Competencia", "Actividad de referencia", "Programas", "Fases"],
                            column_config={"Tipo": st.column_config.SelectboxColumn(options=["Técnico", "Transversal"], required=True),
                                           "Perfil docente": st.column_config.TextColumn(required=True)},
                            key=widget_key("schedule_competencies_" + digest(catalog)))
    changed = not base.equals(edited)
    if st.button("Guardar clasificación de competencias", disabled=not changed, key=scoped_key("save_schedule_competencies")):
        try:
            catalog = save_virtual_competencies(path, {item["program_key"]: item["source_digest"] for item in catalog["schedules"]}, edited.to_dict("records"))
            changed = False
            st.success("Clasificación guardada para todas las fases y programas.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
    if changed:
        ready = False
        st.info("Guarde la clasificación para aplicarla al cálculo.")
    for item in catalog["schedules"]:
        with st.expander(item["program"], expanded=len(catalog["schedules"]) == 1):
            st.write(f"Duración lectiva: {item['lective_duration']:g} {item['duration_unit']}.")
            for warning in item["warnings"]:
                st.warning(warning)
            st.markdown("**Fases y actividades del proyecto**")
            st.dataframe(pd.DataFrame([{"Fase": row["phase"], "Actividad del proyecto": row["project_activity"],
                                        "Inicio relativo": row["start_offset"], "Duración": row["duration"], "Unidad": row["duration_unit"],
                                        "Uso": "Etapa lectiva" if is_lective_activity(row) else "Excluida de la planeación",
                                        "Notas de origen": " · ".join(note["text"] for note in row.get("source_notes", []))}
                                       for row in item["blocks"]]), hide_index=True, use_container_width=True)
            st.markdown("**Competencias y actividades de cada fase**")
            activities = lective_activities(item)
            base = pd.DataFrame([{"Fase": row["phase"], "Competencia": row["competency"], "Resultado / actividad": row["activity"],
                                  "Tipo": row["teaching_type"]} for row in activities])
            st.dataframe(base, hide_index=True, use_container_width=True)
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
    cohort_rows, added_fichas = continuing_ficha_inputs(programs["Programa"].tolist(), cohorts, revision)
    st.subheader("Instructores de planta")
    st.caption("Elija Técnico y su programa, o Transversal y el perfil docente configurado en las competencias. Un instructor de planta comparte su capacidad entre las competencias de ese perfil, sin contarse dos veces. Deje vacío si no hay planta.")
    options = staff_options(catalog)
    frame = pd.DataFrame(plant, columns=["Nombre completo", "Cédula", "Tipo", "Perfil"]).astype("string")
    plant = st.data_editor(frame, num_rows="dynamic", hide_index=True, use_container_width=True,
                          column_config={"Nombre completo": st.column_config.TextColumn(required=True),
                                         "Cédula": st.column_config.TextColumn(required=True),
                                         "Tipo": st.column_config.SelectboxColumn(options=["Técnico", "Transversal"], required=True),
                                         "Perfil": st.column_config.SelectboxColumn(options=options["Técnico"] + options["Transversal"], required=True)},
                          key=widget_key("virtual_plant_" + revision))
    draft = {"programs": programs.to_dict("records"), "cohorts": cohort_rows, "plant": plant.to_dict("records")}
    st.session_state[scoped_key("schedule_manual_draft")] = draft
    if added_fichas:
        st.rerun()
    return draft
