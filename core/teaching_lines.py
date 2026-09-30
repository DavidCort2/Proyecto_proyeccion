"""Capacidad docente compartida entre programas compatibles de presencial."""
import json

from core.program_transitions import POLICY_PATH, active_program, program_key


TEACHING_LINE_BASIS = (
    "La planta y los contratistas comparten capacidad entre los programas compatibles de una misma línea, "
    "sin separar técnicos de tecnólogos ni jornadas. En cada trimestre se suman las horas técnicas de sus mallas, "
    "se descuenta la capacidad completa de su planta una sola vez y se divide el saldo entre la capacidad de "
    "un contratista, redondeando al final de la línea. Bilingüismo e Integralidad cubren todos los programas "
    "dentro de su respectivo perfil. Las horas libres de líneas o perfiles distintos no se intercambian. "
    "Las compatibilidades son las indicadas por el centro; las cantidades y las horas proceden de los reportes, "
    "las mallas y los parámetros del escenario."
)


def prepare_teaching_lines(distribution, instructors, transitions):
    configured = json.loads(POLICY_PATH.read_text(encoding="utf-8")).get("teaching_lines", [])
    present = {program_key(active_program(row["Especialidad"], transitions)) for row in distribution}
    present.update(program_key(active_program(row["Especialidad"], transitions))
                   for row in instructors.to_dict("records") if row["Área"] == "Técnica")
    names, membership, selected = set(), set(), []
    for line in configured:
        if (not isinstance(line, dict) or not isinstance(line.get("name"), str)
                or not line["name"].strip() or not isinstance(line.get("programs"), list)
                or len(line["programs"]) < 2
                or any(not isinstance(name, str) or not name.strip() for name in line["programs"])):
            raise ValueError("Revise los nombres y programas de las líneas docentes presenciales configuradas.")
        keys = [program_key(active_program(name, transitions)) for name in line["programs"]]
        name = program_key(line["name"])
        if name in names or len(set(keys)) != len(keys) or membership.intersection(keys):
            raise ValueError("Cada programa debe pertenecer a una sola línea docente presencial.")
        names.add(name)
        membership.update(keys)
        # Con un solo programa presente se conserva su nombre habitual de perfil.
        if len(present.intersection(keys)) >= 2:
            selected.append(line)
    if names.intersection(membership):
        raise ValueError("El nombre de una línea docente no puede coincidir con el de un programa.")
    return selected


def teaching_profile(program, transitions=(), lines=()):
    current = active_program(program, transitions)
    key = program_key(current)
    for line in lines:
        if any(key == program_key(active_program(name, transitions)) for name in line["programs"]):
            return line["name"]
    return current


def shared_teaching_staff(instructors, transitions, lines):
    """Agrupa perfiles sin copiar personas ni alterar el reporte de origen."""
    result = instructors.copy()
    technical = result["Área"].eq("Técnica")
    result.loc[technical, "Especialidad"] = result.loc[technical, "Especialidad"].map(
        lambda name: teaching_profile(name, transitions, lines))
    result.attrs["specialties"] = [
        {**row, "Especialidad": teaching_profile(row["Especialidad"], transitions, lines)
         if row["Área"] == "Técnica" else row["Especialidad"]}
        for row in instructors.attrs.get("specialties", [])
    ]
    return result


def teaching_line_rows(lines):
    return [{"Línea docente": line["name"], "Programa compatible": program,
             "Planta y contratación": "Capacidad compartida", "Origen": line.get("source", "Configuración del centro")}
            for line in lines for program in line["programs"]]
