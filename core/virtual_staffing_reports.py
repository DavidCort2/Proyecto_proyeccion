"""Presentación de cupos, períodos y evidencia, sin recalcular la demanda."""
from collections import defaultdict
from datetime import date, timedelta

from core.virtual_competencies import teaching_profile
from core.virtual_schedule import lective_activities


def contract_reports(contracts):
    """Un cupo puede necesitarse en varios períodos: no son personas adicionales."""
    grouped = defaultdict(list)
    for row in contracts:
        grouped[row["Tipo"], row["Perfil"], row["Cupo"]].append(row)
    slots, periods = [], []
    for key, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: row["Inicio"])
        gaps = []
        for earlier, later in zip(rows, rows[1:]):
            start = date.fromisoformat(earlier["Fin"]) + timedelta(days=1)
            finish = date.fromisoformat(later["Inicio"]) - timedelta(days=1)
            if start <= finish:
                gaps.append(f"{start.isoformat()} a {finish.isoformat()}")
        slots.append({"Cupo de contratación": rows[0]["Instructor"], "Tipo": key[0], "Perfil": key[1],
                      "N.º de cupo": key[2], "Número de períodos": len(rows),
                      "Períodos requeridos": " · ".join(f"{row['Inicio']} a {row['Fin']}" for row in rows),
                      "Pausas sin contratación": " · ".join(gaps) or "Sin pausas entre períodos",
                      "Última fecha requerida en la vigencia": rows[-1]["Fin"],
                      "Capacidad (h/sem)": rows[0]["Capacidad (h/sem)"],
                      "Fin limitado por vigencia": rows[-1]["Fin limitado por vigencia"]})
        periods.extend({**row, "Período del cupo": f"{i} de {len(rows)}"} for i, row in enumerate(rows, 1))
    return slots, periods


def profile_peak_rows(staffing, rules):
    grouped = defaultdict(list)
    for row in staffing:
        grouped[row["Tipo"], row["Perfil"]].append(row)
    result = []
    for (kind, profile), rows in sorted(grouped.items()):
        peak = max(row["Contratistas requeridos"] for row in rows)
        high = [row for row in rows if row["Contratistas requeridos"] == peak] if peak else []
        load = max(rows, key=lambda row: row["Horas requeridas (h/sem)"])
        quarters = sorted({(date.fromisoformat(row["Inicio"]).month - 1) // 3 + 1 for row in high})
        result.append({"Tipo": kind, "Perfil": profile, "Pico simultáneo de contratistas": peak,
                       "Trimestres del pico": ", ".join(f"T{q}" for q in quarters) or "Sin contratación",
                       "Primer inicio del pico": min((r["Inicio"] for r in high), default=""),
                       "Máxima carga (h/sem)": load["Horas requeridas (h/sem)"],
                       "Fichas en máxima carga": load["Fichas activas"],
                       "Atenciones en máxima carga": load.get("Atenciones activas", load["Fichas activas"]),
                       "Capacidad planta (h/sem)": load["Capacidad planta (h/sem)"],
                       "Capacidad por contratista (h/sem)": rules["weekly_contractor_hours"]})
    return result


def schedule_activity_rows(catalog):
    """Permite contrastar cada actividad reconocida con el Excel, sin duplicar horas."""
    result = []
    for item in catalog["schedules"]:
        for row in lective_activities(item):
            profile = item["program"] if row["teaching_type"] == "Técnico" else teaching_profile(row)
            result.append({"Perfil": profile, "Tipo": row["teaching_type"], "Programa": item["program"],
                           "Competencia": row["competency"], "Código de actividad": row["activity_code"],
                           "Resultado / actividad": row["activity"], "Fase": row["phase"], "Bloque": row["block_id"],
                           "Inicio relativo": row["start_offset"], "Duración": row["duration"], "Unidad": row["duration_unit"],
                           "Archivo": item["source_name"], "Hoja": row["source_sheet"], "Fila": row["source_row"]})
    return result
