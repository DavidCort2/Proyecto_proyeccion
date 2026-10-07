"""Cantidades de ingreso virtual editadas, validadas antes de crear las cohortes."""
import math
from numbers import Real

from core.curriculum import name_key

OFFER_COLUMNS = [f"Oferta {i}" for i in range(1, 5)]
MANUAL_BASIS = (
    "Las cantidades de ingreso provienen de la tabla de ofertas guardada. Pueden cambiar el total anual "
    "y tienen prioridad sobre pesos y porcentajes automáticos. Cada ficha inicia sus fases en la fecha "
    "de la oferta elegida. Las continuaciones se conservan y sus aprendices cuentan una sola vez; "
    "la diferencia entre los cupos programados y la meta se muestra por nivel."
)


def normalize_manual_offers(offers, selected, year):
    if not isinstance(offers, dict) or offers.get("planning_year") != year:
        raise ValueError("Las ofertas editadas corresponden a otra vigencia. Restaure la distribución automática.")
    if not isinstance(offers.get("programs"), list):
        raise ValueError("Revise la tabla de ofertas virtuales editadas.")
    counts = {}
    for row in offers["programs"]:
        if not isinstance(row, dict) or not {"Programa", "Nivel", *OFFER_COLUMNS}.issubset(row):
            raise ValueError("Cada fila debe indicar programa, nivel y las cuatro ofertas.")
        key = name_key(row["Programa"])
        if key not in selected or key in counts or name_key(row["Nivel"]) != name_key(selected[key]["Nivel"]):
            raise ValueError("Las ofertas editadas deben corresponder a los programas y niveles incluidos, sin duplicados. Restaure la distribución automática.")
        values = [row[column] for column in OFFER_COLUMNS]
        if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
               or value < 0 or value % 1 for value in values):
            raise ValueError(f"{row['Programa']}: ingrese cantidades enteras no negativas, sin celdas vacías.")
        counts[key] = [int(value) for value in values]
    if set(counts) != set(selected):
        raise ValueError("La tabla editada debe incluir todos los programas seleccionados. Restaure la distribución automática.")
    normalized = {"planning_year": year, "programs": [
        {"Programa": selected[key]["Programa"], "Nivel": selected[key]["Nivel"], **dict(zip(OFFER_COLUMNS, counts[key]))}
        for key in sorted(selected)]}
    return normalized, {(key, offer): count for key, values in counts.items() for offer, count in enumerate(values)}
