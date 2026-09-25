"""Cronogramas virtuales y decisiones docentes, separados de las mallas."""
from contextlib import closing
import json
from pathlib import Path

from core.database import _connect
from core.virtual_schedule import finite_hours, lective_activities, parse_virtual_schedule
from core.virtual_competencies import assign_teaching_profiles, suggest_classifications, teaching_profile
from core.curriculum import name_key

SCHEMA = """
CREATE TABLE IF NOT EXISTS virtual_schedules (
    program_key TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""


def _validate_exclusive_profile(activity, kind, profile):
    required = activity.get("required_teaching_profile")
    if required and (kind != "Transversal" or name_key(profile) != name_key(required)):
        raise ValueError(f"La competencia {activity['competency']} requiere Tipo Transversal y el perfil exclusivo {required}, "
                         "según la configuración del centro. No puede compartir la capacidad de otros perfiles.")


def load_virtual_schedules(path):
    if not Path(path).exists():
        return {"schedules": []}
    with closing(_connect(path)) as db:
        if not db.execute("SELECT name FROM sqlite_master WHERE name='virtual_schedules'").fetchone():
            return {"schedules": []}
        catalog = {"schedules": [json.loads(row[0]) for row in db.execute("SELECT payload FROM virtual_schedules ORDER BY program_key")]}
        assign_teaching_profiles([row for item in catalog["schedules"] for row in lective_activities(item)])
        return catalog


def import_virtual_schedules(path, files):
    parsed = {}
    for filename, content in files:
        item = parse_virtual_schedule(content, filename)
        if item["program_key"] in parsed and parsed[item["program_key"]]["source_digest"] != item["source_digest"]:
            raise ValueError(f"Hay dos versiones del cronograma de {item['program']} en la misma carga.")
        parsed[item["program_key"]] = item
    if not parsed:
        raise ValueError("Seleccione al menos un cronograma Excel.")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as db:
        db.executescript(SCHEMA)
        with db:
            classifications = {}
            profiles = {}
            for saved, in db.execute("SELECT payload FROM virtual_schedules"):
                for activity in json.loads(saved)["activities"]:
                    if activity.get("classification_source") == "manual":
                        classifications[activity["competency"]] = activity["teaching_type"]
                    if activity.get("profile_source") == "manual":
                        profiles[activity["competency"]] = teaching_profile(activity)
            for key, item in parsed.items():
                old = db.execute("SELECT payload FROM virtual_schedules WHERE program_key=?", (key,)).fetchone()
                if old:
                    old = {row["id"]: row for row in json.loads(old[0])["activities"]}
                    for row in item["activities"]:
                        previous = old.get(row["id"])
                        if previous and previous.get("classification_source") == "manual":
                            row["teaching_type"] = previous.get("teaching_type")
                            row["classification_source"] = "manual"
                            # Un cambio en las fechas de la ficha de ejemplo no altera
                            # la plantilla ni invalida las horas docentes guardadas.
                            if all(previous.get(field) == row[field] for field in ("activity", "start_offset", "duration", "duration_unit", "competency")):
                                row["instructor_hours"] = previous.get("instructor_hours")
                for row in item["activities"]:
                    if row["competency"] in classifications:
                        row.update(teaching_type=classifications[row["competency"]], classification_source="manual")
                    if row["competency"] in profiles:
                        row.update(teaching_profile=profiles[row["competency"]], profile_source="manual")
                db.execute("INSERT OR REPLACE INTO virtual_schedules VALUES (?, ?)",
                           (key, json.dumps(item, ensure_ascii=False, allow_nan=False)))
            # Una competencia compartida tiene una sola decisión, usando el texto
            # de todos los programas y respetando las correcciones del usuario.
            schedules = [json.loads(row[0]) for row in db.execute("SELECT payload FROM virtual_schedules")]
            activities = [row for item in schedules for row in lective_activities(item)]
            manual = {row["competency"]: row["teaching_type"] for row in activities
                      if row.get("classification_source") == "manual"}
            suggest_classifications(activities)
            for row in activities:
                if row["competency"] in manual:
                    row.update(teaching_type=manual[row["competency"]], classification_source="manual")
            assign_teaching_profiles(activities)
            for item in schedules:
                db.execute("UPDATE virtual_schedules SET payload=? WHERE program_key=?",
                           (json.dumps(item, ensure_ascii=False, allow_nan=False), item["program_key"]))
    return load_virtual_schedules(path)


def save_virtual_activity_settings(path, program_key, source_digest, settings):
    with closing(_connect(path)) as db:
        with db:
            saved = db.execute("SELECT payload FROM virtual_schedules WHERE program_key=?", (program_key,)).fetchone()
            if saved is None:
                raise ValueError("El cronograma ya no existe. Recargue la pantalla.")
            item = json.loads(saved[0])
            if item["source_digest"] != source_digest:
                raise ValueError("El cronograma cambió en otra sesión. Recargue antes de guardar la clasificación.")
            keyed = {row["id"]: row for row in settings}
            activities = lective_activities(item)
            assign_teaching_profiles(activities)
            required_ids = {row["id"] for row in activities}
            source_ids = {row["id"] for row in item["activities"]}
            if len(keyed) != len(settings) or not required_ids <= set(keyed) <= source_ids:
                raise ValueError("La clasificación debe corresponder a todas las actividades lectivas del cronograma.")
            # Conserva los datos históricos productivos sin permitir que una
            # edición nueva los active ni exigir que el usuario los complete.
            for row in activities:
                choice = keyed[row["id"]]
                if choice["teaching_type"] not in {None, "Técnico", "Transversal"}:
                    raise ValueError("Seleccione Técnico o Transversal para las actividades.")
                _validate_exclusive_profile(row, choice["teaching_type"], teaching_profile(row))
                row["teaching_type"] = choice["teaching_type"]
                row["classification_source"] = "manual"
                row["instructor_hours"] = (None if choice["instructor_hours"] is None else
                                           finite_hours(choice["instructor_hours"], row["activity_code"]))
            db.execute("UPDATE virtual_schedules SET payload=? WHERE program_key=?",
                       (json.dumps(item, ensure_ascii=False, allow_nan=False), program_key))
    return load_virtual_schedules(path)


def save_virtual_competencies(path, expected_digests, settings):
    with closing(_connect(path)) as db:
        with db:
            schedules = [json.loads(row[0]) for row in db.execute("SELECT payload FROM virtual_schedules ORDER BY program_key")]
            if {row["program_key"]: row["source_digest"] for row in schedules} != expected_digests:
                raise ValueError("Los cronogramas cambiaron. Recargue antes de guardar la clasificación.")
            assign_teaching_profiles([row for item in schedules for row in lective_activities(item)])
            required = {row["competency"] for item in schedules for row in lective_activities(item)}
            choices = {row["Competencia"]: row["Tipo"] for row in settings}
            if len(choices) != len(settings) or set(choices) != required or any(value not in {"Técnico", "Transversal"} for value in choices.values()):
                raise ValueError("Clasifique todas las competencias una sola vez como Técnico o Transversal.")
            prior_profiles = {row["competency"]: teaching_profile(row) for item in schedules for row in lective_activities(item)}
            profiles, canonical = {}, {}
            for choice in settings:
                code = choice["Competencia"]
                profile = choice.get("Perfil docente", prior_profiles[code])
                if not isinstance(profile, str) or not name_key(profile):
                    raise ValueError("Indique un perfil docente para cada competencia; use el mismo nombre solo si puede compartir instructor.")
                profiles[code] = canonical.setdefault(name_key(profile), " ".join(profile.split()))
            for item in schedules:
                for row in lective_activities(item):
                    _validate_exclusive_profile(row, choices[row["competency"]], profiles[row["competency"]])
                    if row["teaching_type"] != choices[row["competency"]]:
                        row.update(teaching_type=choices[row["competency"]], classification_source="manual")
                    if teaching_profile(row) != profiles[row["competency"]]:
                        row.update(teaching_profile=profiles[row["competency"]], profile_source="manual")
                db.execute("UPDATE virtual_schedules SET payload=? WHERE program_key=?", (json.dumps(item, ensure_ascii=False, allow_nan=False), item["program_key"]))
    return load_virtual_schedules(path)
