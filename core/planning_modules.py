"""Ubicación estable de los datos de cada modalidad de Titulada."""
from pathlib import Path


def planning_database(base_path, modality):
    base = Path(base_path)
    if modality == "Presencial":
        return base
    if modality == "Virtual":
        return base.with_name(f"{base.stem}_virtual{base.suffix}")
    raise ValueError("Modalidad de Titulada no reconocida.")
