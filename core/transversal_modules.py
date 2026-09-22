"""Horas transversales por trimestre de formación y saldo de continuaciones."""
import math
import pandas as pd

from core.calendar_planner import profile_key
from core.ficha_projection import duration_in_quarters

MODULE_KEYS = ["Nivel", "Jornada", "Trimestre de formación"]
HOUR_COLUMNS = ["Bilingüismo (h)", "Integralidad (h)"]
CONTINUING_KEYS = ["Especialidad", "Nivel", "Jornada", "Trimestre"]


def module_template(manual):
    return pd.DataFrame([{**profile, "Trimestre de formación": q, **{c: float("nan") for c in HOUR_COLUMNS}}
                         for profile in manual[["Nivel", "Jornada"]].drop_duplicates().to_dict("records")
                         for q in range(1, duration_in_quarters(profile["Nivel"], profile["Jornada"]) + 1)])


def validate_modules(modules, manual, rules):
    required = MODULE_KEYS + HOUR_COLUMNS
    if not set(required).issubset(modules.columns):
        raise ValueError("Complete las horas de bilingüismo e integralidad por trimestre de formación.")
    result = modules[required].copy()
    expected = set(module_template(manual)[MODULE_KEYS].itertuples(index=False, name=None))
    actual = set(result[MODULE_KEYS].itertuples(index=False, name=None))
    if actual != expected or result.duplicated(MODULE_KEYS).any():
        raise ValueError("Los módulos deben cubrir todos los trimestres de cada nivel y jornada de la planeación.")
    for column in HOUR_COLUMNS:
        values = pd.to_numeric(result[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all() or (values < 0).any():
            raise ValueError("Complete las horas reales de cada módulo; indique 0 donde no se imparta. No se asumen horas para celdas vacías.")
        result[column] = values.astype(float)
    capacity = result["Jornada"].map(lambda shift: rules.mixed_weekly_hours_per_ficha if shift == "Mixta" else rules.weekly_hours_per_ficha) * rules.weeks_per_quarter
    if (result[HOUR_COLUMNS].sum(axis=1) > capacity).any():
        raise ValueError("Los módulos transversales no pueden superar las horas de formación de una ficha en ese trimestre.")
    return result.sort_values(MODULE_KEYS, ignore_index=True)


def continuing_template(manual, endings, modules, imported, planning_year):
    """Solo precarga horas si la continuidad coincide con fichas y fechas conocidas."""
    lookup = modules.set_index(MODULE_KEYS)
    detail = (imported or {}).get("detail", [])
    output = []
    for index, row in manual.iterrows():
        fichas = [item for item in detail if item["Pasa a la vigencia"] and profile_key({**item, "Jornada": item["Jornada de planeación"]}) == profile_key(row)]
        end_counts = [sum(item["Año fin estimado"] == planning_year and item["Trimestre fin estimado"] == q for item in fichas) for q in range(1, 5)]
        accurate = len(fichas) == row["Fichas que pasan"] and end_counts == endings.loc[index, [f"Terminan T{q}" for q in range(1, 5)]].tolist()
        for q in range(1, 5):
            active = int(row["Fichas que pasan"]) - int(endings.loc[index, [f"Terminan T{k}" for k in range(1, q)]].sum())
            hours = {column: 0.0 if active == 0 or accurate else float("nan") for column in HOUR_COLUMNS}
            if accurate:
                for item in fichas:
                    age = int(item["Trimestre actual"]) + (planning_year - imported["report_year"]) * 4 + q - imported["report_quarter"]
                    key = (row["Nivel"], row["Jornada"], age)
                    if key in lookup.index:
                        for column in HOUR_COLUMNS:
                            hours[column] += float(lookup.loc[key, column])
            output.append({**{key: row[key] for key in CONTINUING_KEYS[:-1]}, "Trimestre": q, **hours})
    return pd.DataFrame(output)


def apply_module_hours(calendar, modules, continuing, rules):
    required = CONTINUING_KEYS + HOUR_COLUMNS
    if not set(required).issubset(continuing.columns) or continuing.duplicated(CONTINUING_KEYS).any():
        raise ValueError("Revise las horas pendientes de las continuaciones por trimestre.")
    if set(continuing[CONTINUING_KEYS].itertuples(index=False, name=None)) != set(calendar[CONTINUING_KEYS].itertuples(index=False, name=None)):
        raise ValueError("Las horas de continuaciones deben corresponder a cada especialidad, nivel, jornada y trimestre.")
    remaining = continuing[required].copy()
    for column in HOUR_COLUMNS:
        values = pd.to_numeric(remaining[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all() or (values < 0).any():
            raise ValueError("Complete las horas pendientes de las continuaciones corregidas o manuales; indique 0 si el módulo ya se completó.")
        remaining[column] = values.astype(float)
    result = calendar.merge(remaining, on=CONTINUING_KEYS, validate="one_to_one")
    rates = result["Jornada"].map(lambda shift: rules.mixed_weekly_hours_per_ficha if shift == "Mixta" else rules.weekly_hours_per_ficha)
    if (result[HOUR_COLUMNS].sum(axis=1) > result["Continuaciones activas"] * rates * rules.weeks_per_quarter + 1e-9).any():
        raise ValueError("Las horas pendientes superan las horas disponibles de las fichas que continúan en ese trimestre.")
    lookup = modules.set_index(MODULE_KEYS)
    for _, group in result.groupby(CONTINUING_KEYS[:-1], sort=False):
        starts = group.set_index("Trimestre")["Fichas nuevas"].to_dict()
        for index, row in group.iterrows():
            totals = {column: float(row[column]) for column in HOUR_COLUMNS}
            for start in range(1, int(row["Trimestre"]) + 1):
                age = int(row["Trimestre"]) - start + 1
                key = (row["Nivel"], row["Jornada"], age)
                if key in lookup.index:
                    for column in HOUR_COLUMNS:
                        totals[column] += starts[start] * float(lookup.loc[key, column])
            for name, column in zip(["bilingüismo", "integralidad"], HOUR_COLUMNS):
                result.loc[index, f"Horas {name} del trimestre"] = totals[column]
                result.loc[index, f"Horas {name} (h/sem)"] = totals[column] / rules.weeks_per_quarter
            technical = float(row["Horas totales del trimestre"]) - sum(totals.values())
            if technical < -1e-9:
                raise ValueError("La carga transversal supera la formación total del trimestre.")
            result.loc[index, "Horas técnicas del trimestre"] = max(0.0, technical)
            result.loc[index, "Horas técnicas (h/sem)"] = max(0.0, technical) / rules.weeks_per_quarter
    return result.drop(columns=HOUR_COLUMNS), remaining
