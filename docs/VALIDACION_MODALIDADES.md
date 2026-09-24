# Validación de Titulada presencial y virtual

## Separación

- Presencial sigue usando `data/planeacion.sqlite3`, sin traslado de sus datos, con su motor de mallas trimestrales.
- Virtual usa `data/planeacion_virtual.sqlite3` y un motor por fechas de cronogramas, independiente de los trimestres y jornadas presenciales.
- Las entradas de pantalla y los borradores pertenecen a una modalidad. Cambiar a Complementaria no calcula ni escribe planeaciones.
- Las descargas incluyen la modalidad en el nombre y en el resumen del Excel.
- La limpieza y la invalidación de sesiones se aplican a una sola base.

## Referencias y decisiones del centro

El [Manual ZAJUNA del instructor](https://zajuna.sena.edu.co/pdfs/titulada/manuales/MANUAL%20ZAJUNA%20INSTRUCTOR_compressed.pdf), sección «Cronograma», describe fases, competencias, resultados, actividades y fechas. El [Manual LMS del aprendiz](https://zajuna.sena.edu.co/Repositorio/Titulada/institution/SENA/Tutoriales/Aprendiz/Manual_LMS_Aprendiz.pdf), apartados 8.2 y 8.4, sitúa el cronograma y las fases dentro del programa.

Se toman nombres y duraciones del Excel; no se fija una duración común para las fases. Las cuatro ofertas anuales y las capacidades semanales se mantienen por instrucción del usuario. Sus fechas y valores se configuran por vigencia. No se presume que las ofertas coincidan con trimestres calendario ni que las horas estimadas del aprendiz sean horas de instructor.

El usuario indicó que la carga docente se completa manualmente por perfil y actividad y posteriormente precisó que solo se cuentan horas de etapa lectiva. Cada actividad lectiva permite seleccionar Técnico/Transversal y sus horas totales de instructor por ficha. La etapa productiva y su seguimiento se conservan como referencia excluida y no requieren clasificación ni horas. La planta técnica se vincula al programa; la transversal, a la competencia lectiva. La capacidad se comparte entre fichas del mismo perfil sin duplicar planta ni compensar perfiles diferentes.

Las ejecuciones virtuales anteriores se conservan para descargar. Para calcular por fases se requieren cronogramas y datos manuales revisados, sin transformar edades trimestrales en fechas inventadas.

## Excel real validado

La copia de prueba `tests/fixtures/virtual_schedules/cronograma_adso.xlsx` corresponde al archivo recibido **Cronograma General - Analisis y Desarrollo de Software.xlsx**:

- Lee «Análisis y desarrollo de software», proyecto y fechas de referencia 27/06/2024–07/10/2026.
- Reconstruye los rótulos partidos de Análisis, Planeación y Ejecución y conserva Inducción, Evaluación y etapa productiva.
- Obtiene 11 bloques y 101 registros de origen: 100 actividades lectivas editables y el seguimiento productivo excluido. Las filas 43 y 77 contienen dos códigos cada una y se separan para poder asignar tipo y horas individualmente. Se conserva el texto original.
- Cuenta las horas de celdas combinadas una sola vez: 9 de inducción, 3072 de bloques lectivos y 864 de etapa productiva.
- El resumen lectivo declara 3120 horas: muestra las 48 horas de diferencia como observación, sin alterar ni distribuir esos valores.
- Las continuaciones de página sin fechas conservan las del bloque anterior, con una observación visible y exportada.
- Clasificación y horas docentes de las actividades lectivas parten pendientes; cero es una decisión explícita válida. El seguimiento productivo no se edita ni genera carga, aunque un catálogo anterior conserve horas para él.

Solo se admite `.xlsx`. El nombre del archivo es libre y el programa se identifica dentro del contenido. Una malla presencial, un PDF, un archivo ilegible o fechas inconsistentes se rechazan. El lector está validado para esta estructura de Cronograma General; otros diseños deberán contener las mismas columnas e identificación del programa.

## Cálculos comprobados

Caso base: tres actividades consecutivas de 7 días y cargas docentes de 10, 20 y 30 horas por ficha. La segunda es transversal. Dos fichas que pasan iniciadas el 25/12/2026 llegan al 01/01/2027 con 50 horas pendientes cada una. Meta 100 y 25 aprendices por ficha generan dos fichas nuevas: 100 horas pendientes + 120 nuevas = **220 horas en 2027**.

Con intervalos de 7, 14 y 7 días y una planta transversal de 32 h/sem, una ficha necesita 60 horas totales y contratos técnicos del 01–07/01 y 22–28/01. La planta transversal cubre su actividad sin cubrir las técnicas. Un caso de 80 horas en siete días conserva el pico de dos contratistas aunque la actividad ocupe solo parte del mes; si inicia el 29/12, la vigencia recibe únicamente 3/7 de sus horas.

Las ofertas se prueban con fechas 10/02, 20/05, 15/08 y 25/11. Las fechas de cohortes y contratos se derivan de los intervalos, sin convertir fases en trimestres.

El reparto uniforme de horas dentro del intervalo es un supuesto de planeación. Se calcula una tasa semanal equivalente y se compara con la capacidad semanal al cambiar las actividades. No representa el horario diario de los instructores ni una obligación de trabajar en días no hábiles.

La exclusión productiva se aplica antes de construir la demanda, los resúmenes mensuales, la cobertura y los contratos. Se prueba con carga productiva vacía, cero y 1000 horas: las tres variantes conservan exactamente las 60 horas lectivas del caso de una ficha nueva y no prolongan contratos después del 21/01. Una continuación que solo cursa etapa productiva genera cero horas y cero contratistas. El conteo de fichas para metas y las fechas generales de formación mantienen su regla anterior.

También se usa el Excel real con una continuación iniciada el 27/06/2024 y vigencia 2026: aun simulando 864 horas docentes productivas históricas, estas no suman ni generan contratos. En el Excel de salida se conservan como datos de origen, con **Incluida en planeación = falso** y **Horas docentes por ficha para planeación = 0**. Las ejecuciones anteriores requieren guardar el recálculo lectivo para actualizar su descarga; su copia histórica no se modifica.

## Pruebas automatizadas

```powershell
.venv\Scripts\python.exe -m pytest -q
```

`tests/test_virtual_schedules.py` cubre el archivo real, celdas combinadas, fases partidas, horas de origen frente a carga manual, exclusión productiva con datos actuales e históricos, guardado/reimportación, fechas de continuaciones, cuatro ofertas, picos, cobertura por perfil, exportación y aislamiento de Presencial.

`tests/test_planning_modules_app.py` usa Streamlit AppTest para comprobar navegación, clasificación, horas, planta manual, guardado/reapertura, borradores al cambiar de modalidad, sustitución de cronogramas, datos inválidos, descargas y limpieza sin cambios en la otra base. Verifica que Virtual no muestre parámetros de jornadas ni trimestres y que ejecuciones presenciales anteriores sigan abriendo.

Las pruebas presenciales e históricas existentes permanecen. `tests/test_virtual_planning.py` conserva la regresión del modelo virtual inicial por trimestres, utilizado solo como compatibilidad; la interfaz activa usa cronogramas. Las pruebas utilizan bases temporales y no reemplazan las ejecuciones reales del centro.
