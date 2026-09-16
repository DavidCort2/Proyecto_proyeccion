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
    columns[3].metric("Pico de contratistas" if "calendar" in execution else "Contratistas requeridos", summary["contratistas_totales"])

    summary_tab, technical_tab, transversal_tab, data_tab = st.tabs(
        ["Resumen", "Especialidades técnicas", "Bilingüismo e integralidad", "Datos guardados"]
    )
    technical = pd.DataFrame(execution["technical"])
    transversal = pd.DataFrame(execution["transversal"])
    with summary_tab:
        if "levels" in execution:
            st.dataframe(pd.DataFrame(execution["levels"]), hide_index=True, use_container_width=True)
            if "calendar" in execution:
                st.write(f"**Total anual: {center['demanda_total_horas_anuales']:g} horas**, incluidas {center['demanda_nuevas_horas_anuales']:g} de nuevas fichas. Pico semanal: {center['demanda_total_horas_semana']:g} horas.")
                st.dataframe(pd.DataFrame(execution["quarterly"]), hide_index=True, use_container_width=True)
                st.caption(f"Pico simultáneo de contratación en T{summary['trimestre_pico_contratacion']}. Las terminaciones de T4 generan {center['reposiciones_siguiente_vigencia']} reposiciones para la siguiente vigencia.")
            else:
                st.write(
                    f"**Horas requeridas: {center['demanda_total_horas_semana']:g} h/semana**, "
                    f"de las cuales {center['demanda_tecnica_horas_semana']:g} son técnicas, "
                    f"{center['demanda_bilinguismo_horas_semana']:g} de bilingüismo y "
                    f"{center['demanda_integralidad_horas_semana']:g} de integralidad. "
                    f"Las nuevas fichas representan {center['demanda_nuevas_horas_semana']:g} h/semana."
                )
        if "growth_rule" in execution:
            st.write(
                f"Meta ingresada: **{center['meta_aprendices']} aprendices → {center['fichas_segun_meta']} fichas**. "
                f"Proyección: **{center['fichas_nuevas']} fichas nuevas → {center['aprendices_proyectados']} cupos**."
            )
            if center["fichas_adicionales_sobre_meta"]:
                st.info(f"Se requieren {center['fichas_adicionales_sobre_meta']} fichas por encima de la meta para cubrir reposiciones y el crecimiento mínimo del 5 %.")
        if "calendar" in execution:
            st.write(f"En T{summary['trimestre_pico_contratacion']}, el pico simultáneo requiere **{summary['contratistas_tecnicos']} contratistas técnicos** y **{summary['contratistas_transversales']} transversales**. El déficit anual suma **{summary['horas_a_contratar_anuales']:g} horas**; revise las horas a contratar de cada trimestre para ajustar la dedicación.")
        else:
            st.write(
                f"Para una meta de **{center['meta_aprendices']} aprendices** y **{center['fichas_activas']} fichas atendidas en la vigencia**, "
                f"se requieren **{summary['contratistas_tecnicos']} contratistas técnicos** y "
                f"**{summary['contratistas_transversales']} transversales**."
            )
        if "fichas_al_cierre" in center:
            st.write(f"De las fichas que pasan, **{center['fichas_que_terminan']} terminan** durante la vigencia. Se proyectan **{center['fichas_al_cierre']} fichas que continúan después del cierre**.")
        st.dataframe(pd.DataFrame([
            {"Componente": "Técnico", "Déficit (h/sem)": summary["deficit_tecnico_horas_semana"], "Contratistas": summary["contratistas_tecnicos"]},
            {"Componente": "Transversal", "Déficit (h/sem)": summary["deficit_transversal_horas_semana"], "Contratistas": summary["contratistas_transversales"]},
        ]), hide_index=True, use_container_width=True)
        st.caption(
            f"El reporte contiene {int((~instructors['Es planta']).sum())} registros de contratistas actuales. "
            "Se conservan como referencia y no se descuentan de la necesidad proyectada."
        )
    with technical_tab:
        if "hours" in execution:
            st.markdown("**Demanda por nivel y jornada**")
            st.dataframe(pd.DataFrame(execution["hours"]), hide_index=True, use_container_width=True)
            st.markdown("**Capacidad compartida de la planta por especialidad**")
            st.caption("Las 32 horas de cada instructor se usan una sola vez para todas las fichas de su especialidad. Dos fichas de 18 h técnicas demandan 36 h: una persona cubre 32 h y quedan 4 h de déficit.")
        st.dataframe(technical.rename(columns={"Fichas activas": "Fichas activas en el pico" if "calendar" in execution else "Fichas de la vigencia"}), hide_index=True, use_container_width=True)
        if "calendar" in execution:
            st.caption("La tabla anterior muestra el trimestre de mayor demanda de cada especialidad; sus picos pueden ocurrir en períodos diferentes.")
            st.markdown("**Atención y contratación por trimestre**")
            st.dataframe(pd.DataFrame(execution["technical_quarterly"]), hide_index=True, use_container_width=True)
            with st.expander("Calendario de ingresos, salidas y horas"):
                st.dataframe(pd.DataFrame(execution["calendar"]), hide_index=True, use_container_width=True)
        if "growth_rule" in execution:
            st.markdown("**Reposiciones y crecimiento mínimo por especialidad**")
            st.dataframe(pd.DataFrame(execution["growth_rule"]["rows"]), hide_index=True, use_container_width=True)
        if "growth_guide" in execution:
            st.markdown("**Guía de reposición y crecimiento usada como referencia**")
            st.dataframe(pd.DataFrame(execution["growth_guide"]["rows"]), hide_index=True, use_container_width=True)
        if not technical.empty:
            st.bar_chart(technical.set_index("Especialidad")[["Capacidad planta (h/sem)", "Demanda técnica (h/sem)"]])
    with transversal_tab:
        st.dataframe(pd.DataFrame(execution["transversal_quarterly"]) if "calendar" in execution else transversal, hide_index=True, use_container_width=True)
    with data_tab:
        if execution.get("ficha_import"):
            imported = execution["ficha_import"]
            st.markdown("**Reporte de fichas usado para las continuaciones**")
            st.caption(f"{imported['source_name']} · {imported['report_year']}, trimestre {imported['report_quarter']} · Proyección para {imported['planning_year']}. La distribución guardada incluye las correcciones manuales realizadas.")
            st.dataframe(pd.DataFrame(imported["detail"]), hide_index=True, use_container_width=True)
        st.markdown("**Especialidades registradas**")
        st.dataframe(pd.DataFrame(instructors.attrs.get("specialties", [])), hide_index=True, use_container_width=True)
        st.markdown("**Instructores de planta con nombre**")
        st.dataframe(instructors.loc[instructors["Es planta"], ["Área", "Especialidad", "Nombre", "Documento", "Horas programadas actuales"]], hide_index=True, use_container_width=True)
        st.markdown("**Capacidad por especialidad**")
        st.dataframe(pd.DataFrame(execution["resources"]), hide_index=True, use_container_width=True)

    with st.expander("Reglas y metodología de esta ejecución"):
        rules = execution["rules"]
        st.write(
            f"Fichas según la meta = meta / {rules['learners_per_ficha']} aprendices, redondeando hacia arriba. "
            f"Cada ficha diurna demanda {rules['weekly_hours_per_ficha']:g} h/semana: "
            f"{rules['weekly_bilingual_hours']:g} de bilingüismo y {rules['weekly_integrality_hours']:g} de integralidad; "
            "las horas restantes son técnicas."
        )
        if "levels" in execution:
            st.write(
                f"Cada ficha mixta demanda {rules['mixed_weekly_hours_per_ficha']:g} h/semana: "
                f"{rules['mixed_weekly_bilingual_hours']:g} de bilingüismo y "
                f"{rules['mixed_weekly_integrality_hours']:g} de integralidad; el resto es técnico. "
                "Las metas y sus redondeos se calculan por separado para Técnico y Tecnólogo."
            )
        st.write(
            f"Cada instructor de planta aporta {rules['weekly_plant_direct_hours']:g} h/semana. "
            "Por especialidad, déficit = máximo(demanda − capacidad de planta, 0). "
            f"Contratistas = déficit / {rules['weekly_contractor_hours']:g}, redondeando hacia arriba por perfil. "
            "Bilingüismo e integralidad se calculan sobre todas las fichas activas."
        )
        if execution.get("distribution_basis") == "quarterly_v1":
            st.caption(f"Año de cuatro trimestres con {rules['weeks_per_quarter']} semanas efectivas cada uno. Horas anuales = suma de horas semanales de las fichas activas en cada trimestre × semanas del trimestre. Ingresos al inicio y terminaciones al final del período. O&P/P&O es diurna de 10 trimestres; Técnico regular 3, Tecnólogo diurno 7 y mixto 9.")
            st.caption(f"Distribución de oferta adicional T1–T4: {rules['intake_weights']}. Las reposiciones ocurren al trimestre siguiente; las de T4 se reservan para la siguiente vigencia. Las nuevas técnicas de T1 terminan en T3 y se reemplazan en T4. La contratación se calcula sobre la demanda simultánea de cada trimestre, compartiendo la capacidad de planta por especialidad.")
        elif execution.get("distribution_basis") == "level_schedule_v1":
            st.caption("Se cubren reposiciones y crecimiento del 5 % por especialidad y nivel. Las nuevas se reparten entre jornadas según las continuaciones, reservando sus reposiciones. No se compensa una meta con la del otro nivel. La capacidad de planta se agrupa una sola vez por especialidad; las horas de las fichas se suman antes de calcular el déficit y redondear contratistas.")
            st.caption("Se presenta carga semanal de todas las fichas de la vigencia, no horas anuales ni un cronograma de atención simultánea. Para calcular esos valores harían falta semanas o fechas de operación.")
        elif execution.get("distribution_basis") == "automatic_growth_v1":
            st.caption("Nuevas mínimas por especialidad = fichas que terminan + techo(5 % de las fichas que pasan). Si la meta supera la suma de mínimos, el saldo se reparte proporcionalmente a las continuaciones (equitativamente si todas son cero). Si no alcanza, se supera la meta para cumplir todos los mínimos. Las horas y la contratación se calculan con las fichas realmente proyectadas.")
            st.caption("La demanda semanal conserva el modelo de carga de todas las fichas de la vigencia (nuevas + continuaciones). Sin fechas de inicio y fin no se estima la carga simultánea ni el pico de contratación.")
        elif execution.get("distribution_basis") == "manual_continuing":
            st.caption("Las fichas que pasan y las que terminan son cantidades manuales por especialidad. La sugerencia de nuevas prioriza reponer las que terminan y distribuye el resto según las que pasan. El crecimiento del 5 % al cierre es orientativo; la meta y la distribución se pueden ajustar.")
            st.caption("La demanda semanal mantiene el modelo de carga de todas las fichas de la vigencia (nuevas + continuaciones). No descuenta las terminaciones: sin fechas de inicio y fin no se puede determinar la carga simultánea ni el pico de contratación.")
        else:
            st.caption("Esta ejecución se guardó con la distribución anterior, proporcional a la planta técnica disponible.")
    st.download_button(
        "Descargar planeación guardada en Excel", data=export_planning(instructors, execution),
        file_name=f"planeacion_indicativa_{execution['planning_year']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
