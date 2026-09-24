"""Lee cronogramas Excel con fases, actividades, fechas y celdas combinadas."""
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import math
import re

from openpyxl import load_workbook

from core.curriculum import name_key
from core.excel_parser import normalize_text


def is_lective_activity(row):
    """La etapa productiva se conserva como origen, pero no genera carga docente."""
    return normalize_text(row["phase"]) != "ETAPA PRODUCTIVA"


def lective_activities(schedule):
    return [row for row in schedule["activities"] if is_lective_activity(row)]


def read_date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError(f"{label}: indique una fecha válida (día/mes/año).")


def finite_hours(value, label):
    try:
        hours = float(value)
        if isinstance(value, bool) or not math.isfinite(hours) or hours < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f"{label}: ingrese horas no negativas; use 0 explícito si no requiere instructor.") from None
    return hours


def _source_number(value, label):
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:HORAS?|MESES?|MES)?\s*", normalize_text(value))
    if not match:
        raise ValueError(f"{label}: no se pudo leer el valor {value!r}.")
    return float(match[1].replace(",", "."))


def _phases(sheet, column, first, last):
    """Reconstruye rótulos partidos al convertir un cronograma PDF a Excel."""
    groups = []
    for row in range(first, last + 1):
        raw = sheet.cell(row, column).value
        if raw is None:
            continue
        compact = re.sub(r"\s+", "", normalize_text(raw))
        if compact.startswith("ETAPA"):
            continue
        if compact.startswith(("FAS", "INDUC")):
            groups.append([row, compact])
        elif groups:
            groups[-1][1] += compact
        else:
            raise ValueError(f"{sheet.title}, fila {row}: no se reconoce el nombre de la fase.")
    result = {}
    for index, (start, text) in enumerate(groups):
        if text.startswith("INDUC"):
            label = "Inducción"
        else:
            match = re.fullmatch(r"FASE(\d+)(.+)", text)
            if not match:
                raise ValueError(f"{sheet.title}, fila {start}: complete el nombre de la fase ({text}).")
            names = {"ANALISIS": "Análisis", "PLANEACION": "Planeación", "EJECUCION": "Ejecución", "EVALUACION": "Evaluación"}
            label = f"Fase {int(match[1])} · {names.get(match[2], match[2].capitalize())}"
        end = groups[index + 1][0] if index + 1 < len(groups) else last + 1
        result.update({row: label for row in range(start, end)})
    return result


def parse_virtual_schedule(content, filename):
    if not filename.lower().endswith(".xlsx"):
        raise ValueError("Los cronogramas virtuales se cargan exclusivamente en Excel (.xlsx).")
    try:
        book = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        raise ValueError(f"{filename}: no es un Excel válido.") from exc
    program, project, activities, blocks, summaries, warnings = None, "", [], [], [], []
    reference_start = reference_end = None
    try:
        for sheet in book:
            header = None
            for row in sheet.iter_rows():
                cells = {normalize_text(cell.value): cell.column for cell in row if cell.value is not None}
                if {"FASES", "ACTIVIDADES DE APRENDIZAJE", "FECHA INICIO", "FECHA FINAL"} <= set(cells):
                    header = row[0].row, cells
                    break
            if header is None:
                continue
            header_row, columns = header
            needed = ["ACTIVIDADES DEL PROYECTO", "TIEMPO DE DURACION ESTIMADO HORAS"]
            if any(label not in columns for label in needed):
                raise ValueError(f"{sheet.title}: faltan las columnas de actividades del proyecto y horas estimadas.")
            for row in sheet.iter_rows(max_row=header_row - 1, values_only=True):
                for raw in row:
                    if isinstance(raw, str) and normalize_text(raw).startswith("NOMBRE DE PROGRAMA:"):
                        name = raw.split(":", 1)[1].strip()
                        if program and name_key(program) != name_key(name):
                            raise ValueError("Cargue un cronograma por programa en cada archivo.")
                        program = name
                    elif isinstance(raw, str) and normalize_text(raw).startswith("NOMBRE DEL PROYECTO:"):
                        project = raw.split(":", 1)[1].strip()
                nonempty = [value for value in row if value is not None]
                if nonempty and normalize_text(nonempty[0]) in {"FECHA INICIO:", "FECHA FIN:"}:
                    value = read_date(nonempty[-1], f"{sheet.title}, encabezado")
                    if normalize_text(nonempty[0]) == "FECHA INICIO:":
                        reference_start = value
                    else:
                        reference_end = value
            # Solo propaga celdas realmente combinadas; los vacíos de una
            # continuación de página se tratan después dentro del mismo bloque.
            merged = {}
            for span in sheet.merged_cells.ranges:
                for row in range(span.min_row, span.max_row + 1):
                    for col in range(span.min_col, span.max_col + 1):
                        merged[(row, col)] = (span.min_row, span.min_col)

            def value(row, label):
                col = columns[label]
                anchor = merged.get((row, col), (row, col))
                return sheet.cell(*anchor).value, anchor

            phases = _phases(sheet, columns["FASES"], header_row + 1, sheet.max_row)
            current = None
            counted_hours = set()
            for row in range(header_row + 1, sheet.max_row + 1):
                location = f"{sheet.title}, fila {row}"
                phase_raw = normalize_text(value(row, "FASES")[0])
                start_raw, _ = value(row, "FECHA INICIO")
                end_raw, _ = value(row, "FECHA FINAL")
                hours_raw, hours_anchor = value(row, "TIEMPO DE DURACION ESTIMADO HORAS")
                learning = sheet.cell(row, columns["ACTIVIDADES DE APRENDIZAJE"]).value
                if phase_raw in {"ETAPA LECTIVA", "ETAPA PRODUCTIVA"}:
                    start, end = read_date(start_raw, location), read_date(end_raw, location)
                    if end < start:
                        raise ValueError(f"{location}: la fecha final es anterior a la inicial.")
                    hours = _source_number(hours_raw, location)
                    summaries.append({"stage": phase_raw, "start": start.isoformat(), "end": end.isoformat(), "hours": hours})
                    if phase_raw == "ETAPA LECTIVA":
                        continue  # Resumen, no otra actividad: no duplica horas.
                    learning = "Seguimiento de etapa productiva"
                    phase = "Etapa productiva"
                    project_activity = "Etapa productiva"
                else:
                    if learning is None or not str(learning).strip():
                        continue
                    phase = phases.get(row)
                    if phase is None:
                        raise ValueError(f"{location}: actividad sin fase.")
                    project_activity = value(row, "ACTIVIDADES DEL PROYECTO")[0]
                    if start_raw is None and end_raw is None and current:
                        start_raw, end_raw = current["start"], current["end"]
                        project_activity = current["project_activity"]
                        warnings.append(f"{location}: continuación sin fechas; conserva el intervalo del bloque anterior.")
                    start, end = read_date(start_raw, location), read_date(end_raw, location)
                    if end < start:
                        raise ValueError(f"{location}: la fecha final es anterior a la inicial.")
                block_key = (phase, start.isoformat(), end.isoformat(), str(project_activity))
                if current is None or current["identity"] != block_key:
                    current = {"id": f"B{len(blocks) + 1}", "identity": block_key, "phase": phase,
                               "project_activity": str(project_activity or ""), "start": start.isoformat(), "end": end.isoformat(),
                               "source_hours": 0.0, "source_sheet": sheet.title, "source_row": row}
                    blocks.append(current)
                anchor_key = (sheet.title, hours_anchor)
                if hours_raw is not None and anchor_key not in counted_hours:
                    current["source_hours"] += _source_number(hours_raw, location)
                    counted_hours.add(anchor_key)
                raw_text = " ".join(str(learning).split())
                matches = list(re.finditer(r"GA\s*\d+\s*-\s*(\d{6,12})\s*-\s*AA\s*\d+", raw_text, flags=re.I))
                # Una celda puede contener varias actividades o competencias.
                # Cada código tiene clasificación y carga propia; las horas de
                # referencia continúan contándose una sola vez por bloque.
                if len(matches) > 1:
                    warnings.append(f"{location}: contiene {len(matches)} códigos de actividad; revise por separado su clasificación y horas docentes.")
                entries = [(re.sub(r"\s+", "", match[0].upper()), match[1],
                            raw_text[match.start() if i else 0:matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)].strip())
                           for i, match in enumerate(matches)] or [(f"{phase} · {raw_text}", phase, raw_text)]
                for identity, competency, activity_text in entries:
                    activities.append({"id": sha256((name_key(program) + "|" + identity).encode()).hexdigest()[:24],
                                       "block_id": current["id"], "phase": phase, "competency": competency,
                                       "activity_code": identity, "activity": activity_text, "source_text": raw_text,
                                       "start": start.isoformat(), "end": end.isoformat(),
                                       "teaching_type": None, "instructor_hours": None,
                                       "source_sheet": sheet.title, "source_row": row})
        if not program or not activities:
            raise ValueError("No se encontró un cronograma con Nombre de programa, Fases, Actividades de Aprendizaje y fechas.")
        if not any(is_lective_activity(row) for row in activities):
            raise ValueError("El cronograma debe contener actividades de etapa lectiva para planear sus horas.")
        if len({item["id"] for item in activities}) != len(activities):
            raise ValueError("Hay actividades con el mismo código repetido. Revise el cronograma para evitar duplicarlas.")
        reference_start = reference_start or min(read_date(row["start"], "Inicio") for row in activities)
        reference_end = reference_end or max(read_date(row["end"], "Fin") for row in activities)
        if any(read_date(row["start"], "Inicio") < reference_start or read_date(row["end"], "Fin") > reference_end for row in activities):
            raise ValueError("Hay actividades fuera de las fechas generales del cronograma. Corrija el archivo.")
        lective = math.fsum(row["source_hours"] for row in blocks if row["phase"] not in {"Inducción", "Etapa productiva"})
        for summary in summaries:
            if summary["stage"] == "ETAPA LECTIVA" and not math.isclose(lective, summary["hours"]):
                warnings.append(f"Los bloques lectivos suman {lective:g} h; el resumen declara {summary['hours']:g} h. Diferencia: {summary['hours'] - lective:g} h. No se distribuye ni se corrige automáticamente.")
        for block in blocks:
            block.pop("identity")
        return {"schema_version": 2, "program": program, "program_key": name_key(program), "project": project,
                "source_name": filename, "source_digest": sha256(content).hexdigest(), "reference_start": reference_start.isoformat(),
                "reference_end": reference_end.isoformat(), "blocks": blocks, "activities": activities,
                "summaries": summaries, "warnings": list(dict.fromkeys(warnings))}
    finally:
        book.close()
