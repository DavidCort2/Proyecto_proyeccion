"""Resultados principales primero; trazabilidad y tablas bajo desplegables."""
import pandas as pd
import streamlit as st

from core.contracting_periods import contracting_headline, individual_contract_periods
from core.curriculum_intakes import OFFER_COLUMNS
from core.program_transitions import transition_rows


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
    if execution.get("plant_balance"):
        with st.expander("Descuento de horas de planta y saldo a contratar"):
            st.caption("Horas a contratar = horas requeridas − horas cubiertas por planta. "
                       "La capacidad corresponde a todos los instructores de planta del reporte y se cuenta una sola vez. "
                       "El saldo global resta toda esa capacidad; el saldo por perfil muestra las horas que quedan "
                       "al respetar las líneas compatibles y áreas docentes.")
            for field in ("plant_balance", "plant_balance_by_profile"):
                frame = pd.DataFrame(execution[field])
                st.dataframe(frame, hide_index=True, use_container_width=True,
                             column_config={name: st.column_config.NumberColumn(format="%.2f")
                                            for name in frame.columns if name.endswith("(h/sem)")})
            if execution.get("teaching_line_basis"):
                st.caption(execution["teaching_line_basis"])
            else:
                st.caption("Las horas libres de un perfil no se descuentan de otro. Los contratistas se redondean "
                           "hacia arriba por perfil y trimestre, usando su capacidad semanal configurada.")
    if "intake_decisions" in execution:
        levels = pd.DataFrame(execution["levels"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Aprendices de fichas que pasan", int(levels["Aprendices que pasan (estimados)"].sum()))
        c2.metric("Aprendices por matricular", int(levels["Aprendices pendientes de ingresar"].sum()))
        c3.metric("Fichas nuevas programadas" if execution.get("manual_offers") else "Fichas nuevas tras descontar continuaciones",
                  execution["center"]["fichas_nuevas"])
        st.caption(f"Las fichas que pasan aportan {execution['rules']['learners_per_ficha']} aprendices cada una, "
                   "igual que las nuevas. Se descuentan de la meta de su nivel una sola vez, aunque terminen durante el año. "
                   "Los reemplazos están incluidos dentro de las nuevas.")
        with st.expander("Descuento de las fichas que pasan en la meta"):
            columns = ["Nivel", "Meta de aprendices", "Fichas que pasan", "Aprendices que pasan (estimados)",
                       "Aprendices pendientes de ingresar", "Fichas nuevas"]
            if execution.get("manual_offers"):
                columns += ["Cupos proyectados", "Aprendices sin cobertura", "Aprendices sobre la meta"]
            st.dataframe(levels[columns],
                         hide_index=True, use_container_width=True)
        if execution.get("manual_offers"):
            center = execution["center"]
            st.caption("Se aplican las cantidades guardadas en la tabla de ofertas. La meta permanece como referencia para comparar los cupos programados.")
            if center["aprendices_sin_cobertura"]:
                st.warning(f"Las ofertas editadas dejan {center['aprendices_sin_cobertura']} aprendices sin cobertura de la meta. Consulte el desglose por nivel.")
            if center["aprendices_sobre_meta"]:
                st.info(f"Hay {center['aprendices_sobre_meta']} cupos por encima de la meta en los niveles con excedente. Consulte el desglose por nivel.")


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


def render_planning_details(execution, instructors, *, offer_editor=None):
    render_intake_offers(execution, editor=offer_editor)
    if execution.get("teaching_lines"):
        from core.teaching_lines import teaching_line_rows
        with st.expander("Programas compatibles y capacidad compartida"):
            st.caption(execution["teaching_line_basis"])
            st.dataframe(pd.DataFrame(teaching_line_rows(execution["teaching_lines"])), hide_index=True, use_container_width=True)
    if execution.get("program_transitions"):
        with st.expander("Programas actualizados y planta compartida"):
            st.caption(execution["program_transition_basis"])
            st.dataframe(pd.DataFrame(transition_rows(execution["program_transitions"])), hide_index=True, use_container_width=True)
    virtual = execution.get("input_mode") == "virtual_manual"
    with st.expander("Duración y terminación de las fichas manuales" if virtual else "Duración y terminación de las fichas del reporte"):
        if execution.get("duration_basis"):
            st.caption(execution["duration_basis"])
        st.dataframe(pd.DataFrame(execution["ficha_import"]["detail"]), hide_index=True, use_container_width=True)
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
        if center["fichas_adicionales_sobre_meta"] and not execution.get("manual_offers"):
            st.info(f"Las fichas que ya pasan superan la meta en {center['fichas_adicionales_sobre_meta']} fichas; sus horas pendientes se mantienen para completar su formación.")
        st.dataframe(pd.DataFrame(execution.get("intake_allocation", execution.get("growth_rule", {}).get("rows", []))), hide_index=True, use_container_width=True)
    with st.expander("Comprobar horas por competencia, trimestre y resultado"):
        st.dataframe(pd.DataFrame(execution["curriculum_hours"]), hide_index=True, use_container_width=True)
    with st.expander("Cobertura de planta"):
        if execution.get("program_transitions"):
            st.caption("El reporte conserva el nombre original del programa. La capacidad y la contratación se agrupan por el programa vigente indicado en «Programas actualizados y planta compartida».")
        if execution.get("plant_basis"):
            st.caption(execution["plant_basis"])
        st.dataframe(instructors.loc[instructors["Es planta"], ["Área", "Especialidad", "Nombre", "Documento"]],
                     hide_index=True, use_container_width=True)
        st.dataframe(pd.DataFrame(execution["resources"]), hide_index=True, use_container_width=True)
    with st.expander("Reglas utilizadas en el cálculo"):
        if execution.get("calculation_basis"):
            st.caption(execution["calculation_basis"])
            st.dataframe(pd.DataFrame(execution["calculation_parameters"]), hide_index=True, use_container_width=True)
        st.caption(execution["monthly_basis"])
        st.caption(execution["contracting_periods_basis"])
        st.write(f"Planta: {execution['rules']['weekly_plant_direct_hours']:g} h/semana por instructor. "
                 f"Contratista: {execution['rules']['weekly_contractor_hours']:g} h/semana. "
                 "Contratistas requeridos = horas pendientes después de planta / capacidad por contratista, "
                 "redondeado hacia arriba por perfil y trimestre.")


def render_intake_offers(execution, *, editor=None):
    if "offers_by_program" not in execution:
        return
    with st.expander("Fichas nuevas por programa y oferta"):
        st.caption(execution["offer_basis"])
        programs = pd.DataFrame(execution["offers_by_program"])
        st.write("**Ingresos proyectados por programa**")
        st.caption("T1: enero–marzo · T2: abril–junio · T3: julio–septiembre · T4: octubre–diciembre. Las fichas ingresan al inicio de cada oferta.")
        if editor is None:
            st.dataframe(programs, hide_index=True, use_container_width=True)
        else:
            editor(execution)
        st.dataframe(pd.DataFrame([{"Programa": "TOTAL", **programs[[*OFFER_COLUMNS, "Total anual"]].sum().to_dict()}]),
                     hide_index=True, use_container_width=True)
        st.write("**Detalle por jornada**")
        st.dataframe(pd.DataFrame(execution["offers_by_profile"]), hide_index=True, use_container_width=True)
        st.caption("Son cantidades de fichas nuevas por abrir; sus números oficiales se asignan al matricularlas. Las fichas que pasan se muestran en los otros detalles.")
        if "intake_decisions" in execution:
            st.write("**Reemplazos y prioridad de los programas**")
            st.dataframe(pd.DataFrame(execution["intake_decisions"]), hide_index=True, use_container_width=True)
            st.caption("Las cantidades manuales tienen prioridad. El criterio automático se conserva como referencia; los reemplazos contabilizados corresponden a ingresos posteriores a la terminación de las fichas que pasan."
                       if execution.get("manual_offers") else
                       "Solo reemplazos: cada ingreso corresponde a una ficha que pasa y termina antes de T4. "
                       "Las salidas de T4 se reponen el año siguiente. No se reabren vacantes de años anteriores. "
                       "Los demás ingresos se asignan a los programas identificados como populares.")


def render_contracting(execution):
    render_contracting_summary(execution)
    render_contracting_details(execution)
