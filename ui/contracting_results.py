"""Resumen de necesidades, picos y períodos de contratación."""
import pandas as pd
import streamlit as st


def render_contracting(execution):
    st.markdown("**Contratación total y duración de la necesidad**")
    st.caption(execution["contracting_basis"])
    summary = execution["summary"]
    columns = st.columns(3)
    for column, key, label in zip(columns, ("total", "tecnico", "transversal"),
                                   ("Pico total de contratistas", "Pico de contratistas técnicos", "Pico de contratistas transversales")):
        quarters = ", ".join(f"T{q}" for q in summary[f"trimestres_pico_{key}"]) or "Sin contratación"
        column.metric(label, summary[f"pico_contratistas_{key}"])
        column.caption(quarters)
    st.dataframe(pd.DataFrame(execution["contracting_quarterly"]), hide_index=True, use_container_width=True)
    chart = pd.DataFrame(execution["contracting_quarterly"]).set_index("Trimestre")
    st.bar_chart(chart[["Contratistas técnicos", "Contratistas transversales"]])
    st.caption("La necesidad cambia cuando las fichas avanzan a otras competencias, terminan o ingresan en una nueva oferta. Menos ingresos no implica siempre menos fichas activas ni menos horas.")
    st.markdown("**Cuántos contratar y hasta cuándo**")
    if execution["contract_windows"]:
        st.dataframe(pd.DataFrame(execution["contract_windows"]), hide_index=True, use_container_width=True)
    else:
        st.info("La planta cubre todas las horas de la vigencia; no se requieren contratistas.")
    st.caption(execution["contracting_periods_basis"])
    st.caption("Los períodos que llegan a diciembre cubren el cierre de esta vigencia; la continuidad del siguiente año se recalcula con sus fichas y mallas.")
    with st.expander("Picos por perfil y exceso si se mantienen durante todo el año"):
        st.dataframe(pd.DataFrame(execution["contracting_profiles"]), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["contracting_profile_quarterly"]), hide_index=True, use_container_width=True)
