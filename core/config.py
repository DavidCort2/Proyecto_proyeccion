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
    mixed_weekly_hours_per_ficha: float = 26.0
    mixed_weekly_bilingual_hours: float = 4.0
    mixed_weekly_integrality_hours: float = 4.0
    weeks_per_quarter: int = 12
    intake_weights: tuple[int, int, int, int] = (50, 25, 15, 10)

    @property
    def mixed_weekly_technical_hours(self) -> float:
        return max(0.0, self.mixed_weekly_hours_per_ficha - self.mixed_weekly_bilingual_hours - self.mixed_weekly_integrality_hours)

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
        if not 1 <= self.weeks_per_quarter <= 13 or int(self.weeks_per_quarter) != self.weeks_per_quarter:
            errors.append("Las semanas efectivas por trimestre deben ser un entero entre 1 y 13.")
        if len(self.intake_weights) != 4 or any(weight < 0 for weight in self.intake_weights) or sum(self.intake_weights) != 100:
            errors.append("Los porcentajes de oferta de los cuatro trimestres deben ser no negativos y sumar 100 %.")
        if self.mixed_weekly_hours_per_ficha <= 0:
            errors.append("Las horas semanales por ficha mixta deben ser mayores que cero.")
        if self.mixed_weekly_bilingual_hours < 0 or self.mixed_weekly_integrality_hours < 0:
            errors.append("Las horas transversales de Mixta no pueden ser negativas.")
        if self.mixed_weekly_bilingual_hours + self.mixed_weekly_integrality_hours > self.mixed_weekly_hours_per_ficha:
            errors.append("Bilingüismo + integralidad no pueden superar las horas de la ficha mixta.")
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
