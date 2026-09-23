# Sistema de Planeación Indicativa SENA

Aplicación Python y Streamlit para calcular fichas, horas e instructores por trimestre a partir de las mallas de cada programa y jornada. SQLite conserva las mallas, la clasificación de competencias y la última planeación ejecutada.

## Iniciar

Requiere Python 3.11 o superior. En Windows, abrir `iniciar.bat` o ejecutar:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

La base está en `data/planeacion.sqlite3`. No requiere servidor de base de datos.

## Preparar y ejecutar

1. En **Mallas y competencias**, cargar uno o varios archivos `PROGRAMA - JORNADA.xlsx`, revisar la vista previa y pulsar **Digitalizar y guardar mallas**. Diurna/Diurno y Mixta/Mixto se normalizan. O&P/P&O requiere su propia malla.
2. Revisar **Todas las competencias**. Los títulos equivalentes comparten una única competencia. La carga selecciona automáticamente las transversales según el tipo del Excel; cuando falta, reconoce los títulos transversales conocidos. Se pueden corregir **Transversal** y el área Bilingüismo/Integralidad con los campos existentes. **Guardar clasificación de competencias** conserva esa corrección en futuras importaciones.
3. En **Reportes y parámetros**, cargar los reportes para identificar la planta y las fichas, o recuperarlos de la ejecución guardada.
4. Configurar vigencia, metas totales por nivel (incluyen los aprendices que pasan y los nuevos), aprendices por ficha, horas disponibles de instructores, semanas efectivas y porcentajes de oferta T1–T4. Los porcentajes deben sumar 100 %. La meta ingresada ya debe contener el crecimiento deseado.
5. En **Planeación**, revisar primero el total de contratistas requeridos y el trimestre del pico máximo. Los detalles y las fechas se consultan debajo en tablas desplegables. No se transcriben continuaciones, terminaciones, módulos ni horas pendientes.
6. Pulsar **Ejecutar y guardar planeación** y descargar el Excel. Si cambian las entradas, se muestra una sola vista previa y se deshabilita su descarga hasta guardarla. El archivo de la ejecución anterior se conserva en su propio desplegable.

La pantalla principal muestra el **total de contratistas requeridos**, el **trimestre del pico máximo** y su desglose técnico/transversal. El total es la cantidad máxima simultánea durante la vigencia. Ambos componentes corresponden al mismo trimestre y suman ese total; los picos propios de cada perfil se consultan en el detalle. Si el máximo se repite, se muestran todos sus trimestres.

En **Contratistas requeridos y fecha de finalización**, cada fila identifica un instructor técnico o transversal proyectado, su perfil, fecha desde/hasta y capacidad semanal. Son cupos por contratar calculados con las mallas, después de la cobertura de planta. Un cupo con períodos separados tiene una fila por período. El número de filas puede superar el pico simultáneo si cambian los perfiles durante el año.

Los programas y niveles de la oferta se obtienen del reporte de fichas, incluidas sus combinaciones sin continuaciones. La malla por sí sola no identifica el nivel; para incorporar un programa a la oferta debe estar identificado con su nivel y jornada en el reporte.

## Formato de las mallas

Cada hoja `Trimestre N` representa un trimestre de formación. Deben existir todos desde el 1, sin saltos. Se permiten portadas sin tablas curriculares.

| Columna | Uso |
| --- | --- |
| Competencia | Identidad compartida, ignorando tildes, mayúsculas, puntuación y espacios redundantes. Unifica equivalencias explícitas, abreviaturas y recortes comprobados, como Física/Ciencias naturales, Matemáticas y variantes de protección ambiental. No combina competencias técnicas por parecido. |
| Resultado | Texto completo del resultado de aprendizaje. |
| Horas semanales | Horas por ficha y semana del resultado en ese trimestre. Se admiten decimales y cero explícito. |
| Tipo competencia | Clasificación automática inicial. Las correcciones manuales tienen prioridad. Si distintas mallas discrepan para una misma competencia, una marca transversal explícita prevalece en la propuesta automática. |

Un resultado puede aparecer en varios trimestres y conservar sus horas en cada uno. Solo se deduplica el catálogo de competencias: no se eliminan resultados ni sus apariciones. Horas negativas, vacías, no numéricas o fórmulas sin valor calculado impiden importar el lote.

La importación es transaccional. Dos archivos distintos para el mismo programa/jornada en un lote se rechazan. Volver a importar reemplaza únicamente esa malla y conserva las clasificaciones y demás mallas. Repetir un archivo no duplica los datos.

El catálogo existente se migra automáticamente sin volver a cargar los Excel: se unen las variantes, se conservan todos los resultados, horas y títulos originales, y se recalcula la clasificación automática. El esquema anterior no distinguía valores predeterminados de correcciones: sus marcas transversales positivas se conservan como manuales y los valores técnicos iniciales se revisan según el Excel. Desde esta versión también se conserva una corrección manual que desmarque una transversal.

## Cálculo de las horas

La duración proviene del número de trimestres de la malla. Las continuaciones avanzan desde el trimestre de formación del reporte hasta el inicio de la vigencia. Una ficha termina al final de su último trimestre; las nuevas ingresan al principio del trimestre calendario.

```text
Edad en T1 = trimestre cursado + trimestres calendario hasta la vigencia
Edad de una nueva en Tq = q − trimestre de ingreso + 1
Horas trimestrales = SUMA(fichas de la cohorte × horas semanales del resultado
                         × semanas efectivas del trimestre)
Horas anuales = SUMA(horas de los cuatro trimestres calendario)
Semanas efectivas del mes = semanas efectivas del trimestre / 3
Horas mensuales de cada ficha = horas semanales de su trimestre de formación
                               × semanas efectivas del mes
```

Cada cohorte recibe únicamente los resultados de su edad y jornada. Las continuaciones no repiten trimestres ya cursados. Las horas técnicas se suman desde las competencias técnicas; no son el sobrante de una jornada genérica. Bilingüismo e Integralidad usan las competencias marcadas como transversales.

Las horas diurnas y mixtas de referencia no sustituyen las horas curriculares. Cambiar las semanas efectivas sí cambia las horas trimestrales: los Excel expresan cargas semanales. Se supone programación distribuida durante el trimestre; sin horarios de clase no se estiman picos diarios.

El detalle mensual identifica cada ficha que pasa y crea identificadores de proyección para las nuevas. Solo suma meses a partir de su oferta de ingreso y hasta su terminación. Las semanas trimestrales se reparten por igual: con 12 semanas son 4 por mes. Esta es una distribución indicativa, pues los archivos no contienen fechas diarias, festivos ni horarios de clase. Los totales mensuales deben conciliar con los trimestrales y anuales.

La variante de nombre «Órtesis y prótesis» se vincula con «Prótesis y órtesis». Una ficha O&P/P&O puede usar la malla diurna del mismo programa únicamente si esta confirma diez trimestres y no existe una malla O&P explícita; no toma una diurna regular de siete trimestres.

Si una combinación con demanda no tiene malla, la ejecución se bloquea e identifica programa y jornada. No se completa con otra malla ni cargas genéricas. El diagnóstico inicial de continuaciones sin malla usa las duraciones históricas, sin habilitar el cálculo final.

## Fichas e instructores

La meta es el total de aprendices atendidos durante la vigencia. Cada ficha que pasa cuenta una sola vez para la meta, aunque termine antes de diciembre. Como el reporte no incluye su matrícula, sus aprendices se estiman con el tamaño de ficha configurado. Técnico y Tecnólogo se calculan por separado.

```text
Aprendices que pasan (estimados) = fichas que pasan × aprendices por ficha
Saldo de la meta = MAX(meta total − aprendices que pasan, 0)
Fichas nuevas = CEIL(saldo de la meta / aprendices por ficha)
```

Las nuevas se distribuyen proporcionalmente a la participación de los programas y jornadas en el reporte, con redondeo por mayores residuos y sin un mínimo obligatorio de una ficha por programa. Se eliminó el crecimiento automático del 5 % por programa: la meta final ya incluye el crecimiento deseado. Así se evita aumentar artificialmente programas pequeños.

Los porcentajes de oferta distribuyen todas las fichas nuevas del nivel y conservan exactamente su total anual. Las fichas que terminan no generan reposiciones adicionales por fuera de ese presupuesto. Se identifican las nuevas que cubren salidas, pero no se agregan otra vez. Una ficha nueva termina según la duración de su malla y deja de demandar horas. Si las continuaciones ya cubren la meta, no se abren nuevas automáticamente; se mantienen todas las horas pendientes de las que pasan.

Las horas no se dividen entre aprendices para obtener fichas: la conversión parte de la meta de aprendices. La malla determina después la demanda de las fichas, competencia por competencia y trimestre por trimestre.

```text
Capacidad de planta = instructores del perfil × horas semanales de planta
Déficit = MAX(demanda semanal del trimestre − capacidad de planta, 0)
Contratistas requeridos = CEIL(déficit / horas semanales por contratista)
```

La planta se cuenta una sola vez por especialidad, compartida entre niveles y jornadas. Se redondea por perfil y trimestre. El pico general corresponde a contratistas simultáneos, no a sumar picos de períodos distintos.

La capacidad disponible incluye **únicamente planta**. Los contratistas actuales del reporte no se muestran ni se descuentan: el resultado es toda la contratación necesaria para la vigencia. No se compensa la falta de un perfil con capacidad libre de otro. Los picos muestran personas simultáneas, no la suma de los doce meses.

La propuesta de asignación comparte las horas de cada instructor entre varias fichas: usa primero planta y luego los contratistas proyectados necesarios. Muestra capacidad, horas asignadas, horas libres y fichas atendidas por instructor y mes. Ninguna persona puede superar su capacidad; la suma asignada a cada ficha debe cubrir su demanda. Se asigna por la especialidad o área del reporte; no se infieren habilitaciones por competencia ni se resuelven cruces de horarios diarios.

### Períodos de contratación y exceso

La planeación muestra los picos total, técnico y transversal con sus trimestres, y propone grupos de contratos con cantidad, fecha de inicio y fecha de fin. Conserva cada cupo durante los trimestres consecutivos donde se necesita y separa los períodos si hay un intervalo sin necesidad. Los cupos activos de cada perfil deben coincidir exactamente con los contratistas requeridos en cada trimestre.

Por ejemplo, si un perfil requiere 27, 21, 10 y 0 contratistas en T1–T4, propone 6 de enero a marzo, 11 de enero a junio y 10 de enero a septiembre. Si se conservaran los 27 todo el año, sobrarían 0, 6, 17 y 27 en esos trimestres. La tabla muestra ese exceso condicional y también la reducción respecto al trimestre anterior. Un período que llega a diciembre cubre el horizonte de esta planeación; su continuidad se evalúa en la siguiente vigencia.

Los picos de perfiles distintos pueden ocurrir en trimestres diferentes y no se suman como pico simultáneo. La suma de contratistas por duración expresa meses-contratista, no personas únicas. Concentrar ingresos al inicio no garantiza que el pico ocurra en T1: las fichas anteriores pueden continuar y las competencias cambian según su trimestre de formación.

## Reportes existentes

- **Instructores**: primera hoja con `Nombre`, `Documento`, `Tipo Contrato`, `Total Horas`, agrupada por especialidad. Se rechazan documentos repetidos. Las secciones Bilingüismo e Integralidad identifican esos grupos de capacidad.
- **Fichas**: primera hoja con `N°`, `Número Ficha`, `Tipo Formación`, `Jornada`, `Trimestre`, agrupada por programa. El título debe contener el período, por ejemplo `2026 - Trimestre 4`. Se rechazan fichas repetidas. La vigencia debe ser posterior al año del reporte.

El reporte incluido `data/reporteFichas_2026_4.xlsx` contiene varios programas. Las dos mallas ADSO de las pruebas cubren solamente ADSO Diurna y Mixta: las demás se recuperan del catálogo que el usuario haya cargado. La aplicación no carga archivos locales automáticamente.

## Persistencia y exportación

| Tabla | Contenido |
| --- | --- |
| `curricula` | Programa, jornada, duración, archivo y huella del contenido. |
| `competencies` | Catálogo único, selección transversal, área y procedencia automática/manual de la clasificación. |
| `curriculum_outcomes` | Resultado, competencia, título original, trimestre, horas y hoja/fila del Excel. |
| `specialties`, `instructors`, vista `plant_instructors` | Último reporte normalizado de instructores. |
| `execution` | Última ejecución, entradas, copia de mallas y clasificación, cálculos y resultados. |

Guardar una planeación reemplaza los instructores y la ejecución previa en una transacción. Las mallas y competencias permanecen. Modificar el catálogo no modifica la copia de una ejecución anterior ni su descarga.

Un reinicio completo vacía reportes, ejecución, mallas, resultados y clasificación, y cambia la versión de reinicio de la base. Las sesiones abiertas detectan ese cambio y borran sus archivos y parámetros en memoria al recargar. Las metas iniciales quedan en cero; las capacidades y el tamaño de ficha conservan valores iniciales válidos para evitar divisiones por cero.

Para hacerlo desde la aplicación, abrir **Reportes y parámetros → Limpieza del sistema**, marcar **Confirmo que deseo borrar todos los datos del sistema** y pulsar **Formatear sistema**. La pantalla se reinicia y queda lista para nuevas cargas. El borrado de los datos guardados es permanente; los Excel originales y las descargas en el equipo se conservan.

El Excel contiene distribución, metas, calendario, dotación, continuaciones y capacidad, más **Mallas curriculares**, **Competencias**, **Resultados curriculares** y **Trazabilidad horas**. Esta última muestra cohorte/ficha, edad, competencia, resultado, horas unitarias, fichas, horas requeridas y hoja/fila de origen.

Sus dos primeras hojas son **Contratacion requerida** y **Contratistas y fechas**, con el resumen principal y el detalle individual de inicio y finalización. Las fechas se derivan de los meses de necesidad de cada cupo de la ejecución guardada y conservan el mismo identificador de sus asignaciones mensuales.

También exporta **Resumen mensual**, **Horas mensuales por ficha**, **Dotacion mensual por perfil**, **Capacidad mensual instructores**, **Asignacion mensual de horas** y **Supuestos mensuales**. La ejecución guarda estas tablas para que una descarga posterior conserve los mismos cálculos.

Las hojas **Periodos de contratacion**, **Contratacion por trimestre**, **Picos por perfil**, **Excesos y reducciones** y **Criterio de contratacion** permiten revisar y reproducir la duración de la necesidad. Las ejecuciones antiguas deben recalcularse desde sus reportes y mallas para obtener este desglose con capacidad de planta únicamente.

La documentación previa se conserva en `docs/MODELOS_ANTERIORES.md`. Sus cálculos y pruebas de regresión permanecen; la interfaz principal usa el flujo curricular automático.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan bases temporales. Los dos Excel originales están en `tests/fixtures/curricula/`. Se comprueban importación, deduplicación, clasificación, reimportación, transacciones, jornadas, duraciones, continuaciones, ofertas, capacidad compartida, exportación y recuperación de la interfaz.

Para comprobar los reportes y mallas de la base local y generar un Excel de revisión sin reemplazar la última ejecución:

```powershell
.\.venv\Scripts\python.exe scripts/validate_curricula.py
```

El archivo se escribe en `data/validaciones/planeacion_periodos_contratacion.xlsx`. Después de un reinicio completo se deben volver a cargar los dos reportes, las mallas y ejecutar antes de usar esta validación.
