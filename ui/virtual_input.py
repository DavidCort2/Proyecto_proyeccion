"""Formularios manuales de Titulada virtual."""
import streamlit as st

from core.curriculum import catalog_digest
from core.virtual_planning import virtual_templates
from ui.planning_session import scoped_key, widget_key


def virtual_inputs(catalog, previous):
    if not catalog["curricula"]:
        st.info("Cargue las trimestralizaciones virtuales en «Mallas y competencias» para registrar los programas y su planta.")
        return None
    # Una base estable evita aplicar dos veces las ediciones de st.data_editor.
    base_key = scoped_key("manual_bases")
    catalog_key = scoped_key("manual_catalog")
    revision_key = scoped_key("manual_editor_revision")
    if st.session_state.get(catalog_key) != catalog_digest(catalog):
        templates = virtual_templates(catalog, previous)
        # Al agregar/reemplazar una malla se conservan los borradores existentes.
        draft = st.session_state.get(scoped_key("virtual_draft"))
        if draft is not None:
            templates = virtual_templates(catalog, {"virtual_inputs": draft})
        st.session_state[base_key] = templates
        st.session_state[catalog_key] = catalog_digest(catalog)
        st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
    programs, cohorts, plant = st.session_state[base_key]
    revision = str(st.session_state[revision_key])
    st.subheader("Programas virtuales a planear")
    st.caption("Seleccione el nivel de cada programa. El peso de oferta reparte las fichas nuevas dentro de cada nivel: con todos en 1, el reparto es igual. Un peso 2 recibe el doble de participación que un peso 1, sujeto al redondeo a fichas completas.")
    programs = st.data_editor(programs, hide_index=True, use_container_width=True, disabled=["Programa"],
                             column_config={
                                 "Incluir": st.column_config.CheckboxColumn(required=True),
                                 "Nivel": st.column_config.SelectboxColumn(options=["Técnico", "Tecnólogo"], required=True),
                                 "Peso de oferta": st.column_config.NumberColumn(min_value=1, step=1, required=True),
                             }, key=widget_key("virtual_programs_" + revision))
    st.subheader("Fichas que pasan")
    st.caption("Agregue una fila por programa y trimestre de formación al iniciar la vigencia. Si sus fichas van en trimestres distintos, sepárelas en varias filas. Deje la tabla vacía si no pasan fichas. Las terminaciones se calculan con la malla.")
    cohorts = st.data_editor(cohorts, hide_index=True, use_container_width=True, num_rows="dynamic",
                            column_config={
                                "Programa": st.column_config.SelectboxColumn(options=programs["Programa"].tolist(), required=True),
                                "Fichas que pasan": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                                "Trimestre al iniciar la vigencia": st.column_config.NumberColumn(min_value=1, step=1, required=True),
                            }, key=widget_key("virtual_cohorts_" + revision))
    st.subheader("Instructores de planta")
    st.caption("Ingrese la cantidad disponible por perfil; use 0 donde no haya planta. La planta técnica se comparte entre las fichas de su programa. Bilingüismo e Integralidad cubren sus respectivas competencias en los programas virtuales.")
    plant = st.data_editor(plant, hide_index=True, use_container_width=True, disabled=["Área", "Perfil"],
                          column_config={"Instructores de planta": st.column_config.NumberColumn(min_value=0, step=1, required=True)},
                          key=widget_key("virtual_plant_" + revision))
    draft = {"programs": programs.to_dict("records"), "cohorts": cohorts.to_dict("records"), "plant": plant.to_dict("records")}
    st.session_state[scoped_key("virtual_draft")] = draft
    return draft
