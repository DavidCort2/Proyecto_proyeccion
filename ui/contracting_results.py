"""Resultados principales primero; trazabilidad y tablas bajo desplegables."""
import pandas as pd
import streamlit as st

from core.contracting_periods import contracting_headline, individual_contract_periods


def render_contracting_summary(execution):
    headline = contracting_headline(execution)
    with st.container(border=True):
        st.subheader(f"Contratación requerida · Vigencia {execution['planning_year']}")
        c1, c2 = st.columns(2)
        c1.metric("Total de contratistas requeridos", headline["Total de contratistas requeridos"])
        c2.metric("Trimestre del pico máximo", headline["Trimestre del pico máximo"])
        st.caption("El total indica la cantidad máxima de contratistas que se necesitan al mismo tiempo durante la vigencia.")
        c1, c2 = st.columns(2)
        c1.metric("Técnicos en el pico", headline["Técnicos en el pico"])
        c2.metric("Transversales en el pico", headline["Transversales en el pico"])
        quarter = headline["Trimestre del desglose"]
        if quarter:
            st.caption(f"Desglose de T{quarter}: técnicos + transversales = total requerido. Si el pico se repite, cada trimestre se puede consultar en el detalle.")
        else:
            st.info("La planta cubre todas las horas de la vigencia; no se requieren contratistas.")
        st.caption("Las horas se toman de las competencias de la malla que cursa cada ficha en cada trimestre. Se descuenta únicamente la cobertura de planta.")


def render_contracting_details(execution):
    with st.expander("Contratistas requeridos y fecha de finalización"):
        rows = individual_contract_periods(execution)
        if rows:
            frame = pd.DataFrame(rows).drop(columns="Instructor ID")
            for column in ("Requerido desde", "Requerido hasta"):
                frame[column] = pd.to_datetime(frame[column])
            st.dataframe(frame, hide_index=True, use_container_width=True, column_config={
                column: st.column_config.DateColumn(column, format="DD/MM/YYYY")
                for column in ("Requerido desde", "Requerido hasta")})
            st.caption("Cada fila identifica un cupo proyectado durante un período continuo. Puede haber más filas que el pico simultáneo cuando cambian los perfiles o hay períodos separados durante el año.")
        else:
            st.info("No hay contrataciones requeridas para esta vigencia.")
        st.caption("La fecha final corresponde a la necesidad dentro de esta vigencia. Los períodos que llegan a diciembre se evalúan de nuevo al planear el siguiente año.")
    with st.expander("Contratistas por trimestre y evolución del pico"):
        frame = pd.DataFrame(execution["contracting_quarterly"])
        st.dataframe(frame[["Trimestre", "Fichas activas", "Contratistas técnicos", "Contratistas transversales",
                            "Contratistas requeridos", "Contratos que inician", "Contratos que finalizan"]],
                     hide_index=True, use_container_width=True)
        chart = frame.assign(Trimestre=frame["Trimestre"].map(lambda q: f"T{q}")).set_index("Trimestre")
        st.bar_chart(chart[["Contratistas técnicos", "Contratistas transversales"]])
    with st.expander("Contratación agrupada por perfil y período"):
        st.dataframe(pd.DataFrame(execution["contract_windows"]), hide_index=True, use_container_width=True)
    with st.expander("Picos por perfil, reducciones y exceso de contratación"):
        st.caption(execution["contracting_periods_basis"])
        st.dataframe(pd.DataFrame(execution["contracting_profiles"]), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["contracting_profile_quarterly"]), hide_index=True, use_container_width=True)


def render_planning_details(execution, instructors):
    with st.expander("Demanda y contratación por mes"):
        st.caption(execution["monthly_basis"])
        st.dataframe(pd.DataFrame(execution["monthly"]), hide_index=True, use_container_width=True)
    with st.expander("Horas mensuales de cada ficha"):
        st.dataframe(pd.DataFrame(execution["monthly_fichas"]), hide_index=True, use_container_width=True)
    with st.expander("Capacidad mensual por perfil e instructor"):
        st.dataframe(pd.DataFrame(execution["monthly_staffing"]), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["monthly_instructors"]), hide_index=True, use_container_width=True)
    with st.expander("Distribución de horas entre instructores y fichas"):
        st.dataframe(pd.DataFrame(execution["monthly_assignments"]), hide_index=True, use_container_width=True)
    with st.expander("Ofertas, metas y fichas activas por programa"):
        if execution.get("intake_basis"):
            st.caption(execution["intake_basis"])
        st.dataframe(pd.DataFrame(execution["levels"]), hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["calendar"]), hide_index=True, use_container_width=True)
        center = execution["center"]
        if center["fichas_adicionales_sobre_meta"]:
            st.info(f"Las fichas que ya pasan superan la meta en {center['fichas_adicionales_sobre_meta']} fichas; sus horas pendientes se mantienen para completar su formación.")
        st.dataframe(pd.DataFrame(execution.get("intake_allocation", execution.get("growth_rule", {}).get("rows", []))), hide_index=True, use_container_width=True)
    with st.expander("Comprobar horas por competencia, trimestre y resultado"):
        st.dataframe(pd.DataFrame(execution["curriculum_hours"]), hide_index=True, use_container_width=True)
    with st.expander("Cobertura de planta"):
        st.dataframe(instructors.loc[instructors["Es planta"], ["Área", "Especialidad", "Nombre", "Documento"]],
                     hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["resources"]), hide_index=True, use_container_width=True)
    with st.expander("Reglas utilizadas en el cálculo"):
        st.caption(execution["monthly_basis"])
        st.caption(execution["contracting_periods_basis"])
        st.write(f"Planta: {execution['rules']['weekly_plant_direct_hours']:g} h/semana por instructor. "
                 f"Contratista: {execution['rules']['weekly_contractor_hours']:g} h/semana. "
                 "Contratistas requeridos = horas pendientes después de planta / capacidad por contratista, "
                 "redondeado hacia arriba por perfil y trimestre.")


def render_contracting(execution):
    render_contracting_summary(execution)
    render_contracting_details(execution)
