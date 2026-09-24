"""Oferta y demanda por trimestre: las reposiciones no se suman a la ficha saliente."""
import pandas as pd

from core.excel_parser import normalize_text
from core.ficha_projection import duration_in_quarters
from core.level_planner import PROFILE_COLUMNS, hours_by_profile
from core.planner import largest_remainder_allocation, technical_staffing_plan, transversal_staffing_plan, staffing_summary
from core.workflow import records

ENDING_COLUMNS = [f"Terminan T{quarter}" for quarter in range(1, 5)]


def profile_key(row):
    from core.curriculum import curriculum_key
    program, schedule = curriculum_key(row["Especialidad"], row["Jornada"])
    return program, normalize_text(row["Nivel"]), schedule


def suggested_endings(manual, imported=None, *, strict=False):
    """Conserva fechas del reporte; reconcilia cambios manuales sin inventar fichas."""
    weights = {}
    for row in (imported or {}).get("detail", []):
        if row["Termina en la vigencia"]:
            profile = {**row, "Jornada": row["Jornada de planeación"]}
            counts = weights.setdefault(profile_key(profile), [0] * 4)
            counts[int(row["Trimestre fin estimado"]) - 1] += 1
    result = manual[PROFILE_COLUMNS].copy()
    for index, row in manual.iterrows():
        if strict:
            counts = weights.get(profile_key(row), [0] * 4)
            if sum(counts) != int(row["Fichas que terminan"]):
                raise ValueError(f"{row['Especialidad']} · {row['Jornada']}: las terminaciones no coinciden con las fichas del reporte y sus mallas.")
            allocation = dict(zip(ENDING_COLUMNS, counts))
        else:
            allocation = largest_remainder_allocation(int(row["Fichas que terminan"]), ENDING_COLUMNS,
                                                     weights.get(profile_key(row), [1] * 4))
        for column, count in allocation.items():
            result.loc[index, column] = count
    return result.reindex(columns=PROFILE_COLUMNS + ENDING_COLUMNS).astype({column: int for column in ENDING_COLUMNS})


def validate_endings(manual, endings):
    required = PROFILE_COLUMNS + ENDING_COLUMNS
    if not set(required).issubset(endings.columns) or len(endings) != len(manual):
        raise ValueError("Revise las terminaciones de los cuatro trimestres para cada fila.")
    expected = [profile_key(row) for row in manual.to_dict("records")]
    keyed = {profile_key(row): row for row in endings.to_dict("records")}
    if len(keyed) != len(expected) or set(keyed) != set(expected):
        raise ValueError("Las terminaciones trimestrales deben corresponder a las mismas especialidades, niveles y jornadas.")
    result = pd.DataFrame([keyed[key] for key in expected], columns=required)
    for column in ENDING_COLUMNS:
        values = pd.to_numeric(result[column], errors="coerce")
        if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError("Las terminaciones trimestrales deben ser enteros no negativos.")
        result[column] = values.astype(int)
    if not result[ENDING_COLUMNS].sum(axis=1).equals(manual["Fichas que terminan"].reset_index(drop=True)):
        raise ValueError("La suma de Terminan T1 a T4 debe coincidir con las fichas que terminan de cada fila.")
    return result


def calendar_rows(distribution, endings, rules, durations=None, intake_schedule=None):
    """Reserva reemplazos al trimestre siguiente y prioriza primera oferta adicional."""
    if durations is not None:
        from core.curriculum import require_curriculum_durations
        require_curriculum_durations(distribution, durations)
    rows = []
    for index, row in distribution.iterrows():
        finish = endings.loc[index, ENDING_COLUMNS].astype(int).tolist()
        replacements = [0, *finish[:3]]
        if intake_schedule is not None:
            starts = list(intake_schedule[index])
        else:
            additional = int(row["Fichas nuevas"]) - sum(replacements)
            intake = largest_remainder_allocation(additional, range(4), rules.intake_weights)
            starts = [replacements[q] + intake[q] for q in range(4)]
        from core.curriculum import curriculum_key
        if durations is not None:
            duration = int(durations[curriculum_key(row["Especialidad"], row["Jornada"])])
        else:
            duration = duration_in_quarters(row["Nivel"], row["Jornada"])
        # Una ficha técnica abierta en T1 termina en T3: se reemplaza en T4.
        extra_replacements = [0] * 4
        for q in range(duration, 4) if intake_schedule is None else []:
            required = finish[q - 1] + starts[q - duration]
            extra_replacements[q] = max(0, required - starts[q])
            starts[q] += extra_replacements[q]
        if intake_schedule is not None:
            pending_replacements = 0
            replacements = []
            for q in range(4):
                pending_replacements += (finish[q - 1] if q else 0) + (starts[q - duration] if q >= duration else 0)
                covered = min(starts[q], pending_replacements)
                replacements.append(covered)
                pending_replacements -= covered
        # Las horas curriculares se completan desde resultados por edad, sin
        # calcular primero una demanda ficticia a partir de la jornada nominal.
        rates = hours_by_profile(pd.DataFrame([row]), rules).iloc[0] if durations is None else None
        for q in range(4):
            continuing = int(row["Fichas que pasan"]) - sum(finish[:q])
            new_active = sum(starts[start] for start in range(q + 1) if q - start < duration)
            new_ending = starts[q - duration + 1] if q >= duration - 1 else 0
            active = continuing + new_active
            item = {**{column: row[column] for column in PROFILE_COLUMNS},
                    "Trimestre": q + 1, "Semanas": rules.weeks_per_quarter,
                    "Fichas nuevas": starts[q], "Reposiciones": replacements[q] + (starts[q - duration] if q >= duration and intake_schedule is None else 0),
                    "Nuevas adicionales por rotación": extra_replacements[q],
                    "Continuaciones activas": continuing, "Nuevas activas": new_active,
                    "Fichas activas": active, "Terminan continuaciones": finish[q],
                    "Terminan nuevas": new_ending, "Fichas al cierre": active - finish[q] - new_ending}
            for name, rate in [("totales", "Horas"), ("técnicas", "Técnicas"), ("bilingüismo", "Bilingüismo"), ("integralidad", "Integralidad")]:
                weekly = active * rates[f"{rate} por ficha (h/sem)"] if rates is not None else 0.0
                item[f"Horas {name} (h/sem)"] = float(weekly)
                item[f"Horas {name} del trimestre"] = float(weekly * rules.weeks_per_quarter)
            item["Horas nuevas del trimestre"] = float(new_active * rates["Horas por ficha (h/sem)"] * rules.weeks_per_quarter) if rates is not None else 0.0
            rows.append(item)
    return pd.DataFrame(rows)


def apply_calendar(execution, instructors, distribution, endings, rules, *, modules=None, continuing_hours=None, ficha_import=None, curriculum_catalog=None):
    from core.curriculum import duration_lookup
    from core.curriculum_intakes import OFFER_BASIS, curricular_offer_schedule, curricular_offer_tables
    from core.program_transitions import active_program
    transitions = execution.get("program_transitions", [])
    # La presencia de mallas obliga al calendario curricular, incluso si falta
    # una etiqueta de una ejecución anterior; nunca activa reposiciones extra.
    schedule = (curricular_offer_schedule(distribution, rules, execution.get("intake_allocation", []), transitions)
                if curriculum_catalog is not None or execution.get("target_basis") else None)
    calendar = calendar_rows(distribution, endings, rules, duration_lookup(curriculum_catalog) if curriculum_catalog is not None else None, schedule)
    if schedule is not None:
        execution["offers_by_program"], execution["offers_by_profile"] = curricular_offer_tables(calendar, execution["intake_allocation"], transitions)
        execution["offer_basis"] = OFFER_BASIS
        if transitions:
            execution["offer_basis"] += " " + execution["program_transition_basis"]
    if curriculum_catalog is not None:
        from core.curriculum_planner import apply_curriculum_hours
        if modules is not None:
            raise ValueError("Seleccione un solo origen de horas: mallas o módulos manuales.")
        calendar, audit = apply_curriculum_hours(calendar, curriculum_catalog, ficha_import, execution["planning_year"], rules)
        execution["curriculum_catalog"] = curriculum_catalog
        execution["curriculum_hours"] = audit
        if transitions:
            calendar["Programa de planeación"] = calendar["Especialidad"].map(lambda name: active_program(name, transitions))
            for row in audit:
                row["Programa de planeación"] = active_program(row["Programa"], transitions)
    if modules is not None:
        from core.transversal_modules import validate_modules, continuing_template, apply_module_hours
        modules = validate_modules(modules, distribution, rules)
        if continuing_hours is None:
            continuing_hours = continuing_template(distribution, endings, modules, ficha_import, execution["planning_year"])
        calendar, continuing_hours = apply_module_hours(calendar, modules, continuing_hours, rules)
        execution["transversal_modules"] = records(modules)
        execution["continuing_transversal_hours"] = records(continuing_hours)
    execution["transversal_demand_model"] = "curricula" if curriculum_catalog is not None else ("modules" if modules is not None else "weekly")
    technical_rows, transversal_rows, quarterly = [], [], []
    for quarter in range(1, 5):
        group = calendar.loc[calendar["Trimestre"] == quarter].copy()
        group["Especialidad"] = group["Especialidad"].map(lambda name: active_program(name, transitions))
        totals = group.groupby("Especialidad", as_index=False).agg(**{
            "Fichas nuevas": ("Fichas nuevas", "sum"),
            "Fichas que pasan": ("Fichas activas", "sum"),
        })
        totals["Fichas que pasan"] -= totals["Fichas nuevas"]
        totals["Fichas que terminan"] = group.assign(end=group["Terminan continuaciones"] + group["Terminan nuevas"]).groupby("Especialidad")["end"].sum().reindex(totals["Especialidad"]).to_numpy()
        tech = technical_staffing_plan(instructors, totals, rules,
                                      demand_by_specialty=group.groupby("Especialidad")["Horas técnicas (h/sem)"].sum().to_dict())
        trans = transversal_staffing_plan(instructors, int(group["Fichas activas"].sum()), rules, demand_by_area={
            "Bilingüismo": group["Horas bilingüismo (h/sem)"].sum(),
            "Integralidad": group["Horas integralidad (h/sem)"].sum()})
        summary = staffing_summary(tech, trans, rules)
        for frame in [tech, trans]:
            frame["Horas a contratar en trimestre"] = frame["Déficit antes de contratar (h/sem)"] * rules.weeks_per_quarter
            frame["Contratistas equivalentes"] = frame["Déficit antes de contratar (h/sem)"] / rules.weekly_contractor_hours
        technical_rows.extend({**row, "Trimestre": quarter} for row in records(tech))
        transversal_rows.extend({**row, "Trimestre": quarter} for row in records(trans))
        quarterly.append({"Trimestre": quarter, "Fichas nuevas": int(group["Fichas nuevas"].sum()),
                          "Fichas activas": int(group["Fichas activas"].sum()),
                          "Horas requeridas": float(group["Horas totales del trimestre"].sum()),
                          "Horas técnicas": float(group["Horas técnicas del trimestre"].sum()),
                          "Bilingüismo": float(group["Horas bilingüismo del trimestre"].sum()),
                          "Integralidad": float(group["Horas integralidad del trimestre"].sum()), **summary})
    tech_frame, trans_frame = pd.DataFrame(technical_rows), pd.DataFrame(transversal_rows)
    # Picos individuales para revisar cada perfil; contratación general usa el pico simultáneo.
    technical = tech_frame.loc[tech_frame.groupby("Especialidad")["Demanda técnica (h/sem)"].idxmax()]
    transversal = trans_frame.loc[trans_frame.groupby("Área")["Demanda (h/sem)"].idxmax()]
    peak = max(quarterly, key=lambda row: (row["contratistas_totales"], row["deficit_total_horas_semana"]))
    summary = {key: peak[key] for key in summary}
    summary["trimestre_pico_contratacion"] = peak["Trimestre"]
    summary["horas_a_contratar_anuales"] = sum(row["deficit_total_horas_semana"] * rules.weeks_per_quarter for row in quarterly)
    center = execution["center"]
    center["fichas_que_terminan"] = int(endings[ENDING_COLUMNS].sum().sum())
    center["fichas_al_cierre"] = int(calendar.loc[calendar["Trimestre"] == 4, "Fichas al cierre"].sum())
    center["reposiciones_siguiente_vigencia"] = int(calendar.loc[calendar["Trimestre"] == 4, ["Terminan continuaciones", "Terminan nuevas"]].sum().sum())
    center["fichas_activas"] = max(row["Fichas activas"] for row in quarterly)
    for name, column in [("total", "totales"), ("tecnica", "técnicas"), ("bilinguismo", "bilingüismo"), ("integralidad", "integralidad")]:
        center[f"demanda_{name}_horas_anuales"] = float(calendar[f"Horas {column} del trimestre"].sum())
        center[f"demanda_{name}_horas_semana"] = float(calendar.groupby("Trimestre")[f"Horas {column} (h/sem)"].sum().max())
    center["demanda_nuevas_horas_anuales"] = float(calendar["Horas nuevas del trimestre"].sum())
    center["demanda_nuevas_horas_semana"] = float(calendar.groupby("Trimestre")["Horas nuevas del trimestre"].sum().max() / rules.weeks_per_quarter)
    center["saldo_planta_horas_semana"] = center["capacidad_planta_horas_semana"] - center["demanda_total_horas_semana"]
    center["nuevas_adicionales_por_rotacion"] = int(calendar["Nuevas adicionales por rotación"].sum())
    hours = []
    for index, row in distribution.iterrows():
        group = calendar.loc[calendar.apply(lambda item: profile_key(item) == profile_key(row), axis=1)]
        distribution.loc[index, "Fichas nuevas"] = int(group["Fichas nuevas"].sum())
        hours.append({**distribution.loc[index].to_dict(),
                      "Pico de fichas activas": int(group["Fichas activas"].max()),
                      "Horas totales (h/sem)": float(group["Horas totales (h/sem)"].max()),
                      "Horas anuales": float(group["Horas totales del trimestre"].sum()),
                      "Horas anuales nuevas": float(group["Horas nuevas del trimestre"].sum()),
                      "Técnicas anuales": float(group["Horas técnicas del trimestre"].sum()),
                      "Bilingüismo anual": float(group["Horas bilingüismo del trimestre"].sum()),
                      "Integralidad anual": float(group["Horas integralidad del trimestre"].sum())})
    for level in execution["levels"]:
        group = calendar.loc[calendar["Nivel"] == level["Nivel"]]
        level["Fichas nuevas"] = int(group["Fichas nuevas"].sum())
        accounted = level["Fichas nuevas"] + (level["Fichas que pasan"] if execution.get("target_basis") else 0)
        level["Fichas sobre la meta"] = max(0, accounted - level["Fichas según meta"])
        level["Cupos proyectados"] = accounted * rules.learners_per_ficha
        level["Horas anuales requeridas"] = float(group["Horas totales del trimestre"].sum())
        level["Horas anuales nuevas"] = float(group["Horas nuevas del trimestre"].sum())
    center["fichas_nuevas"] = int(distribution["Fichas nuevas"].sum())
    accounted = center["fichas_nuevas"] + (center["fichas_que_pasan"] if execution.get("target_basis") else 0)
    center["fichas_adicionales_sobre_meta"] = max(0, accounted - center["fichas_segun_meta"])
    center["aprendices_proyectados"] = center["cupos_teoricos"] = accounted * rules.learners_per_ficha
    if execution.get("target_basis"):
        center["cupos_nuevos"] = center["fichas_nuevas"] * rules.learners_per_ficha
        center["aprendices_que_pasan_estimados"] = center["fichas_que_pasan"] * rules.learners_per_ficha
    center["holgura_cupos"] = center["cupos_teoricos"] - center["meta_aprendices"]
    execution.update(distribution=records(distribution), distribution_basis="quarterly_v1", hours=hours,
                     calendar=records(calendar), quarterly=quarterly, quarter_endings=records(endings),
                     technical_quarterly=technical_rows, transversal_quarterly=transversal_rows,
                     technical=records(technical), transversal=records(transversal), summary=summary)
    execution["rules"]["intake_weights"] = list(rules.intake_weights)
    return execution
