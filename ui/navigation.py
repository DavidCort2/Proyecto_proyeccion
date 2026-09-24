"""Navegación entre los cuatro espacios de formación."""
import streamlit as st

from core.planning_modules import planning_database
from ui.planning_session import preserve_planning_widgets


def render_application(base_path):
    st.set_page_config(page_title="Planeación Indicativa SENA", page_icon="📊", layout="wide")
    with st.sidebar:
        st.title("Planeación Indicativa")
        training = st.radio("Formación", ["Titulada", "Complementaria"], key="nav_training")
        modality = st.radio("Modalidad", ["Presencial", "Virtual"], key="nav_modality")
    preserve_planning_widgets(modality if training == "Titulada" else None)
    st.title(f"{training} · {modality.lower()}")
    if training == "Complementaria":
        st.caption("Módulo pendiente de desarrollo.")
        return
    st.session_state["_planning_scope"] = modality
    st.caption("Planeación independiente de Titulada " + modality.lower() + ".")
    from ui.automatic_planning import render_automatic_planning
    render_automatic_planning(planning_database(base_path, modality), modality=modality, standalone=False)
