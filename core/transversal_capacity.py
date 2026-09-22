"""Compara demanda transversal con planta y continuidad contractual explícita."""
import math

import pandas as pd

AREAS = ["Bilingüismo", "Integralidad"]
CONTINUITY_COLUMNS = ["Área", "Trimestre", "Contratistas a conservar", "Horas por contratista (h/sem)"]


def current_transversal_capacity(instructors, rules):
    rows = []
    for area in AREAS:
        group = instructors.loc[instructors["Área"] == area]
        plant = int(group["Es planta"].sum())
        contractors = len(group) - plant
        programmed = float(group["Horas programadas actuales"].sum()) if "Horas programadas actuales" in group else 0.0
        capacity = plant * rules.weekly_plant_direct_hours + contractors * rules.weekly_contractor_hours
        rows.append({"Área": area, "Planta actual": plant, "Contratistas actuales": contractors,
                     "Horas programadas del reporte (h/sem)": programmed,
                     "Capacidad actual según parámetros (h/sem)": capacity,
                     "Horas libres actuales (h/sem)": max(0.0, capacity - programmed),
                     "Sobrecarga actual (h/sem)": max(0.0, programmed - capacity)})
    return pd.DataFrame(rows)


def suggested_continuity(instructors, rules):
    return pd.DataFrame([{"Área": row["Área"], "Trimestre": quarter,
                          "Contratistas a conservar": row["Contratistas actuales"],
                          "Horas por contratista (h/sem)": float(rules.weekly_contractor_hours)}
                         for row in current_transversal_capacity(instructors, rules).to_dict("records")
                         for quarter in range(1, 5)])


def validate_continuity(frame, instructors, rules):
    if not set(CONTINUITY_COLUMNS).issubset(frame.columns) or len(frame) != 8:
        raise ValueError("Indique la continuidad de ambas áreas transversales en los cuatro trimestres.")
    result = frame[CONTINUITY_COLUMNS].copy()
    for column in CONTINUITY_COLUMNS[1:]:
        numbers = pd.to_numeric(result[column], errors="coerce")
        if numbers.isna().any() or not numbers.map(math.isfinite).all() or (numbers < 0).any():
            raise ValueError("La continuidad transversal debe tener cantidades y horas no negativas.")
        if column != CONTINUITY_COLUMNS[-1] and (numbers % 1 != 0).any():
            raise ValueError("Los trimestres y contratistas a conservar deben ser enteros.")
        result[column] = numbers.astype(float if column == CONTINUITY_COLUMNS[-1] else int)
    expected = {(area, q) for area in AREAS for q in range(1, 5)}
    if set(result[["Área", "Trimestre"]].itertuples(index=False, name=None)) != expected:
        raise ValueError("Use una sola fila por área transversal y trimestre.")
    current = current_transversal_capacity(instructors, rules).set_index("Área")["Contratistas actuales"]
    if (result["Contratistas a conservar"] > result["Área"].map(current)).any():
        raise ValueError("No puede conservar más contratistas que los registrados en esa área. El faltante se calcula como adicional.")
    if (result["Horas por contratista (h/sem)"] > rules.weekly_contractor_hours).any():
        raise ValueError("Las horas disponibles no pueden superar la jornada semanal del contratista.")
    return result.sort_values(["Área", "Trimestre"], ignore_index=True)


def apply_transversal_capacity(execution, instructors, rules, continuity=None):
    continuity = validate_continuity(suggested_continuity(instructors, rules) if continuity is None else continuity, instructors, rules)
    frame = pd.DataFrame(execution["transversal_quarterly"]).merge(continuity, on=["Área", "Trimestre"], validate="one_to_one")
    frame["Capacidad contratos conservados (h/sem)"] = frame["Contratistas a conservar"] * frame["Horas por contratista (h/sem)"]
    frame["Capacidad disponible (h/sem)"] = frame["Capacidad planta (h/sem)"] + frame["Capacidad contratos conservados (h/sem)"]
    frame["Déficit adicional (h/sem)"] = (frame["Demanda (h/sem)"] - frame["Capacidad disponible (h/sem)"]).clip(lower=0)
    frame["Horas sin utilizar (h/sem)"] = (frame["Capacidad disponible (h/sem)"] - frame["Demanda (h/sem)"]).clip(lower=0)
    frame["Contratistas adicionales"] = frame["Déficit adicional (h/sem)"].map(lambda hours: math.ceil(hours / rules.weekly_contractor_hours))
    frame["Contratistas totales del escenario"] = frame["Contratistas a conservar"] + frame["Contratistas adicionales"]
    frame["Horas adicionales del trimestre"] = frame["Déficit adicional (h/sem)"] * rules.weeks_per_quarter
    frame["Dedicación adicional equivalente"] = frame["Déficit adicional (h/sem)"] / rules.weekly_contractor_hours
    # El cálculo anterior era dotación contractual TOTAL tras descontar solo planta.
    frame = frame.rename(columns={"Contratistas requeridos": "Dotación contractual mínima (jornada completa)",
                                  "Déficit antes de contratar (h/sem)": "Demanda sin cubrir por planta (h/sem)",
                                  "Horas a contratar en trimestre": "Horas contractuales totales del trimestre"})
    execution["transversal_quarterly"] = frame.to_dict("records")
    execution["transversal"] = frame.loc[frame.groupby("Área")["Déficit adicional (h/sem)"].idxmax()].to_dict("records")
    execution["transversal_continuity"] = continuity.to_dict("records")
    execution["transversal_current"] = current_transversal_capacity(instructors, rules).to_dict("records")
    by_quarter = frame.groupby("Trimestre")["Contratistas adicionales"].sum()
    execution["summary"]["transversales_adicionales_pico"] = int(by_quarter.max())
    execution["summary"]["trimestre_pico_adicional_transversal"] = int(by_quarter.idxmax())
    execution["summary"]["horas_adicionales_transversales_anuales"] = float(frame["Horas adicionales del trimestre"].sum())
    for row in execution["quarterly"]:
        group = frame.loc[frame["Trimestre"] == row["Trimestre"]]
        row["transversales_a_conservar"] = int(group["Contratistas a conservar"].sum())
        row["transversales_adicionales"] = int(group["Contratistas adicionales"].sum())
        row["horas_adicionales_transversales"] = float(group["Horas adicionales del trimestre"].sum())
    execution["staffing_basis"] = "transversal_continuity_v1"
    return execution
