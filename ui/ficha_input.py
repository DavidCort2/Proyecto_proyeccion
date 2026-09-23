"""Carga y cálculo inicial de continuaciones; la tabla final sigue siendo editable."""
from hashlib import sha256
from io import BytesIO
import json

import pandas as pd
import streamlit as st

from core.excel_parser import normalize_text
from core.fichas_parser import parse_fichas_excel
from core.ficha_projection import duration_in_quarters, merge_ficha_specialties, project_ficha_carryover


@st.cache_data(show_spinner=False, max_entries=4)
def read_fichas(content: bytes) -> pd.DataFrame:
    return parse_fichas_excel(BytesIO(content))


def ficha_inputs(previous: dict, planning_year: int, catalog: pd.DataFrame):
    """Devuelve contexto persistible, clave de importación y validez de la carga."""
    st.markdown("**Reporte de fichas actuales**")
    modes = ["Cargar reporte de fichas"]
    saved = previous.get("ficha_import")
    if previous:
        modes.append("Usar reporte de fichas guardado")
    if st.session_state.get("fichas_mode") not in modes:
        st.session_state.fichas_mode = modes[-1] if saved else modes[0]
    mode = st.radio("Origen de las fichas", modes, key="fichas_mode", horizontal=True)
    try:
        if mode == "Usar reporte de fichas guardado":
            if not saved:
                st.caption("La planeación guardada contiene cantidades manuales. Puede revisarlas en la tabla.")
                return None, "manual", True
            frame = pd.DataFrame(saved["rows"])
            name, digest = saved["source_name"], saved["source_digest"]
            initial_year, initial_quarter = saved["report_year"], saved["report_quarter"]
        else:
            uploaded = st.file_uploader("Reporte de fichas (.xlsx)", type=["xlsx"], key="fichas_upload")
            if uploaded is None:
                st.info("Cargue el reporte para calcular las continuaciones automáticamente, o complete las cantidades en la tabla editable.")
                return None, "manual", True
            name, content = uploaded.name, uploaded.getvalue()
            digest = sha256(content).hexdigest()
            frame = read_fichas(content)
            initial_year = frame.attrs.get("report_year", planning_year - 1)
            initial_quarter = frame.attrs.get("report_quarter", 4)
            if "report_year" not in frame.attrs:
                st.warning("No se identificó el período en el encabezado. Revise el año y trimestre del reporte.")
        c1, c2 = st.columns(2)
        report_year = int(c1.number_input("Año del reporte de fichas", min_value=2000, max_value=2200, value=initial_year, key=f"fichas_year_{digest}"))
        quarter = int(c2.number_input("Trimestre calendario del reporte", min_value=1, max_value=4, value=initial_quarter, key=f"fichas_quarter_{digest}"))
        overrides = {}
        unresolved = False
        for level, schedule in frame[["Nivel", "Jornada"]].drop_duplicates().itertuples(index=False, name=None):
            try:
                duration_in_quarters(level, schedule)
            except ValueError:
                if normalize_text(level) != "TECNOLOGO":
                    raise ValueError(f"El nivel '{level}' no tiene una duración definida. Revise el archivo.")
                normalized = normalize_text(schedule)
                prior = (saved or {}).get("schedule_overrides", {}).get(normalized, 0)
                choice = st.selectbox(
                    f"Duración de Tecnólogo · {schedule}", options=[0, 7, 9], index=[0, 7, 9].index(prior),
                    format_func=lambda value: "Seleccione la duración y jornada" if value == 0 else ("7 trimestres · Diurna (30 h/sem)" if value == 7 else "9 trimestres · Mixta (26 h/sem)"),
                    key=f"fichas_duration_{digest}_{normalized}",
                )
                if choice == 0:
                    unresolved = True
                else:
                    overrides[normalized] = choice
        if unresolved:
            st.warning("Defina la duración de las jornadas especiales para calcular todas las fichas sin asumir una regla.")
            return None, "unresolved", False
        detail, summary = project_ficha_carryover(frame, report_year, quarter, planning_year, overrides, group_by_profile=True)
        summary = merge_ficha_specialties(summary, catalog)
        context = {
            "schema_version": 3,
            "source_name": name, "source_digest": digest, "report_year": report_year,
            "report_quarter": quarter, "planning_year": planning_year,
            "schedule_overrides": overrides,
            "rows": json.loads(frame.to_json(orient="records", force_ascii=False)),
            "detail": json.loads(detail.to_json(orient="records", force_ascii=False)),
            "summary": json.loads(summary.to_json(orient="records", force_ascii=False)),
        }
        context_key = sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        st.info(
            f"{name} · {len(frame)} fichas · {int(summary['Fichas que pasan'].sum())} pasan a {planning_year} · "
            f"{int(summary['Fichas que terminan'].sum())} de ellas terminan durante {planning_year}."
        )
        st.caption(
            "Referencias del modelo histórico: Técnico 3 trimestres; Tecnólogo diurno 7; Tecnólogo mixto 9. "
            "El trimestre reportado se considera en curso y la ficha termina al finalizar su último trimestre. "
            "Las que terminan antes del año planeado no pasan."
        )
        with st.expander("Revisar el cálculo ficha por ficha"):
            st.dataframe(detail, hide_index=True, use_container_width=True)
        st.caption("Los totales se cargan en la tabla editable. Cambiar el archivo, período, vigencia o duración de jornadas vuelve a calcularlos y reemplaza las ediciones de esa tabla.")
        return context, context_key, True
    except Exception as exc:
        st.error(f"No fue posible calcular el reporte de fichas: {exc}")
        return None, "invalid", False
