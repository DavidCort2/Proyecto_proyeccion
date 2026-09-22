# Revisión de competencias y cálculo mensual

> Revisión histórica del modelo mensual anterior. La versión vigente descuenta únicamente planta y proyecta todos los contratos por período; véase `VALIDACION_CONTRATACION.md`. Las columnas de contratistas adicionales de esta revisión ya no forman parte de la interfaz actual.

## Catálogo real corregido

La base local contenía 16 mallas, 89 entradas de competencias y 670 registros de resultados. Había variantes de nombres y textos recortados, como las de Física/Ciencias naturales y Protección ambiental señaladas por el usuario.

La migración dejó **58 competencias únicas y 15 transversales**, conservando los **670 resultados y la suma original de horas**. Las equivalencias mantienen los nombres originales junto a cada resultado. La clasificación automática usa el tipo del Excel; las decisiones manuales registradas prevalecen. Las futuras correcciones, incluso desmarcar una transversal, se conservan al reimportar.

Antes de migrar se guardó `data/planeacion_antes_automatico_mensual.sqlite3`. La ejecución anterior y sus reportes permanecen intactos. Los campos de edición existentes se mantienen.

## Revisión con todos los reportes y mallas guardados

Vigencia 2027, metas de 558 aprendices de Técnico y 2126 de Tecnólogo, 25 aprendices por ficha y 12 semanas por trimestre. Se aplicaron las capacidades y ofertas guardadas, incluyendo las duraciones reales de cada malla.

- 52 fichas que pasan y 116 nuevas proyectadas, incluidos reemplazos y crecimiento.
- 2900 cupos proyectados frente a la meta de 2684, conservando la regla de mínimos y rotación.
- 157764 horas anuales: 113352 técnicas, 15816 de Bilingüismo y 28596 de Integralidad.

| Meses | Horas requeridas en cada mes | Dotación contractual total | Contratistas adicionales |
| --- | ---: | ---: | ---: |
| Enero–marzo | 10480 | 58 | 14 |
| Abril–junio | 12984 | 72 | 25 |
| Julio–septiembre | 14256 | 80 | 33 |
| Octubre–diciembre | 14868 | 85 | 38 |

Las cifras de instructores corresponden a personas simultáneas, no se suman entre meses. La dotación contractual descuenta planta. El adicional supone conservar los contratistas actuales y descuenta su capacidad por perfil: los excedentes de un perfil no compensan déficits de otro.

Se comprobaron **1362 registros de ficha/mes y 4512 asignaciones**. Cada ficha recibe todas sus horas, ninguna capacidad individual se excede y los meses concilian con los trimestres y el total anual. Los instructores pueden compartir su capacidad entre varias fichas del mismo perfil.

## Precisión y alcance del reparto mensual

La edad de formación se calcula desde el reporte para las continuaciones y desde la oferta de ingreso para las nuevas. Solo se cuentan resultados del trimestre de formación correspondiente, hasta su terminación; una oferta tardía no recibe horas anteriores a su ingreso.

Los Excel proporcionan horas semanales por trimestre, sin fechas diarias. Se mantienen los supuestos existentes de ingreso al inicio y terminación al final del trimestre. Las 12 semanas efectivas se distribuyen en cuatro semanas por mes. La propuesta de carga por instructor no es un horario diario y presupone cobertura dentro de los perfiles del reporte.

Las equivalencias de nombre del programa Órtesis/Prótesis también se verificaron. O&P usa la malla diurna correspondiente solo cuando confirma diez trimestres y no hay una malla O&P explícita.

## Reproducir y consultar

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validate_curricula.py
```

La revisión exportada está en `data/validaciones/planeacion_revision_mensual.xlsx`. Contiene totales, demanda por ficha/mes, capacidad de cada instructor, contratación por perfil, distribución de horas y sus supuestos. No reemplaza la última ejecución: al ejecutar desde la aplicación se guarda el mismo cálculo con los parámetros que se estén mostrando.
