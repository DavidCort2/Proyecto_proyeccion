"""Picos, reducciones y períodos continuos de contratación por perfil."""
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
import math


def contracting_windows(counts):
    """Agrupa cupos con los mismos períodos, separando huecos sin demanda.

    [27, 21, 10, 0] => 10 T1–T3, 11 T1–T2, 6 solo T1.
    [3, 1, 3, 1] => 1 T1–T4, 2 solo T1, 2 solo T3.
    Los cupos se conservan durante todo período contiguo donde hagan falta.
    """
    intervals = Counter()
    for slot in range(1, max(counts, default=0) + 1):
        start = None
        for q, required in enumerate([*counts, 0], 1):
            if required >= slot and start is None:
                start = q
            elif required < slot and start is not None:
                intervals[(start, q - 1)] += 1
                start = None
    return [(start, end, count) for (start, end), count in sorted(intervals.items())]


def apply_contracting_periods(execution, rules):
    groups = defaultdict(list)
    for row in execution["monthly_staffing"]:
        if row["Mes número"] in (1, 4, 7, 10):
            groups[(row["Área"], row["Perfil"])].append(row)
    windows, profiles, quarterly_profiles = [], [], []
    year = execution["planning_year"]
    for (area, profile), rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["Trimestre"])
        if [row["Trimestre"] for row in rows] != [1, 2, 3, 4]:
            raise ValueError(f"Faltan trimestres de contratación para {profile}.")
        counts = [row["Contratistas requeridos"] for row in rows]
        peak = max(counts)
        peaks = [q for q, count in enumerate(counts, 1) if count == peak] if peak else []
        intervals = contracting_windows(counts)
        starts, ends = Counter(), Counter()
        for start, end, count in intervals:
            first_month, last_month = start * 3 - 2, end * 3
            windows.append({"Área": area, "Perfil": profile, "Contratistas": count,
                            "Desde T": start, "Hasta T": end,
                            "Inicio": date(year, first_month, 1).isoformat(),
                            "Fin": date(year, last_month, monthrange(year, last_month)[1]).isoformat(),
                            "Meses": (end - start + 1) * 3,
                            "Capacidad por contratista (h/sem)": rules.weekly_contractor_hours,
                            "Capacidad del período (h)": count * (end - start + 1) * rules.weeks_per_quarter * rules.weekly_contractor_hours})
            starts[start] += count
            ends[end] += count
        profiles.append({"Área": area, "Perfil": profile, **{f"T{q}": count for q, count in enumerate(counts, 1)},
                         "Pico de contratistas": peak, "Trimestres de pico": ", ".join(f"T{q}" for q in peaks) or "Sin contratación",
                         "Meses-contratista requeridos": sum(counts) * 3,
                         "Meses-contratista evitables frente al pico anual": (4 * peak - sum(counts)) * 3})
        for row in rows:
            q = row["Trimestre"]
            required = counts[q - 1]
            quarterly_profiles.append({"Área": area, "Perfil": profile, "Trimestre": q,
                                       "Demanda (h/sem)": row["Horas requeridas (h/sem)"],
                                       "Capacidad planta (h/sem)": row["Capacidad planta (h/mes)"] * 3 / rules.weeks_per_quarter,
                                       "Horas a contratar en trimestre": row["Horas a contratar (h/mes)"] * 3,
                                       "Contratistas requeridos": required, "Pico del perfil": peak,
                                       "Exceso si mantiene el pico": peak - required,
                                       "Reducción respecto a T anterior": max(0, counts[q - 2] - required) if q > 1 else 0,
                                       "Contratos que inician": starts[q], "Contratos que finalizan": ends[q]})
            # La propuesta debe reconstruir exactamente la necesidad de cada perfil.
            if sum(count for start, end, count in intervals if start <= q <= end) != required:
                raise ValueError(f"Los períodos de contratación no cubren {profile} en T{q}.")
    quarterly = []
    for q in range(1, 5):
        rows = [row for row in quarterly_profiles if row["Trimestre"] == q]
        by_area = {area: sum(row["Contratistas requeridos"] for row in rows if row["Área"] == area)
                   for area in ("Técnica", "Bilingüismo", "Integralidad")}
        monthly = execution["monthly"][(q - 1) * 3]
        quarterly.append({"Trimestre": q, "Fichas activas": monthly["Fichas activas"],
                          "Horas requeridas": monthly["Horas requeridas"] * 3,
                          "Contratistas técnicos": by_area["Técnica"], "Bilingüismo": by_area["Bilingüismo"],
                          "Integralidad": by_area["Integralidad"],
                          "Contratistas transversales": by_area["Bilingüismo"] + by_area["Integralidad"],
                          "Contratistas requeridos": sum(by_area.values()),
                          "Horas a contratar": math.fsum(row["Horas a contratar en trimestre"] for row in rows),
                          "Contratos que inician": sum(row["Contratos que inician"] for row in rows),
                          "Contratos que finalizan": sum(row["Contratos que finalizan"] for row in rows),
                          "Reducción de contratos respecto a T anterior": sum(row["Reducción respecto a T anterior"] for row in rows),
                          "Exceso técnico si conserva picos por perfil": sum(row["Exceso si mantiene el pico"] for row in rows if row["Área"] == "Técnica"),
                          "Exceso transversal si conserva picos por perfil": sum(row["Exceso si mantiene el pico"] for row in rows if row["Área"] != "Técnica")})
    execution.update(contract_windows=windows, contracting_profiles=profiles, contracting_quarterly=quarterly,
                     contracting_profile_quarterly=quarterly_profiles)
    summary = execution["summary"]
    for key, column in [("total", "Contratistas requeridos"), ("tecnico", "Contratistas técnicos"), ("transversal", "Contratistas transversales")]:
        peak = max(row[column] for row in quarterly)
        summary[f"pico_contratistas_{key}"] = peak
        summary[f"trimestres_pico_{key}"] = [row["Trimestre"] for row in quarterly if row[column] == peak] if peak else []
    summary["meses_contratista_requeridos"] = sum(row["Contratistas requeridos"] * 3 for row in quarterly)
    summary["meses_contratista_evitables"] = sum(row["Meses-contratista evitables frente al pico anual"] for row in profiles)
    execution["contracting_periods_basis"] = (
        "Los períodos indican cuándo se necesita cada grupo de contratistas dentro de la vigencia. "
        "El exceso compara la necesidad de cada trimestre con conservar el pico de cada perfil todo el año. "
        "Los picos de diferentes perfiles pueden ocurrir en trimestres distintos y no se suman como pico simultáneo. "
        "Las fechas siguen los ingresos al inicio y las terminaciones al final de cada trimestre."
    )
    return execution
