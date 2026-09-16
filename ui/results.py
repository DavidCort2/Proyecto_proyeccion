import pandas as pd
import streamlit as st

from core.export import export_planning


def render_results(instructors: pd.DataFrame, execution: dict) -> None:
    st.subheader(f"Última ejecución guardada · Vigencia {execution['planning_year']}")
    st.caption(f"Archivo: {execution['source_name']} · Guardado (UTC): {execution['saved_at']} · Base de datos: data/planeacion.sqlite3")
    center, summary = execution["center"], execution["summary"]
    columns = st.columns(4)
    columns[0].metric("Fichas nuevas", center["fichas_nuevas"])
    columns[1].metric("Fichas que pasan", center["fichas_que_pasan"])
    columns[2].metric("Instructores de planta", int(instructors["Es planta"].sum()))
    columns[3].metric("Contratistas requeridos", summary["contratistas_totales"])

    summary_tab, technical_tab, transversal_tab, data_tab = st.tabs(
        ["Resumen", "Especialidades técnicas", "Bilingüismo e integralidad", "Datos guardados"]
    )
    technical = pd.DataFrame(execution["technical"])
    transversal = pd.DataFrame(execution["transversal"])
    with summary_tab:
        st.write(
            f"Para una meta de **{center['meta_aprendices']} aprendices** y **{center['fichas_activas']} fichas activas**, "
            f"se requieren **{summary['contratistas_tecnicos']} contratistas técnicos** y "
            f"**{summary['contratistas_transversales']} transversales**."
        )
        st.dataframe(pd.DataFrame([
            {"Componente": "Técnico", "Déficit (h/sem)": summary["deficit_tecnico_horas_semana"], "Contratistas": summary["contratistas_tecnicos"]},
            {"Componente": "Transversal", "Déficit (h/sem)": summary["deficit_transversal_horas_semana"], "Contratistas": summary["contratistas_transversales"]},
        ]), hide_index=True, use_container_width=True)
        st.caption(
            f"El reporte contiene {int((~instructors['Es planta']).sum())} registros de contratistas actuales. "
            "Se conservan como referencia y no se descuentan de la necesidad proyectada."
        )
    with technical_tab:
        st.dataframe(technical, hide_index=True, use_container_width=True)
        if not technical.empty:
            st.bar_chart(technical.set_index("Especialidad")[["Capacidad planta (h/sem)", "Demanda técnica (h/sem)"]])
    with transversal_tab:
        st.dataframe(transversal, hide_index=True, use_container_width=True)
    with data_tab:
        st.markdown("**Especialidades registradas**")
        st.dataframe(pd.DataFrame(instructors.attrs.get("specialties", [])), hide_index=True, use_container_width=True)
        st.markdown("**Instructores de planta con nombre**")
        st.dataframe(instructors.loc[instructors["Es planta"], ["Área", "Especialidad", "Nombre", "Documento", "Horas programadas actuales"]], hide_index=True, use_container_width=True)
        st.markdown("**Capacidad por especialidad**")
        st.dataframe(pd.DataFrame(execution["resources"]), hide_index=True, use_container_width=True)

    with st.expander("Reglas y metodología de esta ejecución"):
        rules = execution["rules"]
        st.write(
            f"Fichas nuevas = meta / {rules['learners_per_ficha']} aprendices, redondeando hacia arriba. "
            f"Cada ficha activa demanda {rules['weekly_hours_per_ficha']:g} h/semana: "
            f"{rules['weekly_bilingual_hours']:g} de bilingüismo y {rules['weekly_integrality_hours']:g} de integralidad; "
            "las horas restantes son técnicas."
        )
        st.write(
            f"Cada instructor de planta aporta {rules['weekly_plant_direct_hours']:g} h/semana. "
            "Por especialidad, déficit = máximo(demanda − capacidad de planta, 0). "
            f"Contratistas = déficit / {rules['weekly_contractor_hours']:g}, redondeando hacia arriba por perfil. "
            "Bilingüismo e integralidad se calculan sobre todas las fichas activas."
        )
        st.caption("La distribución sugerida es proporcional a la planta técnica disponible. Debe ajustarse a la oferta real del centro.")
    st.download_button(
        "Descargar planeación guardada en Excel", data=export_planning(instructors, execution),
        file_name=f"planeacion_indicativa_{execution['planning_year']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
