# Sistema de Planeación Indicativa SENA

Aplicación Python y Streamlit para calcular fichas, horas e instructores. Titulada presencial usa mallas trimestrales; Titulada virtual usa cronogramas Excel por fases y fechas, con carga docente manual. Cada modalidad tiene entradas, parámetros, catálogos y resultados independientes. SQLite conserva la clasificación y la última planeación ejecutada de cada modalidad.

## Iniciar

Requiere Python 3.11 o superior. En Windows, abrir `iniciar.bat` o ejecutar:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

No requiere servidor de base de datos. Titulada presencial conserva la base existente `data/planeacion.sqlite3`; Titulada virtual usa `data/planeacion_virtual.sqlite3`. No se trasladan ni copian automáticamente datos de una modalidad a otra.

## Navegación

En la barra lateral seleccione **Formación** (Titulada o Complementaria) y **Modalidad** (Presencial o Virtual).

| Espacio | Funcionamiento |
| --- | --- |
| Titulada · Presencial | Flujo existente: reportes de planta y fichas, mallas, metas y parámetros. |
| Titulada · Virtual | Cronogramas Excel por fases; clasificación técnica/transversal, horas docentes, fichas que pasan, planta, metas y ofertas manuales. |
| Complementaria · Presencial | Espacio vacío, pendiente de implementar. |
| Complementaria · Virtual | Espacio vacío, pendiente de implementar. |

Los borradores de las dos modalidades de Titulada se conservan al navegar durante la misma sesión. Para conservar la planeación al cerrar el navegador, pulse **Ejecutar y guardar planeación**. Los catálogos y su clasificación tienen sus propios botones de guardado. La limpieza afecta solamente a la modalidad abierta; conserva la otra modalidad y los Excel originales.

## Preparar y ejecutar Titulada virtual

1. Seleccione **Titulada → Virtual**. En **Cronogramas y competencias**, cargue los `.xlsx` y pulse **Importar y guardar cronogramas**. Se admite el formato del **Cronograma General - Analisis y Desarrollo de Software.xlsx** recibido: nombre del programa, fases, actividades del proyecto, actividades de aprendizaje, horas estimadas y fechas. El nombre del archivo es libre; el programa se lee del contenido. Virtual no solicita PDF ni reportes de planta/fichas.
2. Revise las observaciones del archivo. Por cada resultado/actividad lectiva elija **Técnico** o **Transversal** e ingrese las **horas totales de instructor por ficha para la actividad completa**. Pulse **Guardar clasificación y horas**. Las horas estimadas de formación del Excel permanecen como referencia. Un campo vacío queda pendiente: use **0** explícito donde no se requieran horas docentes. La etapa productiva y su seguimiento están excluidos del editor, de las horas y de la contratación, incluso si tenían horas manuales guardadas.
3. En **Datos manuales y parámetros**, indique vigencia, metas por nivel, aprendices por ficha y capacidades semanales de planta/contratistas. Configure los porcentajes de las **cuatro ofertas** (suman 100 %) y sus fechas de inicio. Las fechas se exigen en las ofertas que reciben fichas. Virtual no usa jornadas ni semanas por trimestre.
4. En **Programas a planear**, seleccione nivel, programas incluidos y **Peso de oferta**. Este peso determina la participación anual dentro de cada nivel, con redondeo a fichas completas. El total se reparte entre las ofertas conservando las cantidades anuales por programa y nivel.
5. En **Fichas que pasan**, registre programa, cantidad y **fecha de inicio de formación**. Use filas distintas si las fechas de inicio son diferentes. El cronograma permite ubicar fases pendientes y estimar terminación. Deje vacío si no hay continuaciones.
6. En **Instructores de planta**, seleccione **Tipo**, **Perfil** y cantidad: para Técnico, el programa; para Transversal, el código de competencia clasificado en los cronogramas. La capacidad transversal se comparte entre programas con esa competencia. Son cupos sin datos personales y cada instructor se cuenta una vez en su perfil. Deje vacío si no hay planta.
7. En **Planeación**, revise el pico simultáneo técnico/transversal, fechas de contratación, horas anuales, resumen mensual y trazabilidad por actividad. Pulse **Ejecutar y guardar planeación** para conservar datos manuales y habilitar el Excel actualizado.

Las nuevas cubren el saldo de la meta después de descontar los aprendices que pasan, sin crecimiento ni reposiciones adicionales. El calendario virtual traslada los intervalos del cronograma según el inicio de cada cohorte, conservando distancias en días. Las horas docentes se distribuyen uniformemente dentro de cada intervalo como promedio de planeación. Se descuenta planta y se redondea contratación por tipo/perfil al cambiar las actividades. El resumen mensual conserva los picos simultáneos; no representa un horario diario.

Los nombres y duración de las fases proceden del archivo; las cuatro ofertas no equivalen a cuatro fases. El [Manual ZAJUNA del instructor del SENA](https://zajuna.sena.edu.co/pdfs/titulada/manuales/MANUAL%20ZAJUNA%20INSTRUCTOR_compressed.pdf) describe cronogramas, fases, actividades y fechas. Las capacidades y las fechas de ofertas son parámetros del centro, no valores normativos inferidos.

El lector admite las celdas combinadas y nombres de fases partidos del Excel suministrado. Muestra la diferencia de origen entre **3072 horas de bloques lectivos y 3120 del resumen**, sin distribuir automáticamente esas 48 horas. Los detalles y supuestos están en [VALIDACION_MODALIDADES.md](docs/VALIDACION_MODALIDADES.md).

Las ejecuciones virtuales anteriores basadas en trimestres se conservan para descargar. Para recalcular por fases deben cargarse cronogramas y completar fechas y horas; no se convierten edades trimestrales en fechas inventadas.

La planeación virtual cuenta únicamente carga docente de etapa lectiva. Los datos productivos del archivo se conservan identificados como referencia excluida en pantalla y en Excel. Si una ejecución guardada es anterior a esta regla, la vista previa ya la aplica y se debe pulsar **Ejecutar y guardar planeación** para actualizar la descarga. Las fechas generales de formación y el conteo de fichas para metas se mantienen; una ficha que solo está en productiva no genera horas ni contratos.

## Preparar y ejecutar Titulada presencial

1. En **Mallas y competencias**, cargar uno o varios archivos `PROGRAMA - JORNADA.xlsx`, revisar la vista previa y pulsar **Digitalizar y guardar mallas**. Diurna/Diurno y Mixta/Mixto se normalizan. O&P/P&O es una abreviatura del programa y no crea una jornada adicional.
2. Revisar **Todas las competencias**. Los títulos equivalentes comparten una única competencia. La carga selecciona automáticamente las transversales según el tipo del Excel; cuando falta, reconoce los títulos transversales conocidos. Se pueden corregir **Transversal** y el área Bilingüismo/Integralidad con los campos existentes. **Guardar clasificación de competencias** conserva esa corrección en futuras importaciones.
3. En **Reportes y parámetros**, cargar los reportes para identificar la planta y las fichas, o recuperarlos de la ejecución guardada.
4. Configurar vigencia, metas totales por nivel (incluyen los aprendices que pasan y los nuevos), aprendices por ficha, horas disponibles de instructores, semanas efectivas y porcentajes de oferta T1–T4. Los porcentajes deben sumar 100 %. La meta ingresada ya debe contener el crecimiento deseado.
5. En **Planeación**, revisar primero el total de contratistas requeridos y el trimestre del pico máximo. Los detalles y las fechas se consultan debajo en tablas desplegables. No se transcriben continuaciones, terminaciones, módulos ni horas pendientes.
6. Pulsar **Ejecutar y guardar planeación** y descargar el Excel. Si cambian las entradas, se muestra una sola vista previa y se deshabilita su descarga hasta guardarla. El archivo de la ejecución anterior se conserva en su propio desplegable.

La pantalla principal muestra el **total de contratistas requeridos**, el **trimestre del pico máximo** y su desglose técnico/transversal. El total es la cantidad máxima simultánea durante la vigencia. Ambos componentes corresponden al mismo trimestre y suman ese total; los picos propios de cada perfil se consultan en el detalle. Si el máximo se repite, se muestran todos sus trimestres.

En **Contratistas requeridos y fecha de finalización**, cada fila identifica un instructor técnico o transversal proyectado, su perfil, fecha desde/hasta y capacidad semanal. Son cupos por contratar calculados con las mallas, después de la cobertura de planta. Un cupo con períodos separados tiene una fila por período. El número de filas puede superar el pico simultáneo si cambian los perfiles durante el año.

Los programas y niveles de la oferta se obtienen del reporte de fichas, incluidas sus combinaciones sin continuaciones. La malla por sí sola no identifica el nivel; para incorporar un programa a la oferta debe estar identificado con su nivel y jornada en el reporte.

## Formato de las mallas presenciales

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

## Cálculo de las horas presenciales

La duración proviene exclusivamente del número de hojas consecutivas `Trimestre N` de la malla del programa y su jornada. No se asignan duraciones por nivel ni se completan mallas ausentes con reglas históricas. Se requieren las mallas de todos los programas/jornadas del reporte para determinar cuáles fichas pasan y cuáles terminan, incluso si la meta es cero. Las continuaciones avanzan desde el trimestre de formación del reporte hasta el inicio de la vigencia. Una ficha termina al final de su último trimestre; las nuevas ingresan al principio del trimestre calendario.

```text
Edad en T1 = trimestre cursado + trimestres calendario hasta la vigencia
Edad de una nueva en Tq = q − trimestre de ingreso + 1
Período de fin = período calendario del reporte + duración de la malla − trimestre cursado
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

La variante de nombre «Órtesis y prótesis» se vincula con «Prótesis y órtesis». O&P/P&O identifica el programa, no la jornada: se retira esa abreviatura antes de interpretar el horario. «P&O-mañana» y «P&O-tarde» se reconocen como Diurna; «Mixta O&P» conserva Mixta. No existe la jornada «Diurna O&P», ni una duración especial asociada a la abreviatura. Las fichas se agrupan por programa, nivel y jornada real y utilizan la misma malla correspondiente, sin renombrarla ni duplicarla. El texto original del reporte permanece en el detalle. Si solo aparece la abreviatura, sin horario ni jornada, debe corregirse ese dato del archivo. Diurna y Mixta siguen separadas.

Si falta una malla, se enumeran las combinaciones pendientes antes de proyectar continuaciones. Si el trimestre reportado supera la duración curricular, se identifica la ficha para corregir el reporte o cargar la malla adecuada; no se descarta silenciosamente como terminada. Al reemplazar una malla se recalculan fechas y horas desde las filas originales del reporte, sin usar cantidades o fechas de una ejecución anterior.

En **Duración y terminación de las fichas del reporte** se consultan la malla usada, duración, trimestre de formación al iniciar la vigencia, trimestres pendientes y fecha de fin estimada. **Horas mensuales de cada ficha** también incluye duración, archivo de malla y fecha final para las fichas nuevas, aunque terminen en otra vigencia. Esas fechas representan el cierre del trimestre, no una fecha diaria de certificación. El Excel conserva este detalle y el **Criterio de duraciones**.

Los parámetros editables de capacidad por instructor, aprendices por ficha, semanas efectivas y ofertas siguen siendo entradas del escenario, pues los reportes no suministran todos esos valores. Las horas nominales de jornada no intervienen en ninguna etapa del cálculo curricular. Las reglas del modelo histórico se conservan para sus pruebas de compatibilidad; el flujo principal exige mallas y tiene una prueba que falla si intenta invocar duraciones, crecimiento u horas del modelo anterior. Los valores del calendario (cuatro trimestres y tres meses por trimestre) y las tolerancias de redondeo no representan datos de programas.

El motor curricular tiene un recorrido propio: no llama al planificador histórico. Valida únicamente los parámetros que usa; las referencias horarias no bloquean ni completan su demanda. Una meta fraccionaria, capacidad inválida, perfil sin correspondencia en el reporte o demanda incompleta produce un error; no se convierte silenciosamente a otra cantidad. En **Reglas utilizadas en el cálculo** y en las hojas **Parametros usados** y **Criterio de calculo** se muestran los valores efectivos, su origen y la fórmula. La auditoría y sus comprobaciones están en [AUDITORIA_CALCULOS.md](docs/AUDITORIA_CALCULOS.md).

## Fichas e instructores presenciales

La meta es el total de aprendices atendidos durante la vigencia. Cada ficha que pasa cuenta una sola vez para la meta, aunque termine antes de diciembre. Como el reporte no incluye su matrícula, sus aprendices se estiman con el tamaño de ficha configurado. Técnico y Tecnólogo se calculan por separado.

```text
Aprendices que pasan (estimados) = fichas que pasan × aprendices por ficha
Saldo de la meta = MAX(meta total − aprendices que pasan, 0)
Fichas nuevas = CEIL(saldo de la meta / aprendices por ficha)
```

Las nuevas se distribuyen proporcionalmente a la participación de los programas y jornadas en el reporte, con redondeo por mayores residuos y sin un mínimo obligatorio de una ficha por programa. Se eliminó el crecimiento automático del 5 % por programa: la meta final ya incluye el crecimiento deseado. Así se evita aumentar artificialmente programas pequeños.

El apartado **Fichas nuevas por programa y oferta** muestra las cantidades para T1, T2, T3 y T4, el total anual y el detalle por jornada. También se exportan en las hojas **Fichas por oferta** y **Ofertas por jornada**. Estas tablas resumen el calendario que alimenta el cálculo de horas y contratistas.

Para ordenar los ingresos, se usa la cantidad de fichas de cada programa en el reporte, sumando sus jornadas, como referencia de popularidad; no hay datos de solicitudes ni matrícula real. Dentro de cada nivel, los programas con menor presencia ocupan primero los cupos disponibles, dando prioridad a las primeras ofertas. Los de mayor presencia cubren los cupos posteriores y pueden ingresar también al inicio si los porcentajes lo requieren. Los programas con igual presencia comparten los cupos proporcionalmente a sus nuevas pendientes; los residuos enteros se desempatan por nombre normalizado. Se conservan el total anual por programa y jornada y el total por oferta de cada nivel. No se añaden fichas ni se impone una cantidad de contratistas para obtener este orden.

En **Titulada presencial**, la actualización declarada en `config/presencial_programs.json` vincula Diseño e Integración de Automatismos Mecatrónicos con Automatización de Sistemas Mecatrónicos. El programa anterior solo conserva continuaciones; cada ficha mantiene su malla original, horas y fecha de finalización. La participación de ambos nombres se suma una vez para asignar las fichas nuevas al programa vigente. Se utilizan sus jornadas con malla cargada y las proporciones del reporte combinado; si únicamente está cargada la jornada diurna del programa nuevo, los ingresos se proyectan allí. No se reutiliza la malla antigua para los nuevos ingresos.

La planta de ambos nombres forma un solo grupo de capacidad y contratación, compartido entre las fichas antiguas y nuevas. La indicación expresa del usuario de que Automatización es popular la sitúa después de los programas ordenados por presencia en el reporte, respetando los cupos configurados por oferta. Esta indicación no cambia las cuotas anuales ni añade horas o instructores. La relación y su origen se muestran en **Programas actualizados y planta compartida** y en el Excel exportado; se guardan con cada ejecución. Los nombres originales siguen visibles en la trazabilidad de las mallas y fichas. Esta política no se aplica a Titulada virtual.

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
| `virtual_schedules` (solo Virtual) | Cronogramas, fases, actividades, fechas, clasificación y horas docentes manuales. |

Guardar una planeación reemplaza los instructores y la ejecución previa en una transacción. Los catálogos permanecen. Modificar el catálogo no modifica la copia de una ejecución anterior ni su descarga. La ejecución virtual conserva una copia del cronograma y su carga docente; su Excel incluye fechas de ofertas, fases, clasificación, contratos, cobertura por perfil y observaciones de origen.

Un reinicio completo vacía reportes, ejecución y catálogos (incluidos cronogramas y carga docente en Virtual), y cambia la versión de reinicio de la base de la modalidad activa. Las sesiones abiertas detectan ese cambio y borran sus archivos y parámetros en memoria al recargar. Las metas iniciales quedan en cero; las capacidades y el tamaño de ficha conservan valores iniciales válidos para evitar divisiones por cero.

Para hacerlo desde la aplicación, abrir **Reportes y parámetros** (Presencial) o **Datos manuales y parámetros** (Virtual), entrar a **Limpieza del sistema**, marcar la confirmación y pulsar **Formatear sistema**. La pantalla queda lista para nuevas cargas. El borrado de los datos guardados de esa modalidad es permanente; la otra modalidad, los Excel originales y las descargas se conservan.

El Excel presencial contiene distribución, metas, calendario, dotación, continuaciones y capacidad, más **Mallas curriculares**, **Competencias**, **Resultados curriculares** y **Trazabilidad horas**. Esta última muestra cohorte/ficha, edad, competencia, resultado, horas unitarias, fichas, horas requeridas y hoja/fila de origen.

Sus dos primeras hojas son **Contratacion requerida** y **Contratistas y fechas**, con el resumen principal y el detalle individual de inicio y finalización. Las fechas se derivan de los meses de necesidad de cada cupo de la ejecución guardada y conservan el mismo identificador de sus asignaciones mensuales.

También exporta **Resumen mensual**, **Horas mensuales por ficha**, **Dotacion mensual por perfil**, **Capacidad mensual instructores**, **Asignacion mensual de horas** y **Supuestos mensuales**. La ejecución guarda estas tablas para que una descarga posterior conserve los mismos cálculos.

Las hojas **Periodos de contratacion**, **Contratacion por trimestre**, **Picos por perfil**, **Excesos y reducciones** y **Criterio de contratacion** permiten revisar y reproducir la duración de la necesidad. Las ejecuciones antiguas deben recalcularse desde sus reportes y mallas para obtener este desglose con capacidad de planta únicamente.

La documentación previa se conserva en `docs/MODELOS_ANTERIORES.md`. Sus cálculos y pruebas de regresión permanecen; la interfaz principal usa el flujo curricular automático.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan bases temporales. Las mallas originales están en `tests/fixtures/curricula/` y el cronograma virtual real en `tests/fixtures/virtual_schedules/`. Se comprueban importación, clasificación, reimportación, transacciones, jornadas presenciales, fases virtuales, continuaciones, ofertas, capacidad, exportación e interfaz. También se verifica que guardar o limpiar una modalidad no cambie la otra base.

Para comprobar los reportes y mallas de la base local y generar un Excel de revisión sin reemplazar la última ejecución:

```powershell
.\.venv\Scripts\python.exe scripts/validate_curricula.py
```

El archivo se escribe en `data/validaciones/planeacion_periodos_contratacion.xlsx`. Después de un reinicio completo se deben volver a cargar los dos reportes, las mallas y ejecutar antes de usar esta validación.
