import pandas as pd
import streamlit as st
from hashlib import sha256
import json

from core.transversal_capacity import current_transversal_capacity, suggested_continuity, validate_continuity
from core.transversal_modules import MODULE_KEYS, HOUR_COLUMNS, CONTINUING_KEYS, module_template, validate_modules, continuing_template
from core.level_planner import MANUAL_COLUMNS


def transversal_inputs(instructors, rules, previous, digest, year):
    with st.expander("Capacidad y continuidad de bilingüismo e integralidad", expanded=True):
        st.dataframe(current_transversal_capacity(instructors, rules), hide_index=True, use_container_width=True)
        st.caption("El reporte muestra horas programadas, no la jornada máxima disponible. La capacidad usa las horas de planta y contratista de los parámetros. Las horas libres actuales no fijan la demanda del próximo año.")
        base = suggested_continuity(instructors, rules)
        if previous.get("source_digest") == digest and previous.get("planning_year") == year and previous.get("transversal_continuity"):
            base = pd.DataFrame(previous["transversal_continuity"])
            base["Horas por contratista (h/sem)"] = base["Horas por contratista (h/sem)"].clip(upper=rules.weekly_contractor_hours)
        st.caption("Escenario inicial: conservar los contratistas del reporte. Revise cuántos prevé conservar y sus horas disponibles en cada trimestre; use 0 si no continuarán. Esta previsión no garantiza la renovación. Solo se propone personal adicional por las horas que esta capacidad no cubre.")
        edited = st.data_editor(base, hide_index=True, use_container_width=True,
                                disabled=["Área", "Trimestre"],
                                column_config={"Contratistas a conservar": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                                               "Horas por contratista (h/sem)": st.column_config.NumberColumn(min_value=0.0, max_value=float(rules.weekly_contractor_hours), required=True)},
                                key=f"transversal_editor_{digest}_{year}_{rules.weekly_contractor_hours}")
        return validate_continuity(edited, instructors, rules)


def module_inputs(manual, endings, rules, previous, imported, digest, year):
    st.markdown("**Módulos de bilingüismo e integralidad**")
    st.caption("Registre horas POR FICHA en cada trimestre de formación, no horas semanales. Use 0 cuando no corresponda impartir el módulo. La configuración aplica a las especialidades del mismo nivel y jornada; las horas restantes de las 30/26 semanales se asignan a formación técnica.")
    base = module_template(manual)
    if previous.get("transversal_modules"):
        saved = pd.DataFrame(previous["transversal_modules"])
        base = base.drop(columns=HOUR_COLUMNS).merge(saved, on=MODULE_KEYS, how="left", validate="one_to_one")
    module_key = sha256((digest + str(year) + base[MODULE_KEYS].to_json()).encode()).hexdigest()
    modules = st.data_editor(base, hide_index=True, use_container_width=True, disabled=MODULE_KEYS,
                             column_config={column: st.column_config.NumberColumn(min_value=0.0, required=True) for column in HOUR_COLUMNS},
                             key=f"modules_editor_{module_key}")
    modules = validate_modules(modules, manual, rules)
    base_hours = continuing_template(manual, endings, modules, imported, year)
    if (previous.get("source_digest") == digest and previous.get("planning_year") == year
            and previous.get("ficha_import") == imported
            and previous.get("transversal_modules") == modules.to_dict("records")
            and previous.get("quarter_endings") == endings.to_dict("records")
            and pd.DataFrame(previous["distribution"])[MANUAL_COLUMNS].to_dict("records") == manual.to_dict("records")
            and previous.get("continuing_transversal_hours")):
        base_hours = pd.DataFrame(previous["continuing_transversal_hours"])
    context = json.dumps([digest, year, manual.to_dict("records"), endings.to_dict("records"), modules.to_dict("records")], sort_keys=True)
    key = sha256(context.encode()).hexdigest()
    with st.expander("Horas transversales pendientes de las fichas que pasan", expanded=base_hours[HOUR_COLUMNS].isna().any().any()):
        st.caption("El reporte de fichas permite ubicar los módulos pendientes. Si las cantidades o las terminaciones fueron corregidas y ya no coinciden, complete las horas pendientes TOTALES de esas continuaciones en cada trimestre. No se vuelven a cobrar módulos ya completados. Cambiar módulos, continuaciones o terminaciones recalcula esta propuesta.")
        continuing = st.data_editor(base_hours, hide_index=True, use_container_width=True, disabled=CONTINUING_KEYS,
                                    column_config={column: st.column_config.NumberColumn(min_value=0.0, required=True) for column in HOUR_COLUMNS},
                                    key=f"continuing_hours_editor_{key}")
    return modules, continuing
