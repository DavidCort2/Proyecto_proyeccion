import sqlite3

from core.curriculum_store import import_curricula, load_curricula
from core.database import database_reset_version, load_planning, reset_planning_database, save_planning
from test_curriculum import curriculum_catalog, curriculum_files, run_plan


def test_reset_removes_reports_mallas_classification_and_execution(tmp_path, curriculum_catalog, curriculum_files):
    path = tmp_path / "planning.sqlite3"
    import_curricula(path, curriculum_files)
    staff, plan = run_plan(curriculum_catalog)
    save_planning(path, staff, plan)
    version = database_reset_version(path)
    assert all(count == 0 for count in reset_planning_database(path).values())
    assert database_reset_version(path) == version + 1
    assert load_planning(path) is None
    assert load_curricula(path) == {"curricula": [], "competencies": []}
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert len(import_curricula(path, curriculum_files)["curricula"]) == 2
