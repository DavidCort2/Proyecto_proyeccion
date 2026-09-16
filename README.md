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

1. Seleccionar **Cargar un archivo Excel**, **Usar reporte incluido** o, si ya existe una ejecución, **Usar datos guardados**.
2. Revisar las especialidades y los instructores detectados en la vista previa.
3. Ingresar la vigencia (inicialmente el próximo año), la meta de aprendices nuevos y las fichas que continúan.
4. Ajustar los parámetros de cálculo si corresponde.
5. Revisar y editar la distribución por especialidad técnica. Puede agregar especialidades sin planta.
6. Pulsar **Ejecutar y guardar planeación**. El botón solo se habilita cuando la distribución coincide con los totales y los parámetros son válidos.
7. Consultar los resultados y descargar el Excel de la ejecución guardada.

Seleccionar un archivo prepara una vista previa. **El reemplazo de la base de datos ocurre al ejecutar y guardar correctamente**: se borran las especialidades, instructores y resultados anteriores y se inserta la nueva carga en una sola transacción. Si el archivo, la distribución o la escritura fallan, se conserva la última planeación válida. No se mantiene un historial de cargas.

Los resultados y la descarga siempre corresponden a la última ejecución guardada. Si cambia un dato, aparece un aviso de cambios pendientes hasta volver a ejecutar. Al abrir una sesión nueva se recuperan los instructores, los parámetros, la distribución y los resultados desde SQLite, sin volver a cargar el archivo.

La distribución se identifica por el contenido del archivo, por lo que dos reportes con el mismo nombre no comparten las ediciones. Cambiar la meta conserva las ediciones de la tabla; **Generar distribución proporcional** las reemplaza por una propuesta acorde con los totales actuales.

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

Se mantienen los contratistas del reporte como referencia, pero **no se descuentan de la necesidad proyectada**. La exportación incluye resumen, reglas, distribución, técnicos, transversales, capacidad de planta, nombres de los instructores de planta y especialidades.

## Reglas de cálculo

Los valores iniciales se definen en `core/config.py` y son editables desde la aplicación:

- 25 aprendices por ficha.
- 30 horas semanales por ficha: 6 de bilingüismo, 6 de integralidad y 18 técnicas.
- 32 horas semanales de capacidad por instructor de planta.
- 40 horas semanales por contratista proyectado.

```text
Fichas nuevas = CEIL(meta de aprendices / aprendices por ficha)
Fichas activas = fichas nuevas + fichas que continúan
Demanda técnica = fichas activas de la especialidad × horas técnicas por ficha
Capacidad planta = instructores de planta de la especialidad × horas por instructor
Déficit = MAX(demanda - capacidad planta, 0)
Contratistas requeridos = CEIL(déficit / horas por contratista)
```

Bilingüismo e integralidad se calculan por separado sobre todas las fichas activas. El redondeo se aplica por especialidad para no compensar déficits entre perfiles diferentes. La propuesta de distribución es proporcional a la planta técnica disponible y debe ajustarse a la oferta real del centro.

## Estructura y cambios

La aplicación original ya separaba lectura de Excel (`core/excel_parser.py`), reglas (`core/config.py`) y cálculos (`core/planner.py`). La interfaz recalculaba automáticamente en cada interacción, no persistía datos y usaba una clave de editor que no distinguía archivos.

La estructura actual agrega una capa de ejecución validada, persistencia transaccional y presentación de resultados guardados:

```text
app.py                  # Ingreso centralizado, estado del borrador y botón de ejecución
core/
  config.py             # Reglas del escenario
  excel_parser.py       # Lectura y validación del reporte seccionado
  planner.py            # Fórmulas de demanda, capacidad y contratación
  workflow.py           # Validación de la distribución y ejecución completa
  database.py           # Reemplazo atómico y recuperación en SQLite
  export.py             # Excel de la última ejecución
ui/
  results.py            # Resultados, datos guardados y metodología
data/
  reporteInstructores_2026_4.xlsx
  planeacion.sqlite3    # Se crea al ejecutar; excluida de Git
tests/                  # Parser, cálculo, persistencia, exportación y flujo de interfaz
```

El archivo `config/defaults.json` se conserva como referencia del proyecto original; las reglas efectivas provienen de `PlanningRules` y de los parámetros guardados.

## Verificación

```powershell
py -m pytest -q
```

Las pruebas cubren la lectura del reporte incluido (71 instructores, 19 de planta), los cálculos existentes, el reemplazo de cargas, la reversión ante fallos de escritura, la recuperación al reiniciar, la validación de la distribución, el cambio de archivo conservando su nombre y la exportación de nombres de planta.
