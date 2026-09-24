"""Carga de mallas y clasificación única, sin transcripción de horas."""
from collections import defaultdict
import copy
import sqlite3

import pandas as pd
import streamlit as st

from core.curriculum import catalog_digest, curriculum_key, parse_curriculum
from core.curriculum_store import import_curricula, load_curricula, save_competencies
from ui.planning_session import module_file_uploader, scoped_key, widget_key


def resettable_upload_key(name):
    revision = st.session_state.get(scoped_key("_database_reset_version"), 0)
    return scoped_key(f"{name}_reset_{revision}" if revision else name)


def curriculum_inputs(path, *, virtual=False):
    catalog = load_curricula(path)
    st.subheader("Mallas curriculares")
    st.caption("Cargue uno o varios archivos " + ("PROGRAMA - VIRTUAL.xlsx" if virtual else "PROGRAMA - JORNADA.xlsx")
               + ". Se guardan todos los resultados y sus horas por trimestre. Una nueva versión reemplaza solo la malla del mismo programa y jornada en esta modalidad.")
    uploaded = module_file_uploader("Trimestralizaciones virtuales (.xlsx)" if virtual else "Mallas curriculares (.xlsx)",
                                   type=["xlsx"], accept_multiple_files=True, key=resettable_upload_key("curricula_upload"))
    ready = True
    if uploaded:
        files = [(item.name, item.getvalue()) for item in uploaded]
        try:
            parsed = [parse_curriculum(content, name) for name, content in files]
            allowed = {"Virtual"} if virtual else {"Diurna", "Mixta"}
            if any(item["schedule"] not in allowed for item in parsed):
                raise ValueError("Las mallas deben corresponder a Titulada " + ("virtual (PROGRAMA - VIRTUAL.xlsx)." if virtual else "presencial (Diurna o Mixta)."))
            seen = {}
            for item in parsed:
                key = curriculum_key(item["program"], item["schedule"])
                if key in seen and seen[key] != item["source_digest"]:
                    raise ValueError(f"Hay dos versiones de {item['program']} · {item['schedule']} en la misma carga.")
                seen[key] = item["source_digest"]
            st.dataframe(pd.DataFrame([{"Programa": item["program"], "Jornada": item["schedule"],
                                       "Trimestres": item["duration"], "Resultados": len(item["outcomes"])} for item in parsed]),
                         hide_index=True, use_container_width=True)
            persisted = {curriculum_key(item["program"], item["schedule"]): item["source_digest"] for item in catalog["curricula"]}
            ready = all(persisted.get(key) == digest for key, digest in seen.items())
            if st.button("Digitalizar y guardar mallas", type="primary", disabled=ready):
                catalog = import_curricula(path, files)
                ready = True
                st.success("Mallas guardadas. Se conservaron las clasificaciones existentes.")
            elif not ready:
                st.info("Guarde estas mallas para utilizarlas en la planeación.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
            ready = False
    if not catalog["curricula"]:
        st.info("Todavía no hay mallas guardadas. Puede cargarlas antes de los reportes de instructores y fichas.")
        return catalog, False

    hours = []
    occurrences = defaultdict(set)
    for item in catalog["curricula"]:
        totals = defaultdict(float)
        for outcome in item["outcomes"]:
            totals[outcome["quarter"]] += outcome["weekly_hours"]
            occurrences[outcome["competency_key"]].add((item["program"], item["schedule"]))
        hours.extend({"Programa": item["program"], "Jornada": item["schedule"], "Trimestre de formación": q,
                      "Horas semanales por ficha": total} for q, total in sorted(totals.items()))
    st.write(f"**{len(catalog['curricula'])} mallas guardadas · {len(catalog['competencies'])} competencias únicas**")
    with st.expander("Consultar horas y resultados digitalizados"):
        st.dataframe(pd.DataFrame(hours), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame([{"Programa": item["program"], "Jornada": item["schedule"],
                                   "Trimestre": row["quarter"], "Competencia": row["competency"],
                                   "Nombre original en Excel": row.get("source_competency", row["competency"]),
                                   "Resultado": row["result"], "Horas semanales": row["weekly_hours"],
                                   "Tipo en Excel": row["source_type"]}
                                  for item in catalog["curricula"] for row in item["outcomes"]]),
                     hide_index=True, use_container_width=True)
    st.markdown("**Todas las competencias · clasificación compartida entre programas y jornadas**")
    st.caption("La clasificación se propone automáticamente según las mallas. Puede corregir Transversal y su área; sus cambios se conservan al volver a cargar archivos. Los títulos equivalentes comparten una sola competencia y mantienen todos sus resultados y horas.")
    base = pd.DataFrame([{"Competencia": row["name"], "Transversal": row["transversal"],
                          "Área transversal": row["transversal_area"], "Mallas": len(occurrences[row["key"]])}
                         for row in catalog["competencies"]])
    edited = st.data_editor(base, hide_index=True, use_container_width=True,
                            disabled=["Competencia", "Mallas"],
                            column_config={"Transversal": st.column_config.CheckboxColumn(default=False),
                                           "Área transversal": st.column_config.SelectboxColumn(options=["Bilingüismo", "Integralidad"], required=True)},
                            key=widget_key(f"competencies_editor_{catalog_digest(catalog)}"))
    draft = copy.deepcopy(catalog)
    for row, values in zip(draft["competencies"], edited.to_dict("records")):
        row["transversal"], row["transversal_area"] = bool(values["Transversal"]), values["Área transversal"]
    changed = draft != catalog
    if st.button("Guardar clasificación de competencias", disabled=not changed):
        try:
            save_competencies(path, draft["competencies"])
            catalog = load_curricula(path)
            changed = False
            st.success("Clasificación guardada para todas las mallas.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            st.error(str(exc))
    if changed:
        st.info("Guarde la clasificación para aplicarla a la siguiente planeación.")
    return catalog, ready and not changed
