#!/usr/bin/env python3
"""Test hors ligne de RM2870 — `pm_output` survit à un tube fermé.

Incident fondateur RM2868 : `pm-task-add … --porcelain | head -1` tuait le script
sur `BrokenPipeError` **après** le POST Redmine. Le ticket existait côté forge, sa
fiche PM non — un orphelin que rien ne signalait. Le tube fermé par le lecteur est
un usage normal (`head`, `| grep -q`, un pager quitté) : une sortie d'affichage ne
doit jamais interrompre une mutation déjà engagée.

Le volet `same_project` du même ticket a été traité en amont par RM2784 sur `dev` ;
il est couvert par `test_pm_task_import_same_project.py`, pas ici.

Aucun appel réseau.
"""
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


def main():
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
