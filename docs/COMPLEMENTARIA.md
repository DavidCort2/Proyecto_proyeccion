# Complementaria presencial y virtual

## Referencias oficiales consultadas

Consulta: 7 de octubre de 2026.

- La [Resolución SENA 1-02206 de 2025](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_2206_2025.htm), modificada por la [Resolución 1-01041 de 2026](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_1041_2026.htm), define la formación complementaria y las modalidades presencial, virtual y a distancia. La duración de los programas se trata en su artículo 3, dentro del diseño curricular. No se utiliza la derogada Resolución 2198 de 2019 para imponer límites históricos a la duración promedio.
- La [Resolución SENA 642 de 2004](https://normograma.sena.edu.co/compilacion/docs/resolucion_sena_0642_2004.htm) distingue la jornada de planta de 42,5 horas semanales de las 32 horas destinadas a formación directa. Por eso el campo de capacidad de planta representa formación, no la jornada laboral total.

Las **10 horas semanales por curso** y las **40 horas por contratista** son criterios operativos expresamente definidos por el usuario. No se presentan como obligaciones universales de esas resoluciones. La duración promedio ingresada se usa como carga docente estimada de cada curso; este cálculo no valida el diseño curricular ni sustituye los requisitos de cada programa.

## Cálculo y fechas

Para cada modalidad:

```text
cursos = techo(meta de aprendices / promedio de aprendices por curso)
horas requeridas = cursos × duración promedio en horas
semanas equivalentes por curso = duración promedio / 10
```

El escenario programa cursos de dos horas diarias de lunes a viernes. No se cargó un calendario de festivos, recesos ni disponibilidad de ambientes: las fechas son propuestas de capacidad. Si un curso no termina dentro de la vigencia con esa intensidad, se solicita revisar su duración. Cuando la duración no es múltiplo de dos, la última jornada cuenta solo sus horas restantes, pero conserva una reserva de dos horas para evitar sobreprogramación.

Un curso se asigna completo a un instructor, sin saltos entre días hábiles. Los recursos se utilizan en este orden:

1. Planta propia de la modalidad de Complementaria.
2. Horas libres de los contratistas proyectados de Titulada presencial y virtual, compartidas entre ambas modalidades de Complementaria.
3. Contratación adicional estimada para los cursos restantes, también compartida entre modalidades.

Se proponen primero los cursos de mayor duración; a igual duración se prioriza la modalidad con menor proporción cubierta. Dentro de esa modalidad se elige la primera ventana que permita terminar el curso completo; ante igualdad, el contrato que termina antes. Es una propuesta automática de capacidad, no una garantía de programación óptima de horarios. No se infiere compatibilidad temática a partir de metas y duraciones, porque no se ingresan nombres o competencias de estos cursos.

Los contratos de Titulada solo aportan capacidad durante sus períodos guardados. No se prolongan ni se crean para generar apoyo. En presencial se recupera la intensidad semanal desde la capacidad y asignación mensual de la proyección. En virtual se conservan los intervalos de actividad de cada instructor, incluyendo su apoyo técnico a transversal general: no se utiliza un promedio mensual que esconda un pico.

Las horas ocupadas por Titulada y las reservas de Complementaria nunca pueden superar la capacidad de la misma persona en la misma fecha. La planta de Titulada se excluye completamente. La planta propia de Complementaria mantiene su capacidad programada; las horas de otras actividades se distinguen de las horas que cubren cursos.

El pico conjunto cuenta identificadores únicos en una misma fecha. Si un instructor atiende ambas modalidades, aparece en sus detalles respectivos, pero cuenta una vez en el total conjunto. Cuatro cursos simultáneos de diez horas ocupan las cuarenta horas de un contratista; diez cursos cortos a lo largo del año no implican necesariamente tres contratistas, porque los cupos se reutilizan al terminar cada curso.

## Datos y guardado

`data/planeacion_complementaria.sqlite3` conserva una instantánea conjunta con revisión de escritura. Titulada se consulta en modo lectura. Cada fuente conserva vigencia, fecha de guardado, huella y disponibilidad utilizada para poder revisar el cálculo. Una fuente ausente o de otra vigencia aporta cero horas y se identifica en pantalla.

Las instantáneas virtuales anteriores sin detalle de intervalos se reconstruyen en memoria desde sus cronogramas e inputs guardados. Se comprueba que las asignaciones mensuales coincidan; si cambiaron, se solicita ejecutar y guardar Titulada virtual antes de compartir capacidad. La reconstrucción no modifica esa base.

Las entradas de ambas modalidades se conservan al navegar. Guardar cualquiera recalcula y persiste el escenario conjunto. La descarga solo se habilita si la vista previa coincide con el escenario guardado. Cambiar las fuentes de Titulada obliga a guardar nuevamente Complementaria para actualizar su Excel.

## Validación

`tests/test_complementary.py` comprueba:

- Una misma disponibilidad de Titulada no se reserva dos veces entre modalidades.
- Un tramo sin horas libres impide programar un curso continuo; un promedio mensual no lo oculta.
- Un curso no extiende el contrato de Titulada.
- Un contratista adicional puede atender cuatro cursos simultáneos entre ambas modalidades, contando una sola vez en el pico conjunto.
- Los cursos cortos rotan dentro del año; la contratación no se calcula dividiendo todos los cursos anuales entre cuatro.
- Se cuentan las horas exactas de duraciones fraccionarias y se redondean los cursos completos.
- La planta propia tiene prioridad y la planta de Titulada no participa.
- Entradas inválidas, personas duplicadas y disponibilidades superpuestas se rechazan.
- El guardado es transaccional y el Excel concilia cursos, cobertura y horas.

`tests/test_complementary_app.py` comprueba navegación, borradores, planta, guardado conjunto, descarga, actualización de fuentes y que las bases de Titulada permanezcan intactas. La suite completa mantiene además las pruebas existentes de Titulada presencial y virtual.
