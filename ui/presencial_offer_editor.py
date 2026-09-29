"""Edición de ingresos presenciales con guardado y recálculo completo."""
from hashlib import sha256
import json
import sqlite3

import pandas as pd
import streamlit as st

from core.curriculum_intakes import OFFER_COLUMNS
from ui.planning_session import scoped_key, widget_key


def save_offers_and_refresh(save_offers, offers):
    try:
        save_offers(offers)
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(f"No fue posible guardar las ofertas: {exc}")
        return
    revision = scoped_key("presencial_offers_revision")
    st.session_state[revision] = st.session_state.get(revision, 0) + 1
    st.session_state[scoped_key("presencial_offers_saved")] = (
        "Ofertas guardadas. Se actualizaron las fichas, las horas, la contratación y sus fechas."
        if offers is not None else "Distribución automática restaurada y planeación recalculada."
    )
    st.rerun()


def render_restore_offers(save_offers):
    if st.button("Restaurar distribución automática", key=widget_key("restore_presencial_offers")):
        save_offers_and_refresh(save_offers, None)


def render_offer_editor(execution, save_offers):
    programs = pd.DataFrame(execution["offers_by_program"])
    st.caption("Edite Oferta T1 a T4: puede mover fichas entre ofertas y cambiar el total anual de cada programa. "
               "Pulse «Guardar ofertas y recalcular» para actualizar el total anual, las demás tablas, "
               "la contratación y el Excel. Los cambios sin guardar no se aplican a los resultados.")
    revision = st.session_state.get(scoped_key("presencial_offers_revision"), 0)
    signature = sha256(json.dumps([execution["planning_year"], execution["offers_by_program"], revision],
                                 sort_keys=True).encode()).hexdigest()[:16]
    with st.form(scoped_key("presencial_offers_form_" + signature)):
        edited = st.data_editor(
            programs, hide_index=True, use_container_width=True, num_rows="fixed",
            disabled=[column for column in programs.columns if column not in OFFER_COLUMNS],
            column_config={column: st.column_config.NumberColumn(column, min_value=0, step=1, required=True)
                           for column in OFFER_COLUMNS},
            key=widget_key("presencial_offers_editor_" + signature),
        )
        submitted = st.form_submit_button("Guardar ofertas y recalcular", type="primary")
    if submitted:
        offers = {"planning_year": execution["planning_year"],
                  "programs": edited[["Programa", "Nivel", *OFFER_COLUMNS]].to_dict("records")}
        save_offers_and_refresh(save_offers, offers)
    if execution.get("manual_offers"):
        render_restore_offers(save_offers)
