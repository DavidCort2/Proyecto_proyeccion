from dataclasses import dataclass


@dataclass(frozen=True)
class PlanningRules:
    """Reglas de cálculo editables del escenario de planeación."""

    learners_per_ficha: int = 25
    weekly_hours_per_ficha: float = 30.0
    weekly_bilingual_hours: float = 6.0
    weekly_integrality_hours: float = 6.0
    weekly_plant_direct_hours: float = 32.0
    weekly_contractor_hours: float = 40.0

    @property
    def weekly_technical_hours(self) -> float:
        value = (
            self.weekly_hours_per_ficha
            - self.weekly_bilingual_hours
            - self.weekly_integrality_hours
        )
        return max(0.0, value)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.learners_per_ficha <= 0:
            errors.append("Los aprendices por ficha deben ser mayores que cero.")
        if self.weekly_hours_per_ficha <= 0:
            errors.append("Las horas semanales por ficha deben ser mayores que cero.")
        if self.weekly_plant_direct_hours <= 0:
            errors.append("Las horas directas semanales de planta deben ser mayores que cero.")
        if self.weekly_contractor_hours <= 0:
            errors.append("Las horas semanales por contratista deben ser mayores que cero.")
        if self.weekly_bilingual_hours < 0 or self.weekly_integrality_hours < 0:
            errors.append("Bilingüismo e integralidad no pueden tener horas negativas.")
        if self.weekly_bilingual_hours + self.weekly_integrality_hours > self.weekly_hours_per_ficha:
            errors.append(
                "Bilingüismo + integralidad no pueden superar las horas semanales de la ficha."
            )
        return errors
