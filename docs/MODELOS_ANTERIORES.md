# Sistema de Planeación Indicativa SENA

Aplicación Python y Streamlit para planear la siguiente vigencia a partir de la meta de aprendices, las fichas que continúan y los instructores del centro. SQLite conserva la última carga y su planeación completa, incluso al cerrar la aplicación.

## Iniciar

Requiere Python 3.11 o superior. En Windows puede abrir `iniciar.bat`, o ejecutar:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

SQLite está incluido con Python; no necesita instalar un servidor de base de datos.

## Flujo de trabajo

Todos los campos están en el bloque **Preparar la planeación**, sin formularios repartidos en la barra lateral.

1. Seleccionar **Cargar un archivo Excel** o, si ya existe una ejecución, **Usar datos guardados**. No hay carga de reportes incluidos ni archivos locales seleccionados automáticamente.
2. Revisar las especialidades y los instructores detectados en la vista previa.
3. Ingresar la vigencia (inicialmente el próximo año) y las dos metas de aprendices nuevos: **Técnico** y **Tecnólogo**. Cada meta se convierte en fichas por separado.
4. Ajustar los parámetros de cálculo si corresponde.
5. Cargar el reporte de fichas o usar el reporte guardado. Sin archivo se pueden completar las cantidades manualmente en la tabla. El Excel llena las fichas que pasan y las que terminan por especialidad, nivel y jornada; ambos campos siguen siendo editables. Use una fila por combinación y escriba 0 donde no haya continuaciones; las celdas vacías no se consideran cero.
6. Revisar las **terminaciones por trimestre**, la **proyección automática** y las **horas anuales requeridas**, por nivel y componente. Al cambiar las metas o las fichas se recalculan reposiciones, crecimiento mínimo del 5 %, calendario y capacidad de planta. Puede agregar especialidades sin planta.
7. Pulsar **Ejecutar y guardar planeación**. El botón se habilita con datos válidos, incluso si la proyección debe superar la meta para cumplir la regla.
8. Consultar los resultados y descargar el Excel de la ejecución guardada.

Seleccionar un archivo prepara una vista previa. **El reemplazo de la base de datos ocurre al ejecutar y guardar correctamente**: se borran las especialidades, instructores y resultados anteriores y se inserta la nueva carga en una sola transacción. Si el archivo, la distribución o la escritura fallan, se conserva la última planeación válida. No se mantiene un historial de cargas.

Los resultados y la descarga siempre corresponden a la última ejecución guardada. Si cambia un dato, aparece un aviso de cambios pendientes hasta volver a ejecutar. Al abrir una sesión nueva se recuperan los instructores, los parámetros, la distribución y los resultados desde SQLite, sin volver a cargar el archivo.

La distribución se identifica por el contenido del archivo, por lo que dos reportes con el mismo nombre no comparten las ediciones. Cambiar la meta conserva las continuaciones y terminaciones manuales y actualiza automáticamente las nuevas. No hay botones intermedios ni se ingresan manualmente las fichas nuevas. El total que pasa se obtiene de la suma de las especialidades.

## Importación de fichas actuales

Se incluye `data/reporteFichas_2026_4.xlsx`, con 66 fichas. También puede cargar otro archivo con el mismo formato: primera hoja con encabezados **N°, Número Ficha, Tipo Formación, Jornada y Trimestre**, agrupada por títulos de especialidad.

El sistema toma el año y trimestre calendario del encabezado (por ejemplo, `2026 - Trimestre 4`); ambos son revisables en pantalla. El campo **Trimestre** de cada ficha corresponde al trimestre que está cursando, no al trimestre calendario del reporte.

| Formación y jornada | Duración |
| --- | --- |
| Técnico regular, diurna o mixta | 3 trimestres |
| Tecnólogo, Diurna / Diurna-mañana / Diurna-tarde | 7 trimestres |
| Tecnólogo, Mixta | 9 trimestres |
| O&P / P&O, diurna | 10 trimestres |

La finalización estimada se calcula sumando `duración − trimestre cursado` al período calendario del reporte. La ficha termina al **final** de su último trimestre. Solo pasa si esa finalización cae en el año planeado o después. De las que pasan, se cuentan como terminaciones aquellas que finalizan durante ese año.

Ejemplos para un reporte de 2026-T4 y una planeación de 2027:

- Un Técnico en trimestre 3 termina en 2026-T4: no pasa.
- Un Técnico en trimestre 2 termina en 2027-T1: pasa y termina durante 2027.
- Un Tecnólogo diurno en trimestre 7 no pasa; en trimestre 6 sí pasa.
- Un Tecnólogo mixto en trimestre 9 no pasa; en trimestre 8 sí pasa.
- Un Tecnólogo mixto en trimestre 4 termina en 2028-T1: pasa a 2027, pero no termina en 2027.

**O&P y P&O** se reconocen automáticamente, incluidas las variantes mañana y tarde. Se clasifican como **Diurna O&P**, con 30 horas semanales y 10 trimestres, conservando la diferencia de duración frente a Diurna regular. Esta regla prevalece sobre las selecciones antiguas de 7 o 9 trimestres. El archivo incluido produce **54 continuaciones y 37 terminaciones en 2027**. Las otras jornadas desconocidas siguen requiriendo clasificación explícita.

El detalle por ficha muestra duración, finalización estimada y motivo de continuidad. Las especialidades se vinculan por nombre normalizado (espacios, mayúsculas y tildes), sin mezclar programas por parecido. Los programas del reporte sin planta se agregan a la tabla conservando nivel y jornada. Puede añadir manualmente especialidades ausentes del reporte, indicando esos campos. Para las jornadas especiales, la selección de 7 trimestres corresponde a Diurna (30 h/semana) y la de 9 a Mixta (26 h/semana).

Las correcciones manuales se conservan al cambiar la meta o los parámetros de horas. Cambiar el archivo, su período, la vigencia a planear o la duración de jornadas especiales vuelve a calcular y reemplaza los totales iniciales. La pantalla avisa este comportamiento.

Al ejecutar se guardan en SQLite el reporte normalizado, el cálculo original por ficha y la distribución final corregida. Al abrir otra sesión se recuperan sin necesitar el Excel original. La exportación añade **Origen fichas**, **Detalle fichas importadas** y **Continuaciones calculadas**, separadas de la distribución final. Una carga inválida no permite ejecutar ni reemplaza lo guardado.

## Proyección automática: reposiciones y crecimiento mínimo del 5 %

Las fichas que terminan son un subconjunto de las que pasan, por lo que no pueden superar esa cantidad en una especialidad. Se reemplazan en el trimestre siguiente a su terminación: las que terminan en T4 se reservan para T1 de la siguiente vigencia. Además, se proyecta un crecimiento mínimo del 5 % respecto a las fichas que pasan.

El proceso siguiente se aplica **independientemente para Técnico y Tecnólogo**. Un excedente de Técnico no cubre la meta de Tecnólogo. El mínimo del 5 % se redondea una sola vez por especialidad y nivel, sumando sus jornadas; luego se distribuye entre jornadas según las continuaciones, garantizando las reposiciones de cada fila.

Se calcula primero el mínimo de cada especialidad. Si la meta permite más nuevas, se reparte el saldo según las fichas que pasan, mediante mayores restos. Si la meta no alcanza, **se supera la meta para cubrir todos los mínimos**. Si todas las continuaciones son cero, el saldo se reparte equitativamente entre las especialidades registradas; la pantalla lo indica. Si no existe ninguna especialidad y la meta es positiva, se pide agregar una.

```text
Fichas según meta = CEIL(meta de aprendices / aprendices por ficha)
Crecimiento mínimo por especialidad = CEIL(fichas que pasan × 5 %)
Mínimo de nuevas por especialidad = terminaciones en T1–T3 + crecimiento mínimo
Base de nuevas proyectadas = MAX(fichas según meta, suma de mínimos)
Saldo a distribuir = MAX(fichas según meta − suma de mínimos, 0)
Nuevas por especialidad = mínimo de nuevas + saldo asignado proporcionalmente
Total de nuevas = base + reposiciones adicionales por rotación de nuevas técnicas
Fichas al cierre = fichas que pasan + todas las nuevas − todas las terminaciones (incluidas nuevas)
```

Ejemplo de Tecnólogo: **20 fichas que pasan y 8 que terminan en T2** requieren como mínimo **9 nuevas** (8 reposiciones en T3 + 1 de crecimiento), para mantener 21 activas después de las reposiciones. Si la meta equivale a 2 nuevas, se proyectan 9 y se informa el excedente de 7. Las terminaciones de T4 se muestran como reposiciones pendientes para la siguiente vigencia. Las nuevas fichas técnicas también terminan: una apertura en T1 finaliza en T3 y se reemplaza en T4, aumentando las nuevas si el saldo programado no alcanza.

El crecimiento se redondea **hacia arriba por especialidad** para cumplir el mínimo con fichas enteras: 1 ficha que pasa implica al menos 1 nueva; 21 implican al menos 2. Una especialidad con cero continuaciones tiene crecimiento mínimo cero. Esto puede producir un crecimiento efectivo mayor al 5 %, especialmente en programas pequeños.

La meta ingresada no se modifica. La pantalla, SQLite y el Excel conservan por separado la meta original, sus fichas equivalentes, las nuevas proyectadas, las fichas adicionales sobre la meta y los cupos proyectados. El crecimiento del 5 % es ahora **un mínimo obligatorio**, que reemplaza la guía opcional anterior. Los cálculos de demanda y contratación usan el total realmente proyectado, incluyendo el excedente.

Al abrir una planeación guardada con el método anterior se conservan sus continuaciones y terminaciones. La meta única se muestra inicialmente en Técnico y debe redistribuirse; complete nivel y jornada antes de ejecutar. Si una fila antigua incluye varias combinaciones, divida sus cantidades. Los resultados guardados no se reescriben hasta ejecutar. Si la planeación es tan antigua que no registraba terminaciones, estas comienzan en cero y se deben revisar.

## Formato del reporte

Se lee la primera hoja de un archivo `.xlsx`. Debe contener los encabezados, en este orden:

| Nombre | Documento | Tipo Contrato | Total Horas |
| --- | --- | --- | --- |
| DESARROLLO DE SOFTWARE | | | |
| Ana Pérez | 001234 | Planta | 32 |
| Luis López | 005678 | Contratista | 40 |

Las filas con solo la primera celda diligenciada indican la especialidad de los instructores siguientes. Se permiten títulos antes de los encabezados y encabezados repetidos. Se conservan las especialidades sin instructores y los ceros iniciales de documentos guardados como texto en Excel. Los documentos repetidos se rechazan para evitar contar dos veces la capacidad de una persona.

El tipo `Planta` se reconoce ignorando mayúsculas y espacios externos. Los demás tipos se mantienen como registros no pertenecientes a planta, igual que en el modelo original. Las especialidades que contienen `BILING` o `INTEGRAL` se clasifican como bilingüismo o integralidad; las demás son técnicas.

## Datos persistidos

La base se crea automáticamente en `data/planeacion.sqlite3` en la primera ejecución válida. Las pruebas usan bases temporales independientes.

| Tabla o vista | Información |
| --- | --- |
| `specialties` | Catálogo de especialidades y área, incluidas las agregadas en la distribución. |
| `instructors` | Nombre, documento, especialidad, tipo de contrato, horas programadas y marca de planta de cada instructor. |
| `plant_instructors` (vista) | Consulta directa de los profesores de planta con nombre y especialidad. |
| `execution` | Una única ejecución con fecha UTC y datos JSON: archivo de origen, huella del contenido, vigencia, reglas, distribución y resultados. |

En transversales se distinguen **dotación contractual total**, **contratistas que se prevé conservar** y **contratación adicional**. La disponibilidad de los contratos se edita por área y trimestre; su valor inicial es la plantilla del reporte, como escenario revisable de continuidad. La contratación adicional descuenta esa capacidad además de la planta. La tabla técnica mantiene su cálculo de dotación total después de descontar planta. Las ejecuciones anteriores permanecen identificadas como resultados del cálculo anterior hasta volver a guardar.

## Bilingüismo e integralidad por módulos

El modo predeterminado es **Por módulos**. Se registran horas **por ficha y trimestre de formación**, para cada nivel y jornada; 0 significa que ese trimestre no lleva el componente. No se rellenan horas curriculares inventadas: el reporte de instructores no las contiene. Mientras falten horas requeridas se impide guardar. El modo **Semanal uniforme** se conserva explícitamente como escenario de referencia, con un aviso de que no reproduce la operación por módulos.

Cada cohorte nueva recibe únicamente las horas de los módulos correspondientes a su edad de formación. Para las continuaciones, el reporte de fichas permite calcular esa edad al inicio de la vigencia y descontar módulos ya realizados. Si las cantidades o terminaciones manuales ya no coinciden con el reporte, se solicitan las horas pendientes totales de esas continuaciones por trimestre; nunca se repiten automáticamente todos los módulos. La demanda se divide por las semanas efectivas del trimestre: es una capacidad semanal media, que presupone distribuir la programación durante el trimestre. Las horas restantes de las jornadas de 30/26 horas se asignan a formación técnica.

El contraste con el reporte actual separa horas programadas y capacidad según parámetros. En el reporte revisado hay 1 instructor de planta y 7 contratistas de bilingüismo (215 horas programadas), y 1 de planta y 9 contratistas de integralidad (200 horas programadas). Con 32 horas de planta y 40 por contratista, las capacidades son 312 y 392 horas semanales: 97 y 192 horas libres actuales. Estos valores **no son reglas de demanda para el próximo año**.

Por área y trimestre:

```text
Capacidad disponible = planta × jornada de planta + contratos a conservar × horas disponibles
Déficit adicional = MAX(horas de módulos / semanas − capacidad disponible, 0)
Contratistas adicionales = CEIL(déficit adicional / jornada del nuevo contratista)
Horas adicionales del trimestre = déficit adicional × semanas
```

No se compensan déficits de bilingüismo con horas libres de integralidad, ni de un trimestre con otro. Se muestran horas sin utilizar, dedicación equivalente y horas adicionales del año. La cifra anterior de 27, para demandas semanales de 694 y 415 horas, significaba 17 + 10 contratos totales tras descontar planta. Conservando 7 + 9 contratos de 40 horas, ese **escenario uniforme** requiere 11 adicionales, no 27. El resultado del modelo modular depende de las horas curriculares reales; no se fuerza a coincidir con la plantilla actual.

SQLite y Excel conservan módulos, horas pendientes, continuidad contractual y resultados. Las hojas añadidas son **Capacidad transversal actual**, **Continuidad transversal**, **Modulos transversales**, **Horas pendientes transversales** y **Modelo de demanda**.

## Reglas de cálculo

Los valores iniciales se definen en `core/config.py` y son editables desde la aplicación:

- 25 aprendices por ficha.
- Diurna: 30 horas semanales por ficha. Referencia uniforme: 6 de bilingüismo, 6 de integralidad y 18 técnicas.
- Mixta: 26 horas semanales por ficha. Referencia uniforme: 4 de bilingüismo, 4 de integralidad y 18 técnicas.
- En el modo modular, las horas transversales provienen del currículo y las pendientes; las técnicas son las restantes.
- 32 horas semanales de capacidad por instructor de planta.
- 40 horas semanales por contratista proyectado.
- 4 trimestres de 12 semanas efectivas: **48 semanas al año**.
- Oferta adicional inicialmente 50 %, 25 %, 15 % y 10 %, editable y con suma de 100 %.

```text
Fichas activas del trimestre = continuaciones sin terminar + cohortes nuevas todavía activas
Horas anuales = SUMA(fichas activas del trimestre × horas semanales por ficha × semanas del trimestre)
Demanda técnica del trimestre = fichas activas de la especialidad × horas técnicas por ficha
Capacidad planta = instructores de planta de la especialidad × horas por instructor
Déficit = MAX(demanda - capacidad planta, 0)
Contratistas requeridos = CEIL(déficit / horas por contratista)
```

Bilingüismo e integralidad se calculan por separado sobre las fichas activas de cada trimestre. El redondeo de contratistas se aplica por especialidad para no compensar déficits entre perfiles diferentes.

La planta se cuenta **una sola vez por especialidad**, compartiendo sus horas entre ambos niveles y jornadas. No se asigna un instructor completo a cada ficha. Con 18 horas técnicas por ficha, un instructor de 32 horas cubre el equivalente a **1,78 fichas**: dos fichas requieren 36 horas y dejan 4 por cubrir. Dos instructores cubren tres fichas (54 horas) y disponen de 10 horas restantes. La tabla muestra demanda, horas atendidas, capacidad equivalente y déficit.

Al ingresar las metas aparece una referencia de **horas anuales** por nivel y jornada regular, según las ofertas trimestrales. Al completar la distribución se sustituye por el total del escenario, incluidas continuaciones, O&P y reposiciones. Los ingresos se consideran al inicio del trimestre y las terminaciones al final. Son horas dentro del año planeado, no las de toda la duración del programa.

La oferta adicional prioriza T1 y se reparte proporcionalmente al tamaño de las especialidades; las reposiciones siguen las terminaciones. La tabla **Terminaciones por trimestre** toma las fechas del Excel y permite corregirlas. Sin fechas se propone un reparto uniforme; las modificaciones del total se reparten siguiendo la proporción original cuando existe. La suma trimestral debe coincidir con el total manual. Cambiar metas o parámetros conserva estas correcciones.

La demanda y contratación se calculan **por trimestre**, sin contar simultáneamente una ficha y su reemplazo. Ejemplo: dos fichas de Tecnólogo, una terminación en T2 y una ficha de crecimiento producen tres activas en cada trimestre. Dos instructores cubren las 54 horas técnicas; sumar las cuatro fichas atendidas en el año produciría erróneamente 72 horas semanales. Se presentan las horas a contratar y la dedicación equivalente por trimestre, además del pico simultáneo de personas, para no interpretar ese pico como contratación anual completa.

El Excel añade **Calendario de fichas**, **Resumen trimestral**, **Terminaciones por trimestre**, **Planta tecnica por trimestre** y **Transversales por trimestre**, además de **Metas por nivel** y **Horas por nivel y jornada**. SQLite conserva el calendario, las correcciones y los resultados anuales. Los resultados antiguos se mantienen hasta volver a ejecutar con las reglas nuevas.

## Estructura y cambios

La aplicación original ya separaba lectura de Excel (`core/excel_parser.py`), reglas (`core/config.py`) y cálculos (`core/planner.py`). La interfaz recalculaba automáticamente en cada interacción, no persistía datos y usaba una clave de editor que no distinguía archivos.

La estructura actual agrega una capa de ejecución validada, persistencia transaccional y presentación de resultados guardados:

```text
app.py                  # Ingreso centralizado, estado del borrador y botón de ejecución
core/
  config.py             # Reglas del escenario
  excel_parser.py       # Lectura y validación del reporte seccionado
  fichas_parser.py      # Lectura del reporte de fichas por especialidad
  ficha_projection.py  # Duración y continuidad por trimestre
  planner.py            # Fórmulas de demanda, capacidad y contratación
  level_planner.py      # Metas independientes, jornadas y capacidad compartida
  calendar_planner.py   # Cohortes, reposiciones, horas anuales y contratación trimestral
  workflow.py           # Validación de la distribución y ejecución completa
  database.py           # Reemplazo atómico y recuperación en SQLite
  export.py             # Excel de la última ejecución
ui/
  ficha_input.py        # Importación, período, jornadas especiales y vista previa
  calendar_input.py     # Terminaciones por trimestre editables y recuperables
  results.py            # Resultados, datos guardados y metodología
data/
  reporteFichas_2026_4.xlsx  # Reporte de fichas incluido
  planeacion.sqlite3    # Se crea al ejecutar; excluida de Git
tests/                  # Parser, cálculo, persistencia, exportación y flujo de interfaz
```

El archivo `config/defaults.json` se conserva como referencia del proyecto original; las reglas efectivas provienen de `PlanningRules` y de los parámetros guardados.

## Verificación

```powershell
py -m pytest -q
```

Las pruebas usan un reporte de instructores anonimizado en `tests/fixtures` (71 instructores, 20 de planta, misma distribución y horas del reporte revisado) y el reporte de 66 fichas. Cubren módulos cobrados una sola vez, módulos pendientes, capacidad actual, continuidad trimestral, contratación adicional, origen de archivos, límites de finalización, O&P/P&O, ofertas escalonadas, 48 semanas, horas anuales, validaciones, SQLite, interfaz y exportación. No requieren archivos personales de Descargas ni modifican la planeación real guardada.
