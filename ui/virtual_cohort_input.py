"""Registro individual y agregado por lotes de las fichas virtuales que pasan."""
import pandas as pd
import streamlit as st

from core.virtual_planning import whole_number
from core.virtual_schedule import read_date
from ui.planning_session import scoped_key, widget_key


def individual_rows(cohorts):
    """Conserva las cantidades y fechas de los grupos guardados anteriormente."""
    rows = []
    for row in cohorts:
        quantity = row.get("Fichas que pasan")
        count = 1 if pd.isna(quantity) else whole_number(quantity, "Fichas que pasan", 1)
        rows.extend({"Programa": row.get("Programa"), "Fecha fin lectiva": row.get("Fecha fin lectiva")}
                    for _ in range(count))
    return rows


def continuing_ficha_inputs(programs, cohorts, parent_revision):
    st.subheader("Fichas que pasan")
    st.caption("Seleccione el programa y cuántas fichas desea agregar. Cada fila representa una ficha: complete su último día de etapa lectiva. Puede agregar una sola o varias de una vez, editar sus fechas y eliminar filas.")
    base_key = scoped_key("cohort_individual_base")
    revision_key = scoped_key("cohort_individual_revision")
    parent_key = scoped_key("cohort_parent_revision")
    if st.session_state.get(parent_key) != parent_revision:
        # Incluye también el borrador de una sesión abierta con el editor
        # anterior, cuya base todavía puede no contener las últimas ediciones.
        latest = st.session_state.get(scoped_key("schedule_manual_draft"), {}).get("cohorts", cohorts)
        st.session_state[base_key] = individual_rows(latest)
        st.session_state[parent_key] = parent_revision
        st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1

    left, middle, right = st.columns([3, 1, 1], vertical_alignment="bottom")
    program = left.selectbox("Programa de las fichas", options=programs, key=widget_key("cohort_batch_program"))
    quantity = middle.number_input("Cantidad a agregar", min_value=1, value=1, step=1, key=widget_key("cohort_batch_quantity"))
    add = right.button("Agregar fichas", key=scoped_key("add_cohort_batch"), use_container_width=True)
    frame = pd.DataFrame(st.session_state[base_key], columns=["Programa", "Fecha fin lectiva"])
    frame["Fecha fin lectiva"] = pd.to_datetime(frame["Fecha fin lectiva"])
    frame["Programa"] = frame["Programa"].astype("string")
    edited = st.data_editor(frame, num_rows="dynamic", hide_index=True, use_container_width=True,
                            column_config={"Programa": st.column_config.SelectboxColumn(options=programs, required=True),
                                           "Fecha fin lectiva": st.column_config.DateColumn(format="DD/MM/YYYY", required=True)},
                            key=widget_key(f"virtual_cohorts_individual_{parent_revision}_{st.session_state[revision_key]}"))
    rows = [{"Programa": row["Programa"], "Fichas que pasan": 1,
             "Fecha fin lectiva": read_date(row["Fecha fin lectiva"], "Fin lectiva").isoformat() if pd.notna(row["Fecha fin lectiva"]) else None}
            for row in edited.to_dict("records")]
    if add:
        rows.extend({"Programa": program, "Fichas que pasan": 1, "Fecha fin lectiva": None} for _ in range(int(quantity)))
        # Cambiar solo la base de este editor evita reaplicar altas/bajas del
        # widget anterior y conserva las fechas ya editadas y los demás campos.
        st.session_state[base_key] = individual_rows(rows)
        st.session_state[revision_key] += 1
    total = len(rows)
    pending = sum(row["Fecha fin lectiva"] is None for row in rows)
    left, middle, right = st.columns(3)
    left.metric("Total de fichas que pasan", total)
    middle.metric("Con fecha fin lectiva", total - pending)
    right.metric("Fechas pendientes", pending)
    if rows:
        counts = pd.DataFrame(rows).fillna({"Programa": "Sin programa"}).groupby("Programa", sort=True, dropna=False).agg(
            Fichas=("Fichas que pasan", "sum"),
            **{"Fechas pendientes": ("Fecha fin lectiva", lambda values: int(values.isna().sum()))})
        st.dataframe(counts.reset_index(), hide_index=True, use_container_width=True)
    if pending:
        st.info(f"Complete la fecha fin lectiva de {pending} ficha(s) para ejecutar la planeación.")
    return rows, add
