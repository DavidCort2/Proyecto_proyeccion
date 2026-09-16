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
3. Ingresar la vigencia (inicialmente el próximo año) y la meta de aprendices nuevos.
4. Ajustar los parámetros de cálculo si corresponde.
5. Ingresar **manualmente por especialidad** las fichas que pasan y cuántas de ellas terminan durante la vigencia. Escriba 0 donde no existan continuaciones; las celdas vacías no se consideran cero.
6. Revisar la **proyección automática**. Al cambiar la meta o los datos de una especialidad, se calculan las nuevas necesarias para cubrir reposiciones, crecimiento mínimo del 5 % y las fichas restantes de la meta. Puede agregar especialidades sin planta.
7. Pulsar **Ejecutar y guardar planeación**. El botón se habilita con datos válidos, incluso si la proyección debe superar la meta para cumplir la regla.
8. Consultar los resultados y descargar el Excel de la ejecución guardada.

Seleccionar un archivo prepara una vista previa. **El reemplazo de la base de datos ocurre al ejecutar y guardar correctamente**: se borran las especialidades, instructores y resultados anteriores y se inserta la nueva carga en una sola transacción. Si el archivo, la distribución o la escritura fallan, se conserva la última planeación válida. No se mantiene un historial de cargas.

Los resultados y la descarga siempre corresponden a la última ejecución guardada. Si cambia un dato, aparece un aviso de cambios pendientes hasta volver a ejecutar. Al abrir una sesión nueva se recuperan los instructores, los parámetros, la distribución y los resultados desde SQLite, sin volver a cargar el archivo.

La distribución se identifica por el contenido del archivo, por lo que dos reportes con el mismo nombre no comparten las ediciones. Cambiar la meta conserva las continuaciones y terminaciones manuales y actualiza automáticamente las nuevas. No hay botones intermedios ni se ingresan manualmente las fichas nuevas. El total que pasa se obtiene de la suma de las especialidades.

## Proyección automática: reposiciones y crecimiento mínimo del 5 %

Las fichas que terminan son un subconjunto de las que pasan, por lo que no pueden superar esa cantidad en una especialidad. Todas se reemplazan. Además, cada especialidad crece al menos un 5 % respecto a sus fichas que pasan.

Se calcula primero el mínimo de cada especialidad. Si la meta permite más nuevas, se reparte el saldo según las fichas que pasan, mediante mayores restos. Si la meta no alcanza, **se supera la meta para cubrir todos los mínimos**. Si todas las continuaciones son cero, el saldo se reparte equitativamente entre las especialidades registradas; la pantalla lo indica. Si no existe ninguna especialidad y la meta es positiva, se pide agregar una.

```text
Fichas según meta = CEIL(meta de aprendices / aprendices por ficha)
Crecimiento mínimo por especialidad = CEIL(fichas que pasan × 5 %)
Mínimo de nuevas por especialidad = fichas que terminan + crecimiento mínimo
Total de nuevas proyectadas = MAX(fichas según meta, suma de mínimos)
Saldo a distribuir = MAX(fichas según meta − suma de mínimos, 0)
Nuevas por especialidad = mínimo de nuevas + saldo asignado proporcionalmente
Fichas al cierre = fichas que pasan − fichas que terminan + fichas nuevas
```

Ejemplo con una sola especialidad: **20 fichas que pasan y 8 que terminan** requieren como mínimo **9 nuevas** (8 reposiciones + 1 de crecimiento), para quedar con **21 al cierre**. Si la meta equivale a 2 nuevas, se proyectan 9 y se informa el excedente de 7. Si equivale a 12 nuevas, se proyectan 12 para agotar la meta. Si ninguna termina, el mínimo es 1 nueva. Se supone que las nuevas continúan activas al cierre; no se modelan sus fechas de finalización.

El crecimiento se redondea **hacia arriba por especialidad** para cumplir el mínimo con fichas enteras: 1 ficha que pasa implica al menos 1 nueva; 21 implican al menos 2. Una especialidad con cero continuaciones tiene crecimiento mínimo cero. Esto puede producir un crecimiento efectivo mayor al 5 %, especialmente en programas pequeños.

La meta ingresada no se modifica. La pantalla, SQLite y el Excel conservan por separado la meta original, sus fichas equivalentes, las nuevas proyectadas, las fichas adicionales sobre la meta y los cupos proyectados. El crecimiento del 5 % es ahora **un mínimo obligatorio**, que reemplaza la guía opcional anterior. Los cálculos de demanda y contratación usan el total realmente proyectado, incluyendo el excedente.

Al abrir una planeación guardada con el método anterior se conservan sus continuaciones y terminaciones, y la vista previa se recalcula con la nueva regla. Los resultados guardados no se reescriben hasta ejecutar. Si la planeación es tan antigua que no registraba terminaciones, estas comienzan en cero y se deben revisar.

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

Se mantienen los contratistas del reporte como referencia, pero **no se descuentan de la necesidad proyectada**. La exportación incluye resumen, reglas, distribución proyectada, mínimos de reposición y crecimiento, técnicos, transversales, capacidad de planta, nombres de los instructores de planta y especialidades. Las ejecuciones antiguas siguen exportando su guía original cuando corresponde.

## Reglas de cálculo

Los valores iniciales se definen en `core/config.py` y son editables desde la aplicación:

- 25 aprendices por ficha.
- 30 horas semanales por ficha: 6 de bilingüismo, 6 de integralidad y 18 técnicas.
- 32 horas semanales de capacidad por instructor de planta.
- 40 horas semanales por contratista proyectado.

```text
Fichas nuevas = MAX(CEIL(meta de aprendices / aprendices por ficha), suma de mínimos)
Fichas activas = fichas nuevas + fichas que continúan
Demanda técnica = fichas activas de la especialidad × horas técnicas por ficha
Capacidad planta = instructores de planta de la especialidad × horas por instructor
Déficit = MAX(demanda - capacidad planta, 0)
Contratistas requeridos = CEIL(déficit / horas por contratista)
```

Bilingüismo e integralidad se calculan por separado sobre todas las fichas de la vigencia. El redondeo se aplica por especialidad para no compensar déficits entre perfiles diferentes.

La demanda semanal conserva el modelo de carga de **todas las fichas atendidas en la vigencia (nuevas + continuaciones)**. Las terminaciones sirven para proyectar reposiciones y el saldo al cierre, pero no se restan de las horas de formación: sin fechas de inicio y fin no es posible determinar la carga simultánea ni el pico de contratación. La capacidad de planta se usa para calcular la necesidad de instructores; la distribución de nuevas se basa en las fichas manuales.

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
reporteInstructores_2026_4.xlsx  # Reporte incluido en la raíz (también se admite en data/)
data/
  planeacion.sqlite3    # Se crea al ejecutar; excluida de Git
tests/                  # Parser, cálculo, persistencia, exportación y flujo de interfaz
```

El archivo `config/defaults.json` se conserva como referencia del proyecto original; las reglas efectivas provienen de `PlanningRules` y de los parámetros guardados.

## Verificación

```powershell
py -m pytest -q
```

Las pruebas cubren la lectura del reporte incluido (71 instructores, 19 de planta), los cálculos existentes, las continuaciones manuales, las reposiciones y el crecimiento mínimo por especialidad, el reparto del saldo de la meta, la proyección por encima de la meta, el recálculo automático de horas y contratación, el reemplazo de cargas, la reversión ante fallos de escritura, la recuperación al reiniciar, las interacciones con la tabla y el botón de ejecución, el cambio de archivo conservando su nombre y la exportación.
