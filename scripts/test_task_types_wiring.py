#!/usr/bin/env python3
"""Tests de câblage de la taxonomie `type` (RM2379).

Invariants : chaque type NORMS valide (validate-task.VALID_TYPES) est câblé de
bout en bout — tracker (pm-task-add.TYPE_TO_TRACKER), label (TYPE_LABELS),
activité de temps (redmine.reference.yml :: type_to_activity) — et le CF 20
« Task type » (taxonomie fine) ne référence que des types valides, en bijection
(un value_id par type). Vérifie aussi le câblage spécifique du type
`configuration` ajouté par RM2379 (tracker Tâche/4, activité 13, CF20 = 22).

Lancer : python3 scripts/test_task_types_wiring.py
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(_HERE / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate_task = _load("validate_task", "validate-task.py")
pm_task_add = _load("pm_task_add", "pm-task-add.py")
sys.path.insert(0, str(_HERE))
import redmine_utils  # noqa: E402

VALID_TYPES = validate_task.VALID_TYPES
TYPE_TO_TRACKER = pm_task_add.TYPE_TO_TRACKER
TYPE_LABELS = pm_task_add.TYPE_LABELS
type_to_activity = redmine_utils.load_reference().get("type_to_activity") or {}
tt_cf_id, tt_values = redmine_utils.task_type_cf()


def test_all_types_have_tracker_and_label():
    missing_tracker = VALID_TYPES - set(TYPE_TO_TRACKER)
    missing_label = VALID_TYPES - set(TYPE_LABELS)
    assert not missing_tracker, f"types sans tracker : {missing_tracker}"
    assert not missing_label, f"types sans label : {missing_label}"


def test_all_types_have_activity():
    missing = VALID_TYPES - set(type_to_activity)
    assert not missing, f"types sans activité de temps : {missing}"


def test_task_type_cf_only_valid_types_bijective():
    unknown = set(tt_values) - VALID_TYPES
    assert not unknown, f"task_type_cf référence des types inconnus : {unknown}"
    ids = list(tt_values.values())
    assert len(ids) == len(set(ids)), f"value_id CF20 dupliqué : {sorted(ids)}"


def test_configuration_wiring():
    assert "configuration" in VALID_TYPES
    assert TYPE_TO_TRACKER["configuration"] == 4, "configuration → tracker Tâche (4)"
    assert "configuration" in TYPE_LABELS
    assert redmine_utils.activity_for_type("configuration") == 13, \
        "configuration → activité SysAdmin/Conf/Debug (13)"
    assert tt_cf_id == 20 and tt_values.get("configuration") == 22, \
        "configuration → CF20 « Task type » valeur 22 (Config)"


def test_cf20_reverse_reconstructs_configuration():
    # Chemin inverse de redmine-fetch-task : value_id CF20 → type NORMS fin.
    rev = {str(v): k for k, v in tt_values.items()}
    assert rev.get("22") == "configuration"


def test_list_types_exposes_configuration():
    p = subprocess.run(
        [sys.executable, str(_HERE / "pm-task-add.py"), "--list-types"],
        capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, f"--list-types rc={p.returncode} : {p.stderr}"
    data = json.loads(p.stdout)
    values = {t["value"] for t in data}
    assert "configuration" in values, f"--list-types sans configuration : {sorted(values)}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok    {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name} : {exc}")
    sys.exit(1 if failures else 0)
