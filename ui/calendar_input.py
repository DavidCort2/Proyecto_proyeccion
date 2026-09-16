from hashlib import sha256

import pandas as pd
import streamlit as st

from core.calendar_planner import ENDING_COLUMNS, suggested_endings, validate_endings
from core.level_planner import MANUAL_COLUMNS, PROFILE_COLUMNS


def calendar_inputs(manual, imported, previous, source_key):
    base = suggested_endings(manual, imported)
    if (previous.get("quarter_endings") and source_key.startswith(previous["source_digest"])
            and imported == previous.get("ficha_import")
            and manual.to_dict("records") == pd.DataFrame(previous["distribution"])[MANUAL_COLUMNS].to_dict("records")):
        base = validate_endings(manual, pd.DataFrame(previous["quarter_endings"]))
    key = sha256((source_key + manual.to_json(orient="records")).encode()).hexdigest()
    with st.expander("Terminaciones por trimestre · revisar y editar", expanded=False):
        st.caption("El reporte aporta el trimestre de terminación. Sin fechas se propone un reparto uniforme editable. Si cambia el total manual, se redistribuye siguiendo el reporte; revise estas fechas estimadas. La suma debe coincidir con las terminaciones de cada fila.")
        result = st.data_editor(base, hide_index=True, use_container_width=True,
                               disabled=PROFILE_COLUMNS,
                               column_config={column: st.column_config.NumberColumn(min_value=0, step=1, required=True) for column in ENDING_COLUMNS},
                               key=f"quarter_editor_{key}")
    return validate_endings(manual, result)
