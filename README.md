# Sistema de Planeación Indicativa SENA

- iniciar el programa con el comando: py -m streamlit run app.py

Versión enfocada en convertir la meta anual y las fichas que continúan en una proyección de capacidad de planta y necesidad de instructores de contrato por especialidad.

## Flujo principal

1. Cargar el reporte de instructores o usar el archivo incluido.
2. Ingresar la meta proyectada de aprendices.
3. El sistema calcula las fichas nuevas usando 25 aprendices por ficha.
4. Ingresar cuántas fichas continúan desde la vigencia anterior.
5. Distribuir las fichas nuevas y las que pasan entre las especialidades técnicas.
6. El sistema identifica los instructores de planta de cada especialidad.
7. Calcula la demanda semanal técnica, de bilingüismo e integralidad.
8. Descuenta la capacidad de planta.
9. Convierte el déficit restante en instructores contratistas usando 40 horas semanales por contratista.
10. Entrega el total requerido y el detalle por especialidad.

## Reglas iniciales configurables

- 25 aprendices por ficha.
- 30 horas semanales de formación por ficha.
- 6 horas semanales de bilingüismo por ficha.
- 6 horas semanales de integralidad por ficha.
- 18 horas técnicas semanales resultantes por ficha.
- 32 horas semanales de capacidad directa por instructor de planta.
- 40 horas semanales por instructor contratista para la proyección.

Todas estas variables están visibles en la barra lateral para simular escenarios sin modificar el código.

## Cálculo de contratistas

Por cada especialidad:

```text
Demanda técnica = fichas activas de la especialidad × horas técnicas por ficha
Capacidad planta = instructores de planta de la especialidad × 32
Déficit = MAX(Demanda técnica - Capacidad planta, 0)
Contratistas requeridos = CEIL(Déficit / 40)
```

Bilingüismo e integralidad se calculan como bolsas separadas sobre el total de fichas activas.

El redondeo se realiza por especialidad. Esto evita que horas sobrantes de un perfil compensen un déficit de otro perfil que requiere una competencia diferente.

## Distribución de fichas

La aplicación genera una propuesta inicial proporcional a la cantidad de instructores técnicos de planta. La tabla es editable y permite agregar especialidades nuevas.

La proyección solo debe considerarse cerrada cuando:

- La suma de `Fichas nuevas` por especialidad coincide con las fichas calculadas desde la meta.
- La suma de `Fichas que pasan` coincide con el valor ingresado por el usuario.

## Contratistas existentes en el reporte

Los contratistas encontrados en el Excel se muestran como referencia, pero **no se restan de la necesidad proyectada**. La lógica de esta versión determina primero cuántos contratistas se necesitan después de utilizar la capacidad de planta disponible.

## Ejecutar

Requiere Python 3.11 o superior.

```bash
pip install -r requirements.txt
streamlit run app.py
```

En Windows también puede ejecutar `iniciar.bat`.

## Estructura

```text
sena_planeacion_indicativa_v2/
├── app.py
├── requirements.txt
├── iniciar.bat
├── core/
│   ├── config.py
│   ├── excel_parser.py
│   └── planner.py
├── config/
│   └── defaults.json
├── data/
│   └── reporteInstructores_2026_4.xlsx
├── docs/
│   └── NORMATIVA.md
└── tests/
    ├── test_parser.py
    └── test_planner.py
```
