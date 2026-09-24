# Validación de Titulada presencial y virtual

## Separación

Presencial conserva `data/planeacion.sqlite3`, sus mallas y su motor. Virtual usa `data/planeacion_virtual.sqlite3` y el motor `virtual_schedule_v3`. Las pruebas de interfaz verifican que guardar, cambiar de modalidad, restaurar borradores y limpiar una modalidad no modifican la otra. Se conserva la descarga de ejecuciones anteriores.

## Datos de origen

Copias de los archivos recibidos en `tests/fixtures/virtual_schedules`:

| Archivo de prueba | Duración lectiva | Actividades | Competencias, incluida inducción |
| --- | ---: | ---: | ---: |
| `adso_fases.xlsx` | 21 meses | 98 | 19 |
| `ciberseguridad_fases.xlsx` | 9 meses | 56 | 15 |

Hay 24 competencias únicas entre ambos: 23 códigos y la inducción común. Los códigos provienen del Excel. Se sugiere clasificación transversal por el texto de las actividades; el usuario puede corregirla globalmente y la decisión se conserva al importar versiones nuevas. La tabla muestra una actividad de referencia, no un título oficial inferido del código.

ADSO contiene una actividad exactamente repetida, contada una sola vez. Sus bloques sumaban 19,25 meses frente a 21 declarados. El usuario confirmó que los 1,75 restantes pertenecen a Evaluación con acompañamiento: Evaluación pasa de 1 a 2,75 meses. `config/virtual_programs.json` registra esta decisión y el lector calcula la diferencia desde el total declarado; no contiene cantidades de fichas ni de instructores.

En Ciberseguridad, la fila 32 contiene texto incompleto sin código, después de una actividad matemática y antes de una de inglés. Se conserva como nota del bloque sin adjudicarlo a una competencia ni generar otra carga. Las competencias codificadas del bloque sí se extraen.

Las filas sin proyecto ni duración se vinculan por su código GA al único bloque que contiene otros registros identificados de ese GA. Esto ubica correctamente la fila 32 de ADSO en Planeación, las filas 61–63 de ADSO en Ejecución y la fila 34 de Ciberseguridad en Ejecución. No se usa una lista de filas en el motor: si el código no permite identificar un bloque único, el archivo requiere corregirse en vez de asignarlo por proximidad.

La copia anterior `cronograma_adso.xlsx` conserva cobertura de celdas combinadas y fases partidas. Sus horas estimadas se mantienen como referencia de origen. Las fechas de los archivos, las horas estimadas del aprendiz y las antiguas horas docentes manuales no se usan para proyectar carga.

## Reglas y supuestos visibles

- La fecha de terminación ingresada es el último día de etapa lectiva. Desde el día siguiente se reconstruyen los límites de fases hacia atrás usando sus duraciones. Se rechazan continuaciones cuyo fin lectivo ya pasó o cuyo inicio estimado es posterior al comienzo de la vigencia.
- Las fichas nuevas comienzan el primer día de cada trimestre calendario. Son fechas indicativas, no fechas oficiales de convocatorias.
- La meta incluye aprendices de continuaciones y nuevas. El saldo se divide por aprendices por ficha, redondeado hacia arriba por nivel. Pesos de programas y porcentajes de oferta distribuyen ese total sin aumentarlo.
- La regla de atención es 2 horas diarias por ficha de lunes a viernes: 10 semanales para el conjunto técnico activo y 10 por cada competencia transversal activa. Se agrupan las actividades repetidas de la misma competencia y bloque. Las técnicas comparten el perfil del programa.
- Sin calendario de festivos cargado, no se descuentan festivos. Las fracciones de mes se prorratean en días entre aniversarios mensuales; se redondea el límite hacia arriba. Los resultados son una proyección de capacidad, no una agenda diaria de clases.
- Cada instructor toma fichas completas de su perfil. Planta de 32 h/sem cubre 3 fichas; contratista de 40 h/sem cubre 4. Dos personas de planta cubren 6 fichas, no 7 mediante suma de horas libres. La cédula única impide contar una persona dos veces.
- La etapa productiva está excluida de duración lectiva, demanda, capacidad y contratos. Los contratos se muestran por intervalos de necesidad dentro de la vigencia; el límite de diciembre no afirma que la ficha termine allí.

## Aritmética comprobada

Tres bloques consecutivos de siete días generan 30 horas por ficha (3 × 5 × 2), aunque el Excel incluya otras horas de referencia. Dos fichas que pasan con fin lectivo 14/01/2027 tienen 20 horas pendientes cada una. Con meta 100 y 25 aprendices por ficha entran dos nuevas: 40 pendientes + 60 nuevas = **100 horas**.

Con bloques de 7, 14 y 7 días, el segundo transversal, una ficha demanda 40 horas. Si hay una persona de planta transversal, solo se requieren contratos técnicos del 01–07/01 y 22–28/01.

Cuatro fichas simultáneas del mismo perfil caben en un contratista; cinco requieren dos. Una persona de planta cubre tres; la cuarta requiere contratación. Cuatro fichas de dos programas que comparten competencia transversal generan 40 h/sem de esa competencia: planta cubre tres y el contratista restante cubre una ficha completa de 10 h/sem.

Las pruebas con ambos archivos reales combinan continuaciones con fechas distintas, ofertas nuevas y planta identificada. Para cada mes se comprueba igualdad entre horas de fichas, horas asignadas a instructores y cobertura de planta más horas a contratar. Ninguna asignación supera la capacidad de su persona. El Excel exporta competencias únicas, fases, contratos, horas por ficha, capacidad y asignaciones mensuales.

## Ejecución de pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`test_virtual_schedules.py` cubre lector, cálculos, clasificaciones, calendario, validación, guardado y exportación. `test_planning_modules_app.py` cubre el flujo de pantalla y aislamiento. La suite completa incluye las pruebas presenciales y sus cálculos de mallas.

`test_virtual_cohort_app.py` verifica el ingreso de diez fichas en un lote con fechas independientes, sus contadores y el cálculo de horas pendientes. También comprueba guardado y reapertura, expansión de grupos antiguos, lotes de distintos programas y conservación de fechas, planta y eliminaciones al agregar más fichas o navegar entre modalidades.
