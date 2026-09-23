# Contratación completa por períodos

> Revisión histórica de `curricula_v3`. El presupuesto de fichas cambió en `curricula_v4`: véase `VALIDACION_META_Y_REINICIO.md`. Los resultados de 85 contratistas documentados aquí correspondían al modelo anterior y no se utilizan para calcular nuevas planeaciones.

La versión `curricula_v3` descuenta exclusivamente la capacidad de planta. El reporte de instructores permanece como origen, pero sus contratistas actuales no cubren la demanda proyectada ni se muestran como personal disponible. Las horas de cada ficha siguen su malla y trimestre de formación.

## Comprobación con la base local

Se recalculó la vigencia 2027 con los dos reportes, las 16 mallas y los parámetros guardados: 12 semanas por trimestre, 32 horas semanales por planta y 40 por contratista. Se conservaron 52 fichas que pasan, 116 nuevas y 157764 horas anuales.

| Trimestre | Fichas activas | Horas trimestrales | Contratistas técnicos | Bilingüismo | Integralidad | Total de contratistas |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 | 91 | 31440 | 40 | 5 | 13 | 58 |
| T2 | 112 | 38952 | 51 | 8 | 13 | 72 |
| T3 | 123 | 42768 | 56 | 8 | 16 | 80 |
| T4 | 128 | 44604 | 59 | 10 | 16 | 85 |

Con estas entradas, el pico es **85 contratistas en T4: 59 técnicos y 26 transversales**. La demanda no baja en el segundo semestre. Se necesitan 58 desde enero, 14 más desde abril, 8 más desde julio y 5 más desde octubre, hasta el cierre de la vigencia. El desglose contiene 24 grupos de contratos por perfil e intervalo.

Contratar los 85 desde enero dejaría 27 cupos contractuales por encima de la necesidad en T1, 13 en T2 y 5 en T3. Los inicios escalonados evitan 135 meses-contratista frente a conservar desde enero todos los picos por perfil. Esta unidad mide duración acumulada; no equivale a 135 personas.

Estos valores provienen de las horas de las mallas, las continuaciones, las reposiciones y la distribución de ofertas. El sistema no fuerza que el pico sea al inicio: menos ingresos posteriores no implica automáticamente menos fichas activas ni menos horas.

## Controles

La suite completa terminó con **167 pruebas aprobadas**.

- Se verificaron 1362 registros ficha/mes y 4512 asignaciones. Cada ficha recibe todas sus horas y ninguna asignación supera la capacidad del instructor.
- Los meses concilian con los trimestres y las 157764 horas anuales. Con 12 semanas trimestrales, cada mes representa 4 semanas efectivas.
- Los contratos activos de cada perfil reconstruyen exactamente la necesidad de los cuatro trimestres.
- Agregar contratistas actuales al reporte no modifica horas, capacidad disponible, necesidades, asignaciones ni períodos.
- Se cubren escenarios sin déficit, sin planta, entradas en cualquiera de las cuatro ofertas y períodos separados por trimestres sin necesidad.
- El redondeo mensual y trimestral comparte la misma regla: los residuos de sumar horas decimales no crean un contratista extra cuando la capacidad ya cubre la demanda.
- La exportación y la recuperación desde SQLite conservan los períodos calculados. La interfaz principal presenta la contratación completa, sin el apartado de contratistas actuales ni adicionales.

## Presentación de los resultados

La pestaña **Planeación** abre con un único resumen: total simultáneo de contratistas, trimestre del pico máximo y desglose técnico/transversal del mismo trimestre. En la validación real muestra 85, T4, 59 y 26, respectivamente. Los reportes y campos editables se encuentran en **Reportes y parámetros**; las mallas conservan su propia pestaña.

Debajo del resumen, las tablas están contraídas inicialmente. **Contratistas requeridos y fecha de finalización** identifica cada cupo como instructor técnico o transversal, su perfil y las fechas desde/hasta. Se verificaron las fechas de los 85 cupos reales contra sus registros mensuales de capacidad. Un cupo con necesidad en T1 y T3 tiene dos períodos separados, sin contratación en T2.

Las dos primeras hojas del Excel son **Contratacion requerida** y **Contratistas y fechas**. Se comprueba que reproduzcan el resumen y los períodos individuales de la instantánea guardada. Cambiar los parámetros muestra una vista previa identificada y exige guardar para habilitar su descarga; la ejecución anterior se descarga desde un desplegable separado. Las pruebas verifican que el resumen no se duplique, que los datos de contratistas históricos no se muestren y que todas las tablas del resultado estén dentro de desplegables.

## Ejemplo de necesidad transversal decreciente

Una prueba importa una malla de cuatro trimestres con 40 horas semanales por ficha. Sus horas de Integralidad son 40, 20, 4 y 0; las técnicas son 0, 20, 36 y 40. Ingresan 27 fichas en enero y permanecen activas durante todo el año. Con una planta de 32 horas en cada área y contratistas de 40 horas, los transversales requeridos son **27, 13, 2 y 0**.

La propuesta divide esa necesidad en:

- 14 contratistas de enero a marzo.
- 11 contratistas de enero a junio.
- 2 contratistas de enero a septiembre.

Conservar los 27 todo el año dejaría 25 por encima de la necesidad en T3. El pico técnico de este ejemplo ocurre en T4; no se suma con el transversal de T1 como si fueran simultáneos.

## Alcance temporal y reproducción

Los archivos contienen horas semanales por trimestre. Los ingresos se consideran al inicio y las terminaciones al final de cada trimestre; las semanas efectivas se reparten por igual entre sus tres meses. La asignación comparte capacidad entre fichas del perfil correspondiente y es una propuesta de carga, no un horario diario. Los períodos que llegan a diciembre deben reevaluarse para la siguiente vigencia.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validate_curricula.py
```

El Excel revisado está en `data/validaciones/planeacion_periodos_contratacion.xlsx`. Incluye las hojas de períodos, picos por perfil, contratación trimestral, excesos, demanda mensual y trazabilidad por ficha/competencia. Esta comprobación conserva la última ejecución guardada; el botón **Ejecutar y guardar planeación** actualiza los resultados con la configuración visible.
