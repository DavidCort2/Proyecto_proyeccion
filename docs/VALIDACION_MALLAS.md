# Validación de la planeación por mallas

> Este documento conserva las comprobaciones de la primera implementación. La revisión actual, con clasificación automática y cálculo mensual, está en [VALIDACION_AUTOMATICA.md](VALIDACION_AUTOMATICA.md).

Se digitalizaron las dos mallas suministradas en `data/planeacion.sqlite3`. Las competencias se dejaron técnicas por defecto. Se conservó la ejecución anterior y se creó la copia `data/planeacion_antes_mallas.sqlite3` antes de importar.

## Datos comprobados en los Excel originales

| ADSO | Trimestres | Registros de resultados | Horas por semana en cada trimestre | Horas por ficha con 12 semanas/trimestre |
| --- | ---: | ---: | ---: | ---: |
| Diurna | 7 | 44 | 30 | 2520 |
| Mixta | 9 | 45 | 26 | 2808 |

Las dos mallas reúnen **89 registros de resultados y 18 competencias únicas**. Los resultados y sus horas se conservan aunque la misma competencia aparezca en varios trimestres.

## Caso controlado de cálculo

Reporte 2026-T4 con una ficha ADSO diurna cursando T6 y una mixta cursando T8. Ambas pasan a 2027 y terminan en T1, cursando respectivamente T7 y T9. Se configura meta de 100 aprendices de Tecnólogo, 25 por ficha, 12 semanas y oferta adicional concentrada en T1.

La proyección da dos fichas nuevas en T1 y dos reposiciones en T2, una por jornada en cada oferta. Se mantienen dos fichas activas diurnas y dos mixtas durante los cuatro trimestres.

```text
Horas semanales = 2 × 30 + 2 × 26 = 112
Horas anuales = 112 × 12 × 4 = 5376
Horas pendientes de las dos continuaciones = (30 + 26) × 12 = 672
```

Con todas las competencias técnicas y un instructor técnico de planta compartido entre jornadas:

```text
Capacidad de planta = 32 horas/semana
Déficit = 112 − 32 = 80 horas/semana
Dotación contractual técnica = techo(80 / 40) = 2 por trimestre
```

Al marcar únicamente **INGLES** como transversal de Bilingüismo, el mismo escenario conserva 5376 horas totales y distribuye **408 horas de inglés y 4968 técnicas**. Esta clasificación se usó solo en pruebas temporales; no se seleccionaron transversales en la base del usuario.

Otra comprobación: si las dos fichas del reporte ya terminaron y se abren dos nuevas en T4, una de cada jornada, la vigencia recibe únicamente **672 horas**, no un año completo de formación.

## Comprobaciones automatizadas

La suite completa pasó con **133 pruebas**. Incluye 21 nuevas pruebas de motor e interfaz curricular, además de las regresiones existentes.

- Lectura de ambas mallas, conservación de resultados, trimestres y horas.
- Catálogo único, clasificación técnica inicial y selección transversal global.
- Reimportación sin duplicados y conservación de decisiones anteriores.
- Rechazo de horas inválidas, trimestres incompletos y lotes inválidos, sin sustituir datos válidos.
- Cálculo por edad de las continuaciones, ofertas, jornadas y duración real de la malla.
- Capacidad de planta compartida, redondeo de contratistas y suma de horas.
- Guardado, reapertura y cambios pendientes en Streamlit.
- Instantánea de la clasificación y mallas de cada ejecución, sin alterar descargas anteriores.
- Exportación de 89 resultados y trazabilidad cuya suma coincide con las horas calculadas.
- Bloqueo de la ejecución cuando falta una malla necesaria.

## Cobertura del reporte actual

Las mallas ADSO cubren sus jornadas Diurna y Mixta. El reporte guardado contiene otras **13 combinaciones sin malla**:

| Programa | Jornadas faltantes |
| --- | --- |
| Aseguramiento metrológico industrial | Diurna, Mixta |
| Control de la seguridad digital | Diurna |
| Desarrollo creativo de productos para la industria | Diurna, Mixta |
| Desarrollo de componentes mecánicos | Diurna, Mixta |
| Desarrollo y adaptación de prótesis y órtesis | Diurna, Diurna O&P |
| Dibujo mecánico | Diurna |
| Diseño e integración de automatismos mecatrónicos | Diurna, Mixta |
| Programación de software | Diurna |

La interfaz muestra estos faltantes. No se ejecutó ni reemplazó la planeación completa del centro con horas inventadas: se requiere cargar esas mallas y escoger las competencias transversales para obtener el nuevo resultado completo.
