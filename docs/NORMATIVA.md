# Base normativa y criterios de modelado — Versión 2

Fecha de revisión: 15 de septiembre de 2026.

## Reglas respaldadas

### Jornada de instructores de planta
La **Resolución SENA 642 de 2004** establece que la jornada semanal del grupo ocupacional Instructor es de 42,5 horas y que **32 horas semanales** se dedican a actividades directas de Formación Profesional Integral.

Esta regla sigue siendo aplicada y explicada en el **Concepto SENA 43348 de 2026**.

Fuentes:
- https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_0642_2004.htm
- https://normograma.sena.edu.co/compilacion/docs/concepto_sena_0043348_2026.htm

### Planeación indicativa y contratación
La **Circular SENA 233 de 2025**, referente al Banco de Instructores 2026, indica que los Centros deben identificar necesidades de contratación según metas, programas que continúan de una vigencia a otra y planeación indicativa. También dispone revisar la programación previa y garantizar proyección completa de los instructores de planta antes de justificar contratación por prestación de servicios.

Fuente:
- https://normograma.sena.edu.co/compilacion/docs/circular_sena_0233_2025.htm

### Potencial anual de horas de planta
La **Resolución 3775 de 2025**, modificada en 2026, fijó para la vigencia 2026 una base de **201 días hábiles** para calcular el potencial de horas de instructores de planta.

Fuente:
- https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_3775_2025.htm

## Reglas configurables en esta versión

### 6 horas de bilingüismo
La **Circular 43 de 2025** establece lineamientos actuales sobre competencias lingüísticas e integración transversal del inglés, pero el texto consultado no fija un mínimo universal de seis horas semanales. La **Circular 237 de 2017** sí recomendaba un mínimo de 6 horas semanales para la formación titulada. Por precisión, la V2 usa 6 como valor inicial **editable**.

Fuentes:
- https://normograma.sena.edu.co/compilacion/docs/circular_sena_0043_2025.htm
- https://normograma.sena.edu.co/compilacion/docs/circular_sena_0237_2017.htm

### 6 horas de integralidad y 30 horas semanales por ficha
Se modelan como reglas operativas suministradas para el proyecto. No se codifican como obligación normativa universal porque la revisión realizada no encontró una disposición nacional vigente que obligue exactamente esos valores para todos los programas y diseños curriculares.

## Criterio de cálculo V2
- 25 aprendices por ficha (editable).
- Fichas nuevas = techo(meta proyectada / aprendices por ficha).
- Fichas activas = fichas nuevas + fichas que pasan al siguiente año.
- Demanda semanal total = fichas activas × horas semanales por ficha.
- Demanda técnica = fichas activas × (horas ficha - bilingüismo - integralidad).
- Capacidad base de planta = número de instructores de planta × 32 horas directas semanales.
- Saldo = capacidad de planta - demanda.
- El déficit se calcula por especialidad para evitar compensar perfiles no intercambiables.
- Cada contratista se modela inicialmente con 40 horas semanales, según el criterio operativo suministrado para el proyecto. Este valor es editable y no se presenta como una regla normativa universal.
- Contratistas requeridos por especialidad = techo(déficit de horas / horas semanales del contratista).
- Bilingüismo e integralidad se calculan como bolsas separadas sobre todas las fichas activas.
