"""Limpieza explícita de los datos guardados y de la sesión de planeación."""
import sqlite3

import streamlit as st

from core.database import reset_planning_database


def render_system_reset(path):
    with st.expander("Limpieza del sistema"):
        st.warning(
            "Se borrarán todos los reportes guardados, las mallas, las competencias "
            "y su clasificación, y la planeación. También se reiniciarán las metas, "
            "los parámetros y los archivos cargados en pantalla. Este borrado no se puede deshacer."
        )
        st.caption("Los archivos Excel originales y las descargas en su equipo se conservan.")
        confirmed = st.checkbox(
            "Confirmo que deseo borrar todos los datos del sistema",
            key="confirm_system_reset",
        )
        if st.button("Formatear sistema", disabled=not confirmed, key="format_system") and confirmed:
            try:
                reset_planning_database(path)
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f"No fue posible completar la limpieza: {exc}")
                return
            # La siguiente ejecución detecta la nueva versión de la base y limpia
            # la sesión antes de crear los widgets, incluidas las cargas de Excel.
            st.session_state["_system_reset_complete"] = True
            st.rerun()
