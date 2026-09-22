"""Catálogo curricular persistente e independiente del reemplazo de planeaciones."""
from contextlib import closing
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from core.database import _connect
from core.curriculum import parse_curriculum, curriculum_key
from core.competency_identity import competency_identity, automatic_classification

SCHEMA = """
CREATE TABLE IF NOT EXISTS curricula (
    id INTEGER PRIMARY KEY, program TEXT NOT NULL, program_key TEXT NOT NULL,
    schedule TEXT NOT NULL, duration INTEGER NOT NULL CHECK(duration > 0),
    source_name TEXT NOT NULL, source_digest TEXT NOT NULL,
    UNIQUE(program_key, schedule)
);
CREATE TABLE IF NOT EXISTS competencies (
    id INTEGER PRIMARY KEY, name_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    transversal INTEGER NOT NULL DEFAULT 0 CHECK(transversal IN (0, 1)),
    transversal_area TEXT NOT NULL CHECK(transversal_area IN ('Bilingüismo', 'Integralidad')),
    classification_source TEXT NOT NULL DEFAULT 'automatic',
    classification_updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS curriculum_outcomes (
    curriculum_id INTEGER NOT NULL REFERENCES curricula(id),
    competency_id INTEGER NOT NULL REFERENCES competencies(id),
    quarter INTEGER NOT NULL CHECK(quarter > 0), result TEXT NOT NULL,
    weekly_hours REAL NOT NULL CHECK(weekly_hours >= 0), source_type TEXT NOT NULL,
    source_sheet TEXT NOT NULL, source_row INTEGER NOT NULL,
    source_competency TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(curriculum_id, source_sheet, source_row)
);
CREATE TABLE IF NOT EXISTS curriculum_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _refresh_automatic_classification(db):
    for cid, name in db.execute("SELECT id,name FROM competencies WHERE classification_source='automatic'").fetchall():
        types = [row[0] for row in db.execute("SELECT DISTINCT source_type FROM curriculum_outcomes WHERE competency_id=?", (cid,))]
        transversal, area = automatic_classification(name, types)
        db.execute("UPDATE competencies SET transversal=?,transversal_area=? WHERE id=?", (int(transversal), area, cid))


def _ensure_schema(db):
    """Migra una vez los datos existentes, sin tocar la última ejecución guardada."""
    db.executescript(SCHEMA)
    if db.execute("SELECT value FROM curriculum_metadata WHERE key='identity_version'").fetchone() == ('2',):
        return
    with db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(competencies)")}
        if "classification_source" not in columns:
            db.execute("ALTER TABLE competencies ADD COLUMN classification_source TEXT NOT NULL DEFAULT 'automatic'")
            db.execute("ALTER TABLE competencies ADD COLUMN classification_updated_at TEXT NOT NULL DEFAULT ''")
            # El esquema anterior no guardaba procedencia. Sus marcas positivas
            # eran decisiones explícitas; los ceros eran el valor inicial.
            db.execute("UPDATE competencies SET classification_source='manual' WHERE transversal=1")
        columns = {row[1] for row in db.execute("PRAGMA table_info(curriculum_outcomes)")}
        if "source_competency" not in columns:
            db.execute("ALTER TABLE curriculum_outcomes ADD COLUMN source_competency TEXT NOT NULL DEFAULT ''")
        db.execute("""UPDATE curriculum_outcomes SET source_competency=(
            SELECT name FROM competencies WHERE id=competency_id) WHERE source_competency=''""")
        groups = defaultdict(list)
        for row in db.execute("SELECT id,name,transversal,transversal_area,classification_source,classification_updated_at FROM competencies"):
            key, display = competency_identity(row[1])
            groups[(key, display)].append(row)
        for (key, display), rows in groups.items():
            keeper = min(row[0] for row in rows)
            chosen = max(rows, key=lambda row: (row[4] == 'manual', row[5], row[0]))
            for row in rows:
                if row[0] != keeper:
                    db.execute("UPDATE curriculum_outcomes SET competency_id=? WHERE competency_id=?", (keeper, row[0]))
                    db.execute("DELETE FROM competencies WHERE id=?", (row[0],))
            db.execute("""UPDATE competencies SET name_key=?,name=?,transversal=?,transversal_area=?,
                       classification_source=?,classification_updated_at=? WHERE id=?""",
                       (key, display, *chosen[2:], keeper))
        for cid, program, schedule in db.execute("SELECT id,program,schedule FROM curricula").fetchall():
            db.execute("UPDATE curricula SET program_key=? WHERE id=?", (curriculum_key(program, schedule)[0], cid))
        _refresh_automatic_classification(db)
        db.execute("INSERT OR REPLACE INTO curriculum_metadata VALUES ('identity_version','2')")


def import_curricula(path, files):
    """Valida todo el lote antes de escribir; reemplaza solo la misma malla."""
    parsed = {}
    for filename, content in files:
        item = parse_curriculum(content, filename)
        key = curriculum_key(item["program"], item["schedule"])
        if key in parsed and parsed[key]["source_digest"] != item["source_digest"]:
            raise ValueError(f"Dos archivos distintos corresponden a {item['program']} · {item['schedule']}.")
        parsed[key] = item
    if not parsed:
        raise ValueError("Seleccione al menos una malla curricular.")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as db:
        _ensure_schema(db)
        with db:
            for item in parsed.values():
                db.execute("""INSERT INTO curricula (program, program_key, schedule, duration, source_name, source_digest)
                           VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(program_key, schedule) DO UPDATE SET
                           program=excluded.program, duration=excluded.duration,
                           source_name=excluded.source_name, source_digest=excluded.source_digest""",
                           tuple(item[k] for k in ("program", "program_key", "schedule", "duration", "source_name", "source_digest")))
                cid = db.execute("SELECT id FROM curricula WHERE program_key=? AND schedule=?",
                                 (item["program_key"], item["schedule"])).fetchone()[0]
                db.execute("DELETE FROM curriculum_outcomes WHERE curriculum_id=?", (cid,))
                for row in item["outcomes"]:
                    db.execute("INSERT INTO competencies (name_key, name, transversal_area) VALUES (?, ?, ?) ON CONFLICT(name_key) DO NOTHING",
                               (row["competency_key"], row["competency"], "Integralidad"))
                    competency_id = db.execute("SELECT id FROM competencies WHERE name_key=?", (row["competency_key"],)).fetchone()[0]
                    db.execute("""INSERT INTO curriculum_outcomes (curriculum_id,competency_id,quarter,result,weekly_hours,
                               source_type,source_sheet,source_row,source_competency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (cid, competency_id, row["quarter"], row["result"], row["weekly_hours"], row["source_type"], row["source_sheet"], row["source_row"], row["source_competency"]))
            _refresh_automatic_classification(db)
    return load_curricula(path)


def load_curricula(path):
    empty = {"curricula": [], "competencies": []}
    if not Path(path).exists():
        return empty
    with closing(_connect(path)) as db:
        if not db.execute("SELECT name FROM sqlite_master WHERE name='curricula'").fetchone():
            return empty
        _ensure_schema(db)
        db.execute("BEGIN")
        db.row_factory = sqlite3.Row
        curricula = []
        for raw in db.execute("SELECT * FROM curricula ORDER BY program_key, schedule"):
            item = dict(raw)
            cid = item.pop("id")
            item["outcomes"] = [dict(row) for row in db.execute("""
                SELECT o.quarter, c.name_key AS competency_key, c.name AS competency, o.result,
                       o.weekly_hours, o.source_type, o.source_sheet, o.source_row, o.source_competency
                FROM curriculum_outcomes o JOIN competencies c ON c.id=o.competency_id
                WHERE curriculum_id=? ORDER BY o.quarter, o.source_row""", (cid,))]
            curricula.append(item)
        competencies = [dict(row) for row in db.execute("""
            SELECT name_key AS key, name, transversal, transversal_area, classification_source FROM competencies
            WHERE id IN (SELECT competency_id FROM curriculum_outcomes) ORDER BY name_key""")]
        for item in competencies:
            item["transversal"] = bool(item["transversal"])
        return {"curricula": curricula, "competencies": competencies}


def save_competencies(path, rows):
    rows = list(rows)
    if len({row["key"] for row in rows}) != len(rows):
        raise ValueError("Hay competencias repetidas en la clasificación.")
    with closing(_connect(path)) as db:
        _ensure_schema(db)
        with db:
            for row in rows:
                if type(row["transversal"]) is not bool or row["transversal_area"] not in {"Bilingüismo", "Integralidad"}:
                    raise ValueError("Revise la clasificación de las competencias.")
                current = db.execute("SELECT transversal,transversal_area FROM competencies WHERE name_key=?", (row["key"],)).fetchone()
                if current is None:
                    raise ValueError("El catálogo cambió. Recargue las competencias antes de guardar.")
                desired = (int(row["transversal"]), row["transversal_area"])
                if current != desired:
                    db.execute("""UPDATE competencies SET transversal=?,transversal_area=?,classification_source='manual',
                               classification_updated_at=? WHERE name_key=?""",
                               (*desired, datetime.now(timezone.utc).isoformat(), row["key"]))
