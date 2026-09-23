from __future__ import annotations

from dataclasses import asdict
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sqlite3
import json

import pandas as pd
import streamlit as st

from core.config import PlanningRules
from core.database import load_planning, save_planning
from core.excel_parser import parse_instructors_excel
from core.planner import (
    fichas_from_target,
    largest_remainder_allocation,
    technical_specialty_catalog,
)
from core.level_planner import MANUAL_COLUMNS, execute_level_plan, validate_profiles
from ui.results import render_results
from ui.ficha_input import ficha_inputs
from ui.calendar_input import calendar_inputs
from ui.transversal_input import transversal_inputs, module_inputs

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "planeacion.sqlite3"


@st.cache_data(show_spinner=False, max_entries=4)
def read_report(content: bytes) -> pd.DataFrame:
    return parse_instructors_excel(BytesIO(content))


def legacy_main() -> None:
    """Compatibilidad de la interfaz anterior para verificar ejecuciones históricas."""
    st.set_page_config(page_title="Planeación Indicativa SENA", page_icon="📊", layout="wide")
    st.title("Planeación Indicativa")
    st.caption("Centro de Formación SENA · Prepare los datos, distribuya las fichas y ejecute la planeación de la próxima vigencia.")
    try:
        saved = load_planning(DATABASE_PATH)
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"No fue posible abrir la base de datos: {exc}")
        st.stop()
    previous = saved[1] if saved else {}
    defaults = previous.get("rules", asdict(PlanningRules()))
    instructors = None
    source_name = source_digest = ""
    draft_valid = False
    continuing = 0
    ficha_import = None
    # La meta ingresada se conserva; la proyección puede superarla.
    st.session_state.pop("suggested_target", None)

    with st.container(border=True):
        st.subheader("1. Preparar la planeación")
        st.caption("Todos los datos se ingresan aquí. Al ejecutar se reemplazan la carga y los resultados anteriores; no se acumulan archivos.")
        options = ["Cargar un archivo Excel"]
        if saved:
            options.insert(0, "Usar datos guardados")
        if st.session_state.get("source_mode") not in options:
            st.session_state.source_mode = options[0]
        source_mode = st.radio("Origen de los instructores", options, key="source_mode", horizontal=True)
        content = None
        if source_mode == "Cargar un archivo Excel":
            uploaded = st.file_uploader("Reporte de instructores (.xlsx)", type=["xlsx"], key="report_upload")
            st.caption("Primera hoja: Nombre, Documento, Tipo Contrato y Total Horas, con las especialidades como títulos de sección.")
            if uploaded is not None:
                source_name, content = uploaded.name, uploaded.getvalue()
        elif saved:
            instructors = saved[0]
            source_name, source_digest = previous["source_name"], previous["source_digest"]
        if content is not None:
            source_digest = sha256(content).hexdigest()
            try:
                instructors = read_report(content)
            except Exception as exc:
                st.error(f"No fue posible leer el reporte: {exc}")

        if instructors is not None:
            st.info(
                f"{source_name} · {len(instructors.attrs.get('specialties', []))} especialidades · "
                f"{int(instructors['Es planta'].sum())} instructores de planta · "
                f"{int((~instructors['Es planta']).sum())} contratistas actuales."
            )
            with st.expander("Revisar los instructores del archivo antes de ejecutar"):
                st.dataframe(instructors, hide_index=True, use_container_width=True)
        else:
            st.info("Cargue un archivo válido o use los datos guardados para preparar la distribución.")

        c1, c2, c3 = st.columns(3)
        year = c1.number_input("Vigencia a planear", min_value=2000, max_value=2200, value=previous.get("planning_year", date.today().year + 1), step=1, key="planning_year")
        saved_targets = previous.get("targets_by_level", {})
        target_technical = c2.number_input("Meta de aprendices · Técnico", min_value=0, value=saved_targets.get("Técnico", previous.get("target_learners", 500)), step=25, key="target_technical")
        target_technologist = c3.number_input("Meta de aprendices · Tecnólogo", min_value=0, value=saved_targets.get("Tecnólogo", 0), step=25, key="target_technologist")
        targets = {"Técnico": int(target_technical), "Tecnólogo": int(target_technologist)}
        target = sum(targets.values())
        demand_labels = ["Por módulos (horas por trimestre de formación)", "Semanal uniforme (escenario de referencia)"]
        demand_model = st.radio("Cálculo de bilingüismo e integralidad", demand_labels,
                                index=1 if previous.get("transversal_demand_model") == "weekly" else 0, key="transversal_demand_model")
        modular = demand_model == demand_labels[0]
        if modular:
            st.caption("La demanda transversal se obtiene de los módulos y horas pendientes, no de multiplicar todas las fichas por una carga semanal fija.")
        if previous and not saved_targets:
            st.info("La meta anterior no distinguía niveles. Se muestra inicialmente en Técnico; redistribúyala entre Técnico y Tecnólogo y clasifique las filas antes de ejecutar.")
        with st.expander("Parámetros de cálculo", expanded=True):
            if modular:
                st.caption("Los campos semanales de bilingüismo e integralidad se conservan como referencia del escenario uniforme. En este cálculo por módulos se usan las horas curriculares de la tabla, y la formación técnica ocupa el resto de la jornada.")
            c1, c2, c3 = st.columns(3)
            learners = c1.number_input("Aprendices por ficha", min_value=1, value=int(defaults["learners_per_ficha"]), key="learners_per_ficha")
            weekly = c2.number_input("Horas semanales por ficha diurna", min_value=1.0, value=float(defaults["weekly_hours_per_ficha"]), step=1.0, key="weekly_hours_per_ficha")
            plant_hours = c3.number_input("Horas semanales por instructor de planta", min_value=1.0, value=float(defaults["weekly_plant_direct_hours"]), step=0.5, key="weekly_plant_direct_hours")
            bilingual = c1.number_input("Bilingüismo por ficha diurna", min_value=0.0, value=float(defaults["weekly_bilingual_hours"]), step=1.0, key="weekly_bilingual_hours")
            integrality = c2.number_input("Integralidad por ficha diurna", min_value=0.0, value=float(defaults["weekly_integrality_hours"]), step=1.0, key="weekly_integrality_hours")
            contractor_hours = c3.number_input("Horas semanales por contratista", min_value=1.0, value=float(defaults["weekly_contractor_hours"]), step=1.0, key="weekly_contractor_hours")
            mixed_weekly = c1.number_input("Horas semanales por ficha mixta", min_value=1.0, value=float(defaults.get("mixed_weekly_hours_per_ficha", 26.0)), step=1.0, key="mixed_weekly_hours_per_ficha")
            mixed_bilingual = c2.number_input("Bilingüismo por ficha mixta", min_value=0.0, value=float(defaults.get("mixed_weekly_bilingual_hours", 4.0)), step=1.0, key="mixed_weekly_bilingual_hours")
            mixed_integrality = c3.number_input("Integralidad por ficha mixta", min_value=0.0, value=float(defaults.get("mixed_weekly_integrality_hours", 4.0)), step=1.0, key="mixed_weekly_integrality_hours")
            weeks = c1.number_input("Semanas efectivas por trimestre", min_value=1, max_value=13, value=int(defaults.get("weeks_per_quarter", 12)), key="weeks_per_quarter")
            st.caption(f"Año de 4 trimestres × {weeks} semanas = {4 * weeks} semanas. Los ingresos se programan al inicio y las terminaciones al final del trimestre.")
            offers = st.columns(4)
            weights = tuple(int(offers[q].number_input(f"Oferta adicional T{q + 1} (%)", min_value=0, max_value=100,
                           value=defaults.get("intake_weights", [50, 25, 15, 10])[q], key=f"intake_weight_{q}")) for q in range(4))
            st.caption("Estos porcentajes distribuyen el crecimiento y el saldo de la meta; los reemplazos siguen las fechas de terminación. Deben sumar 100 %.")
        rules = PlanningRules(int(learners), weekly, bilingual, integrality, plant_hours, contractor_hours, mixed_weekly, mixed_bilingual, mixed_integrality, int(weeks), weights)
        errors = rules.validate()
        for error in errors:
            st.error(error)
        expected_technical = fichas_from_target(targets["Técnico"], int(learners))
        expected_technologist = fichas_from_target(targets["Tecnólogo"], int(learners))
        expected_new = expected_technical + expected_technologist
        st.write(f"Según las metas: **{expected_technical} fichas de Técnico + {expected_technologist} de Tecnólogo = {expected_new} fichas nuevas**.")
        annual_preview = st.empty()
        if not errors:
            estimates = []
            for level, count, duration in [("Técnico", expected_technical, 3), ("Tecnólogo", expected_technologist, 7)]:
                intakes = largest_remainder_allocation(count, range(4), weights)
                ficha_weeks = sum(intakes[q] * min(duration, 4 - q) * weeks for q in range(4))
                estimates.append({"Nivel": level, "Fichas según meta": count,
                                  "Horas anuales si son diurnas": ficha_weeks * weekly,
                                  "Horas anuales si son mixtas": ficha_weeks * mixed_weekly})
            with annual_preview.container():
                st.markdown("**Referencia inicial de horas anuales de las metas**")
                st.dataframe(pd.DataFrame(estimates), hide_index=True, use_container_width=True)
                st.caption("Según las ofertas trimestrales y la duración regular de cada nivel. Esta referencia no incluye continuaciones ni reposiciones. Complete las filas y terminaciones para ver el total del escenario.")
        ficha_ready, import_key = True, "manual"
        if instructors is not None:
            ficha_import, import_key, ficha_ready = ficha_inputs(
                previous, int(year), technical_specialty_catalog(instructors),
            )
        st.markdown("**2. Ingresar las fichas por especialidad técnica**")
        st.caption(
            "Revise las fichas calculadas desde el reporte o ingréselas manualmente (0 si no hay). Puede editar todos los totales. "
            "Indique cuántas de esas fichas terminan durante la vigencia y se prevé reemplazar. "
            "El total se suma automáticamente; estas cantidades nunca se reparten ni se cambian por una sugerencia."
        )
        st.caption("Use una fila por especialidad, nivel y jornada. Las nuevas se distribuyen dentro de cada nivel; la planta de una especialidad atiende sus fichas de ambos niveles y jornadas.")
        if instructors is not None and ficha_ready:
            distribution_source = f"{source_digest}_{import_key}"
            if st.session_state.get("distribution_source") != distribution_source:
                st.session_state.distribution_source = distribution_source
                same_saved_import = ficha_import == previous.get("ficha_import")
                if source_digest == previous.get("source_digest") and same_saved_import and int(year) == previous.get("planning_year"):
                    base = pd.DataFrame(previous["distribution"])
                    if "Fichas que terminan" not in base:
                        base["Fichas que terminan"] = 0
                    base = base.reindex(columns=MANUAL_COLUMNS)
                elif ficha_import:
                    base = pd.DataFrame(ficha_import["summary"], columns=MANUAL_COLUMNS)
                else:
                    catalog = technical_specialty_catalog(instructors)
                    base = pd.DataFrame({
                        "Especialidad": catalog["Especialidad"],
                        "Nivel": None,
                        "Jornada": "Diurna",
                        "Fichas que pasan": pd.Series(pd.NA, index=catalog.index, dtype="Int64"),
                        "Fichas que terminan": 0,
                    })
                st.session_state.distribution_base = base
                st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
            if list(st.session_state.distribution_base.columns) != MANUAL_COLUMNS:
                if "Fichas que terminan" not in st.session_state.distribution_base:
                    st.session_state.distribution_base["Fichas que terminan"] = 0
                st.session_state.distribution_base = st.session_state.distribution_base.reindex(columns=MANUAL_COLUMNS)
                st.session_state.editor_revision += 1
            if source_digest == previous.get("source_digest") and previous.get("distribution_basis") != "quarterly_v1":
                st.info("Esta planeación se guardó con el método anterior. Revise nivel, jornada y terminaciones trimestrales antes de ejecutar. Los resultados anteriores se conservan hasta guardar.")
            # Las columnas ausentes de formatos antiguos llegan como float/NaN.
            # El editor necesita texto para aceptar las selecciones del usuario.
            for column in ["Nivel", "Jornada"]:
                values = st.session_state.distribution_base[column].astype(object)
                st.session_state.distribution_base[column] = values.where(values.notna(), None)
            manual = st.data_editor(
                st.session_state.distribution_base, use_container_width=True, hide_index=True, num_rows="dynamic",
                column_config={
                    "Especialidad": st.column_config.TextColumn(required=True),
                    "Nivel": st.column_config.SelectboxColumn(options=["Técnico", "Tecnólogo"], required=True),
                    "Jornada": st.column_config.SelectboxColumn(options=["Diurna", "Mixta"], required=True),
                    "Fichas que pasan": st.column_config.NumberColumn("Fichas que pasan (editable)", min_value=0, step=1, required=True),
                    "Fichas que terminan": st.column_config.NumberColumn("De esas, terminan en la vigencia", min_value=0, step=1, required=True, help="Solo cuente fichas incluidas en las que pasan. Sirven de referencia para las reposiciones."),
                },
                key=f"distribution_{distribution_source}_{st.session_state.editor_revision}",
            )
            try:
                transversal_continuity = transversal_inputs(instructors, rules, previous, source_digest, int(year))
                manual = validate_profiles(manual, instructors)
                quarter_endings = calendar_inputs(manual, ficha_import, previous, distribution_source + str(year))
                modules, continuing_hours = (module_inputs(manual, quarter_endings, rules, previous, ficha_import, source_digest, int(year))
                                             if modular else (None, None))
                execution_preview = execute_level_plan(instructors, manual, rules, targets, int(year), source_name, source_digest,
                                                       quarter_endings=quarter_endings, ficha_import=ficha_import,
                                                       transversal_continuity=transversal_continuity,
                                                       transversal_modules=modules, continuing_transversal_hours=continuing_hours)
                distribution = pd.DataFrame(execution_preview["distribution"], columns=MANUAL_COLUMNS + ["Fichas nuevas"])
                continuing = int(distribution["Fichas que pasan"].sum())
                projected_new = int(distribution["Fichas nuevas"].sum())
                rule = execution_preview["growth_rule"]
                st.markdown("**Proyección automática de fichas nuevas**")
                st.write(
                    f"Fichas según la meta: **{expected_new}** · Reposiciones: **{rule['replacement_fichas']}** · "
                    f"Crecimiento mínimo: **{rule['growth_fichas']}** · Nuevas proyectadas: **{projected_new}**."
                )
                st.dataframe(pd.DataFrame(execution_preview["levels"]), hide_index=True, use_container_width=True)
                with annual_preview.container():
                    annual_columns = st.columns(3)
                    for index, level in enumerate(execution_preview["levels"]):
                        annual_columns[index].metric(f"Horas anuales · {level['Nivel']}", f"{level['Horas anuales requeridas']:g}")
                    annual_columns[2].metric("Total de horas al año", f"{execution_preview['center']['demanda_total_horas_anuales']:g}")
                    st.caption(f"Horas de formación durante {year}: suma de fichas activas × horas semanales × {weeks} semanas en cada trimestre. Incluye continuaciones y nuevas; no son horas de toda la duración del programa.")
                st.dataframe(pd.DataFrame(execution_preview["quarterly"]), hide_index=True, use_container_width=True)
                st.markdown("**Contratación transversal adicional**")
                st.write(f"Pico de **{execution_preview['summary']['transversales_adicionales_pico']} contratistas adicionales**, después de usar la planta y los contratos que prevé conservar. Horas adicionales del año: **{execution_preview['summary']['horas_adicionales_transversales_anuales']:g}**.")
                st.dataframe(pd.DataFrame(execution_preview["transversal_quarterly"])[[
                    "Área", "Trimestre", "Demanda (h/sem)", "Capacidad disponible (h/sem)",
                    "Contratistas a conservar", "Contratistas adicionales", "Horas sin utilizar (h/sem)",
                    "Horas adicionales del trimestre"]], hide_index=True, use_container_width=True)
                if modular:
                    st.caption("Las horas de módulos se distribuyen entre las semanas efectivas del trimestre. El resultado es una capacidad semanal media: requiere programar los módulos a lo largo del trimestre para evitar concentraciones en una misma semana.")
                else:
                    st.warning("Escenario semanal de referencia: aplica transversales todas las semanas. Para su operación por módulos, seleccione el cálculo por módulos y configure sus horas reales.")
                projection = pd.DataFrame(execution_preview["hours"])
                st.dataframe(projection, hide_index=True, use_container_width=True)
                center_preview = execution_preview["center"]
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Pico de horas requeridas / semana", f"{center_preview['demanda_total_horas_semana']:g}")
                h2.metric("Horas técnicas al año", f"{center_preview['demanda_tecnica_horas_anuales']:g}")
                h3.metric("Bilingüismo al año", f"{center_preview['demanda_bilinguismo_horas_anuales']:g}")
                h4.metric("Integralidad al año", f"{center_preview['demanda_integralidad_horas_anuales']:g}")
                st.caption(f"Las nuevas fichas requieren {center_preview['demanda_nuevas_horas_anuales']:g} horas en esta vigencia. Reposiciones para T1 del próximo año: {center_preview['reposiciones_siguiente_vigencia']}. La contratación se estima por trimestre, sin mantener el pico durante todo el año.")
                if center_preview["nuevas_adicionales_por_rotacion"]:
                    st.info(f"Se agregan {center_preview['nuevas_adicionales_por_rotacion']} fichas en T4 para reemplazar nuevas fichas técnicas de T1 que terminan en T3. Están incluidas en la proyección y pueden superar la meta.")
                with st.expander("Capacidad de atención de la planta por especialidad"):
                    st.dataframe(pd.DataFrame(execution_preview["technical_quarterly"]), hide_index=True, use_container_width=True)
                    st.caption("La capacidad se comparte entre las fichas de cada especialidad. A 18 h técnicas por ficha, 32 h de planta equivalen a 1,78 fichas: puede cubrir una completa y 14 h de otra; dos fichas requieren 36 h y dejan 4 h por cubrir.")
                st.caption(
                    "Cada especialidad y nivel recibe sus reposiciones + el 5 % de las fichas que pasan, redondeado hacia arriba una sola vez entre sus jornadas. "
                    "Las fichas restantes de la meta se reparten proporcionalmente a las que pasan. "
                    "La proyección se actualiza al cambiar cualquier dato, sin modificar las cantidades manuales."
                )
                if projected_new > expected_new:
                    st.warning(
                        f"La regla requiere {projected_new - expected_new} fichas adicionales sobre la meta. "
                        f"Se proyectan {projected_new} fichas nuevas, equivalentes a {projected_new * int(learners)} "
                        f"cupos, frente a la meta ingresada de {int(target)} aprendices. Puede ejecutar y guardar esta proyección."
                    )
                if continuing == 0 and expected_new > 0:
                    st.info("Todas las continuaciones son cero: la meta se reparte equitativamente entre las especialidades registradas.")
                draft_valid = not errors
                if draft_valid:
                    st.success("Proyección lista para ejecutar: reposiciones y crecimiento del 5 % cubiertos.")
            except ValueError as exc:
                st.warning(str(exc))

        st.markdown("**3. Ejecutar y guardar**")
        st.caption("La carga anterior se elimina únicamente cuando la nueva planeación es válida y se guarda correctamente.")
        execute = st.button("Ejecutar y guardar planeación", type="primary", use_container_width=True, disabled=not draft_valid)
        if execute:
            try:
                with st.spinner("Calculando y guardando en SQLite…"):
                    execution = execution_preview
                    if ficha_import:
                        execution["ficha_import"] = ficha_import
                    save_planning(DATABASE_PATH, instructors, execution)
                    saved = load_planning(DATABASE_PATH)
                st.success("Planeación ejecutada y guardada. La base de datos contiene únicamente esta carga y su última ejecución.")
            except (ValueError, sqlite3.Error, OSError) as exc:
                st.error(f"No fue posible ejecutar y guardar la planeación: {exc}")

    st.divider()
    if saved:
        current = saved[1]
        pending = (
            not draft_valid or source_digest != current["source_digest"]
            or source_name != current["source_name"] or int(year) != current["planning_year"]
            or int(target) != current["target_learners"] or int(continuing) != current["continuing_fichas"]
            or json.dumps(asdict(rules), sort_keys=True) != json.dumps(current["rules"], sort_keys=True)
            or current.get("distribution_basis") != "quarterly_v1"
            or targets != current.get("targets_by_level")
            or ficha_import != current.get("ficha_import")
        )
        if draft_valid:
            pending = pending or distribution.to_dict("records") != current["distribution"]
            pending = pending or execution_preview["quarter_endings"] != current.get("quarter_endings")
            pending = pending or execution_preview["transversal_continuity"] != current.get("transversal_continuity")
            pending = pending or execution_preview["transversal_demand_model"] != current.get("transversal_demand_model")
            pending = pending or execution_preview.get("transversal_modules") != current.get("transversal_modules")
            pending = pending or execution_preview.get("continuing_transversal_hours") != current.get("continuing_transversal_hours")
        if pending:
            st.warning("Hay datos pendientes de ejecutar. Los resultados y la descarga corresponden a la última ejecución guardada indicada abajo.")
        render_results(*saved)
    else:
        st.info("Aún no hay una planeación guardada. Complete los datos y pulse «Ejecutar y guardar planeación» para obtener los resultados.")


def main() -> None:
    from ui.automatic_planning import render_automatic_planning
    render_automatic_planning(DATABASE_PATH)


if __name__ == "__main__":
    main()
