"""Instantánea conjunta de Complementaria, sin escribir en las bases de Titulada."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def load_complementary(path):
    if not Path(path).exists():
        return None
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT revision, saved_at, payload FROM complementary_execution WHERE id=1").fetchone()
    return {**json.loads(row[2]), "revision": row[0], "saved_at": row[1]} if row else None


def save_complementary(path, execution, *, expected_revision=0):
    payload = json.dumps(execution, ensure_ascii=False, allow_nan=False)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS complementary_execution "
                           "(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, saved_at TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT revision FROM complementary_execution WHERE id=1").fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise ValueError("Complementaria cambió en otra sesión. Recargue antes de guardar para conservar sus reservas de horas.")
            connection.execute("INSERT OR REPLACE INTO complementary_execution VALUES (1, ?, ?, ?)",
                               (revision + 1, datetime.now(timezone.utc).isoformat(timespec="seconds"), payload))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return load_complementary(path)
