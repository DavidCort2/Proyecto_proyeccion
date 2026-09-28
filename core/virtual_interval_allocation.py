"""Asigna carga semanal a personas únicas, con apoyo técnico al perfil compatible."""
from collections import defaultdict
import math


def allocate_interval(tasks, labels, plant, rules, previous, support_key):
    """La carga técnica tiene prioridad; la capacidad residual nunca se duplica."""
    people, allocations = {}, defaultdict(list)
    remaining = {key: set(tasks[key]) for key in labels}
    contractors = defaultdict(list)

    def register(person, key):
        identifier = person["Instructor"]
        if identifier not in people:
            capacity = rules.weekly_plant_direct_hours if person["Vinculación"] == "Planta" else rules.weekly_contractor_hours
            people[identifier] = {**person, "home_key": key, "capacity": capacity, "used": 0.0}
        return people[identifier]

    for key in sorted(labels):
        for person in plant[key]:
            register(person, key)

    def assign(person, key):
        rate = rules.weekly_hours_for(key[0])
        slots = math.floor((person["capacity"] - person["used"] + 1e-9) / rate)
        candidates = remaining[key]
        former = {unit for former_key, unit in previous.get(person["Instructor"], set()) if former_key == key}
        units = sorted(former & candidates)[:slots]
        units.extend(sorted(candidates - set(units))[:slots - len(units)])
        for unit in units:
            allocations[person["Instructor"]].append((key, unit))
        candidates.difference_update(units)
        person["used"] += len(units) * rate

    def assign_plant(key):
        for person in plant[key]:
            assign(people[person["Instructor"]], key)

    def hire(key):
        capacity = math.floor(rules.weekly_contractor_hours / rules.weekly_hours_for(key[0]))
        for slot in range(1, math.ceil(len(remaining[key]) / capacity) + 1):
            person = register({"Instructor": f"Contrato · {key[0]} · {labels[key]} · {slot}",
                               "Nombre": "Por contratar", "Cédula": "", "Vinculación": "Contratista", "Cupo": slot}, key)
            contractors[key].append(person)
            assign(person, key)

    # Los contratistas técnicos existen solo mientras hay demanda de su programa.
    # No se crean ni prolongan contratos técnicos para obtener capacidad de apoyo.
    for key in sorted(labels):
        if key[0] == "Técnico":
            assign_plant(key)
            hire(key)
    for key in sorted(labels):
        if key[0] != "Transversal":
            continue
        assign_plant(key)
        if key == support_key:
            helpers = sorted((person for person in people.values() if person["home_key"][0] == "Técnico"),
                             key=lambda person: (person["Vinculación"] != "Planta", person["Instructor"]))
            for person in helpers:
                assign(person, key)
        hire(key)
    if any(remaining.values()):
        raise ValueError("La capacidad calculada no cubre todas las fichas del intervalo.")
    if any(person["used"] > person["capacity"] + 1e-9 for person in people.values()):
        raise ValueError("La asignación supera la capacidad semanal de un instructor.")
    return people, allocations, contractors
