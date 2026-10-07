"""Estado de edición y archivos independientes por modalidad."""
from dataclasses import dataclass

import streamlit as st


SCOPE_PREFIXES = {"Presencial": "", "Virtual": "virtual:",
                  "Complementaria Presencial": "complementaria:presencial:",
                  "Complementaria Virtual": "complementaria:virtual:", "Complementaria común": "complementaria:shared:"}


def scope_for_key(key):
    for scope, prefix in reversed(list(SCOPE_PREFIXES.items())):
        if key.startswith(prefix):
            return scope


def scoped_key(name):
    return SCOPE_PREFIXES.get(st.session_state.get("_planning_scope"), "") + name


def widget_key(name):
    key = scoped_key(name)
    keys = st.session_state.setdefault("_planning_widget_keys", set())
    keys.add(key)
    return key


def preserve_planning_widgets(active_modality=None):
    # Streamlit elimina los widgets ocultos al navegar. Separarlos de su ciclo
    # de vida mantiene los borradores hasta guardar o limpiar esa modalidad.
    for key in st.session_state.get("_planning_widget_keys", set()):
        active = active_modality is not None and scope_for_key(key) == active_modality
        if not active and key in st.session_state:
            st.session_state[key] = st.session_state[key]


def clear_module_session():
    scope = st.session_state.get("_planning_scope", "Presencial")
    for key in list(st.session_state):
        if key.startswith("_") or key.startswith("nav_"):
            continue
        if scope_for_key(key) == scope:
            del st.session_state[key]
    # Estos metadatos también pertenecen a la modalidad activa.
    for name in ("_database_reset_version", "_system_reset_complete"):
        st.session_state.pop(scoped_key(name), None)


@dataclass
class RememberedUpload:
    name: str
    content: bytes

    def getvalue(self):
        return self.content


def module_file_uploader(label, *, key, accept_multiple_files=False, **kwargs):
    memory_key = scoped_key("uploads:" + key)

    def remember():
        value = st.session_state.get(key)
        items = (value or []) if accept_multiple_files else ([value] if value else [])
        st.session_state[memory_key] = [RememberedUpload(item.name, item.getvalue()) for item in items]

    uploaded = st.file_uploader(label, key=key, accept_multiple_files=accept_multiple_files,
                                on_change=remember, **kwargs)
    if uploaded:
        items = uploaded if accept_multiple_files else [uploaded]
        st.session_state[memory_key] = [RememberedUpload(item.name, item.getvalue()) for item in items]
        return uploaded
    remembered = st.session_state.get(memory_key, [])
    if remembered:
        st.caption("Archivos conservados al navegar: " + ", ".join(item.name for item in remembered))
        if st.button("Quitar archivos conservados", key=key + ":forget"):
            st.session_state.pop(memory_key, None)
            return [] if accept_multiple_files else None
    return remembered if accept_multiple_files else (remembered[0] if remembered else None)
