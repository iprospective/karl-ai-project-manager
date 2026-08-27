#!/usr/bin/env python3
"""Test hors ligne de RM2870 — deux défauts vus sur un même incident (RM2868).

1. `pm-task-import.same_project()` comparait un `redmine.project_id` TEXTUEL au
   dict projet de l'API des issues, qui ne rend que `{id, name}` : le garde-fou se
   déclenchait sur le cas nominal et `--force` devenait le chemin normal.
2. `pm-task-add … --porcelain | head -1` tuait le script sur `BrokenPipeError`
   APRÈS le POST Redmine — ticket créé, aucune fiche PM.

Aucun appel réseau : `redmine_utils.fetch_project` est doublé.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from test_support import hermetic_core, subprocess_env                # noqa: E402

hermetic_core()
FAILURES = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f" {detail}"))
    if not cond:
        FAILURES.append(label)


def load_import_module():
    """`pm-task-import.py` n'est pas importable par son nom (tiret)."""
    spec = importlib.util.spec_from_file_location(
        "pm_task_import_under_test", SCRIPTS / "pm-task-import.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print("· same_project : project_id textuel vs API qui ne rend que {id, name}")
    mod = load_import_module()
    calls = []

    def fake_fetch_project(ref, **kw):
        calls.append(ref)
        table = {"calicote-dolibarr": {"id": 11, "identifier": "calicote-dolibarr"},
                 "matnat-infra": {"id": 42, "identifier": "matnat-infra"}}
        return table.get(str(ref))

    mod.redmine_utils.fetch_project = fake_fetch_project

    issue_ok = {"id": 11, "name": "Calicote Dolibarr"}               # pas d'identifier : c'est le point
    check("textuel + bon projet → True",
          mod.same_project("calicote-dolibarr", issue_ok) is True)
    check("textuel + AUTRE projet → False",
          mod.same_project("matnat-infra", issue_ok) is False)
    check("id numérique déclaré → True, sans appel réseau",
          mod.same_project(11, issue_ok) is True and "11" not in [str(c) for c in calls])
    check("id numérique d'un autre projet → False",
          mod.same_project(99, issue_ok) is False)
    check("rien de déclaré → None (on ne tranche pas)",
          mod.same_project(None, issue_ok) is None)
    check("projet déclaré introuvable → None (on ne conclut pas à l'écart)",
          mod.same_project("projet-inexistant", issue_ok) is None)

    print("· pm_output : un tube fermé ne tue plus une mutation en cours")
    prog = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "from test_support import hermetic_core\n"
        "hermetic_core()\n"
        "from pm_output import out\n"
        "out.configure(porcelain=True)\n"
        "out.value(2868)\n"
        "for i in range(500):\n"
        "    out.value(i)\n"
        "    out.op('add', rm=2868, extra='slug')\n"
        "sys.stderr.write('SURVECU\\n')\n"
    )
    env = subprocess_env()
    p1 = subprocess.Popen([sys.executable, "-c", prog], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, cwd=str(SCRIPTS))
    p2 = subprocess.Popen(["head", "-1"], stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    first = p2.communicate()[0].decode().strip()
    err = p1.stderr.read().decode()
    p1.wait()

    check("la 1re ligne porcelain est bien lue", first == "2868", repr(first))
    check("le script survit à la fermeture du tube", "SURVECU" in err, err[-200:])
    check("aucune BrokenPipeError ne remonte", "BrokenPipeError" not in err, err[-200:])
    check("code de sortie 0", p1.returncode == 0, str(p1.returncode))

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        return 1
    print("✓ RM2870 : tout vert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
