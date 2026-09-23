# Auditoría del cálculo automático

El flujo que ejecuta `app.main` no contiene una tabla «meta → número de instructores», cuotas mínimas de contratación ni una cantidad de referencia de contratistas. Los resultados se calculan desde las entradas. Las cifras de los casos de prueba de este documento no son reglas del sistema.

## Recorrido y procedencia

| Dato o decisión | Procedencia y uso |
| --- | --- |
| Meta total por nivel | Valor ingresado; incluye continuaciones y nuevos ingresos. No se añade crecimiento adicional. |
| Fichas, programa, nivel, jornada y trimestre cursado | Filas originales del reporte de fichas; no se reutilizan cantidades calculadas de una ejecución anterior. |
| Duración y horas por competencia/trimestre | Malla del programa y jornada. No se rellenan con duraciones ni horas nominales. |
| Clasificación técnica/transversal | Clasificación del catálogo, propuesta desde las mallas y editable por el usuario. |
| Aprendices por ficha | Parámetro visible. El reporte no contiene matrícula individual; las continuaciones se estiman con este tamaño. |
| Distribución de nuevas fichas entre programas | Participación observada en el reporte, redondeada conservando el total; sin mínimos por programa. |
| Trimestres de ingreso | Porcentajes de oferta configurados; no se fuerza un pico en T1. |
| Planta disponible | Registros del Excel marcados como planta y su perfil. Los contratistas actuales no fijan ni reducen la contratación proyectada. |
| Capacidad semanal por instructor | Parámetros visibles de planta y contratista; las horas programadas históricas no son la capacidad disponible. |
| Semanas efectivas | Parámetro visible, distribuido entre los tres meses de cada trimestre. No se inventan horarios diarios. |

```text
Aprendices que pasan = fichas que pasan × aprendices por ficha configurados
Fichas nuevas = techo(máximo(meta − aprendices que pasan, 0) / aprendices por ficha)
Horas del período = suma de las horas de la malla que corresponde cursar a cada ficha
Capacidad de planta del perfil = número de planta del perfil × capacidad configurada
Déficit del perfil = máximo(horas requeridas − capacidad de planta, 0)
Contratistas del perfil = techo(déficit / capacidad por contratista)
Total del período = suma de contratistas de todos los perfiles en ese mismo período
Pico anual = máximo de los totales de los períodos
```

La capacidad y la demanda se comparan en la misma unidad: semanal, mensual o trimestral. La capacidad de una persona se comparte entre sus fichas y se cuenta una sola vez. No se presupone que la capacidad libre de otro perfil pueda cubrir un perfil distinto. El redondeo a personas y fichas completas explica saltos discretos; no implica cuotas prefijadas para ciertas metas.

## Controles añadidos

- `execute_curriculum_plan` arma directamente fichas, terminaciones, calendario curricular, asignaciones mensuales y períodos de contratación; no llama a `execute_level_plan` ni al planificador histórico.
- La validación curricular solo considera los parámetros efectivos. Las referencias de horas de jornada no intervienen siquiera en cálculos intermedios de demanda.
- Se rechazan metas fraccionarias o negativas, capacidades no finitas o no positivas, porcentajes inválidos y perfiles que no corresponden al reporte.
- Una demanda incompleta no se convierte a cero ni se rellena con horas nominales. El cero explícito de una malla sí es válido.
- La presencia de mallas siempre selecciona la distribución curricular de ofertas; no activa reposiciones del modelo anterior si falta una etiqueta de una ejecución guardada.
- Los valores efectivos y su origen quedan visibles en el detalle de la aplicación y en el Excel exportado.

Los módulos históricos conservan sus reglas para compatibilidad y sus pruebas. No participan en el recorrido automático actual. Una prueba hace fallar cualquier intento de invocar ese recorrido histórico, incluido crecimiento, duraciones o propiedades de horas nominales.

Los valores iniciales de los campos editables continúan existiendo y sí influyen cuando el usuario los conserva. No son un objetivo de contratación oculto: representan supuestos visibles sobre tamaño de ficha, capacidad, semanas y ofertas. Los archivos disponibles no permiten reemplazarlos por datos individuales completos.

## Casos independientes de resultado conocido

Meta 75, una ficha que pasa y dos nuevas en T1; malla con horas semanales 11, 27, 8 y 19; la continuación cursa los trimestres 2, 3 y 4. Con planta de 23 h/sem y contratista de 17 h/sem, la demanda semanal es 49, 62, 35 y 38.

| Cambio, manteniendo la meta 75 | Contratistas T1, T2, T3, T4 |
| --- | --- |
| Caso base: una planta | 2, 3, 1, 1 |
| Malla con el doble de horas | 5, 6, 3, 4 |
| Tres instructores de planta | 0, 0, 0, 0 |
| Capacidad contractual de 31 h/sem | 1, 2, 1, 1 |
| Tamaño de ficha de 20 aprendices | 3, 4, 2, 2 |

También se comprueba que una meta alta con horas curriculares explícitamente en cero no fuerce contrataciones, que las ofertas tardías puedan producir el pico en T4 y que añadir contratistas históricos no modifique el resultado.

## Revisión de los datos guardados

Se recalculó en memoria la ejecución de 2027 usando sus entradas guardadas: 17 mallas, 69 fichas de origen, 20 registros de planta, 11 semanas efectivas por trimestre y metas de 558 técnicos y 2126 tecnólogos. No se reemplazó la ejecución guardada ni se modificaron sus archivos.

| Escenario de comprobación | Horas anuales | Contratistas T1, T2, T3, T4 | Pico |
| --- | ---: | --- | ---: |
| Entradas guardadas | 102058 | 49, 54, 51, 40 | 54 |
| Referencias nominales en cero | 102058 | 49, 54, 51, 40 | 54 |
| Horas de todas las mallas multiplicadas por 1,5, solo en memoria | 153087 | 79, 86, 81, 66 | 86 |
| Capacidad contractual multiplicada por 1,5, solo en memoria | 102058 | 37, 38, 35, 30 | 38 |

El escenario base conservó los resultados guardados. Las comprobaciones conciliaron horas por ficha, horas asignadas, capacidad por persona, períodos de contratación y picos. Estos números describen esa ejecución concreta; no son expectativas para cargas futuras.

Validación final: **245 pruebas aprobadas**, incluidas 31 comprobaciones nuevas de independencia respecto de reglas históricas, sensibilidad a las entradas y rechazo de datos incompletos o inválidos.
