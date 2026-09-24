"""Limpieza explícita de los datos guardados y de la sesión de planeación."""
import sqlite3

import streamlit as st

from core.database import reset_planning_database
from ui.planning_session import scoped_key, widget_key


def render_system_reset(path):
    modality = st.session_state.get("_planning_scope")
    sources = "los cronogramas y la carga docente" if modality == "Virtual" else "las mallas y las competencias"
    with st.expander("Limpieza del sistema"):
        if modality:
            st.info(f"Esta limpieza afecta únicamente a Titulada {modality.lower()}. La otra modalidad conserva sus datos.")
        st.warning(
            f"Se borrarán todos los datos manuales y reportes guardados de esta modalidad, {sources}, "
            "su clasificación y la planeación. También se reiniciarán las metas, "
            "los parámetros y los archivos cargados en pantalla. Este borrado no se puede deshacer."
        )
        st.caption("Los archivos Excel originales y las descargas en su equipo se conservan.")
        confirmed = st.checkbox(
            "Confirmo que deseo borrar todos los datos de esta modalidad",
            key=widget_key("confirm_system_reset"),
        )
        if st.button("Formatear sistema", disabled=not confirmed, key=scoped_key("format_system")) and confirmed:
            try:
                reset_planning_database(path)
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(f"No fue posible completar la limpieza: {exc}")
                return
            # La siguiente ejecución detecta la nueva versión de la base y limpia
            # la sesión antes de crear los widgets, incluidas las cargas de Excel.
            st.session_state[scoped_key("_system_reset_complete")] = True
            st.rerun()
