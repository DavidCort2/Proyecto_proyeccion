# Revisión de meta, oferta y limpieza de datos

## Causas identificadas

El modelo anterior interpretaba toda la meta como nuevos ingresos, reservaba reposiciones y aplicaba un crecimiento mínimo del 5 % redondeado hacia arriba por programa. Además, agregaba reposiciones de nuevas fichas técnicas por fuera del presupuesto anual: 109 fichas calculadas para las metas terminaban siendo 116 nuevas. Esas nuevas se sumaban a 52 continuaciones.

La versión `curricula_v4` interpreta la meta como aprendices totales de la vigencia, incluidas continuaciones y nuevos ingresos. Esa interpretación queda indicada en los campos y en el Excel. Los aprendices que pasan se estiman con el tamaño configurado de ficha, porque el reporte no contiene matrículas individuales. Las nuevas cubren solo el saldo; no se añade otro 5 % ni reposiciones por fuera del total anual.

Los programas y jornadas reciben una distribución proporcional a sus fichas del reporte mediante mayores residuos. No se obliga a abrir una ficha de crecimiento en cada programa pequeño. La oferta trimestral respeta los porcentajes sobre el total de nuevas de cada nivel.

## Revisión antes del reinicio

Con las metas guardadas de 558 técnicos y 2126 tecnólogos, y 25 aprendices por ficha:

| Nivel | Fichas que pasan | Aprendices que pasan estimados | Saldo de aprendices | Fichas nuevas |
| --- | ---: | ---: | ---: | ---: |
| Técnico | 8 | 200 | 358 | 15 |
| Tecnólogo | 44 | 1100 | 1026 | 42 |
| Total | 52 | 1300 | 1384 | 57 |

Los 57 grupos nuevos ofrecen 1425 cupos. Sumados a las continuaciones, son 2725 aprendices estimados; la diferencia respecto de 2684 se debe al redondeo de fichas completas por nivel.

| Trimestre | Fichas activas | Horas trimestrales | Técnicos de contrato | Transversales de contrato | Total de contratistas |
| --- | ---: | ---: | ---: | ---: | ---: |
| T1 | 81 | 27780 | 33 | 16 | 49 |
| T2 | 87 | 29808 | 38 | 16 | 54 |
| T3 | 85 | 29124 | 36 | 16 | 52 |
| T4 | 69 | 23880 | 29 | 13 | 42 |

Las horas anuales pasan de 157764 a 110592. Se verificaron 966 registros ficha/mes y 3228 asignaciones; cada ficha recibe sus horas y ninguna capacidad de instructor se excede. Los contratistas se obtienen del déficit después de planta por perfil; la cifra de 68 instructores del reporte no se utiliza como condición, límite ni objetivo del cálculo.

El pico resulta en T2, aunque T1 concentra más ingresos. Coinciden continuaciones con nuevas fichas que aún no terminan. Se conserva ese resultado de las mallas y las fechas, sin imponer que enero tenga el máximo. Los 60 períodos individuales no se suman como personas simultáneas: el pico concurrente es 54.

## Controles y alcance

La suite completa aprobó 179 pruebas. El flujo de reinicio se comprueba también en una sesión abierta: se invalidan los identificadores de carga, se borran las metas anteriores y se permite importar otra vez desde cero.

- Meta cubierta por continuaciones: cero nuevas, conservando sus horas pendientes.
- Meta de 1050 aprendices con 40 fichas que pasan: solo dos nuevas; un programa con una ficha no recibe crecimiento obligatorio.
- Una nueva que termina en T3 deja de consumir horas en T4 y no crea una reposición no presupuestada.
- Todos los ingresos de las ofertas suman exactamente el presupuesto anual por nivel y perfil.
- Las continuaciones reciben su edad de formación correcta; cada nueva comienza en el trimestre 1 de la malla desde su oferta.
- Las horas mensuales, trimestrales, anuales y las asignaciones concilian; las fechas individuales reconstruyen la necesidad de cada mes.
- El reinicio vacía las tablas y una sesión ya abierta pierde sus cargas y metas anteriores al recargar; se comprueba que se puedan cargar mallas nuevas después.

Las fechas siguen el modelo indicativo de ingresos al inicio y terminaciones al final de cada trimestre. Las semanas efectivas se distribuyen entre sus tres meses. El tamaño de las fichas es una estimación configurable, no matrícula real por grupo.

Los datos numéricos de esta revisión son evidencia previa a la limpieza y no son entradas ni valores iniciales del sistema. Después del reinicio deben cargarse nuevamente las mallas y los dos reportes, e ingresarse las metas finales.

El reinicio solicitado se ejecutó y verificó: cero filas en ejecución, instructores, especialidades, mallas, resultados, competencias y metadatos curriculares; integridad SQLite correcta y sin referencias rotas. Se eliminaron las dos bases de respaldo anteriores y los Excel generados de validaciones previas. Los Excel de origen del usuario no se modificaron.
