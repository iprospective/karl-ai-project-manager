#!/usr/bin/env python3
"""Tests offline du garde-fou checklist de `pm-task-status-update` (RM2884).

Lancer : python3 scripts/test_pm_task_status_checklist.py
Aucun réseau.

Contexte : `--allow-unchecked` était un drapeau nu. Il servait donc à franchir le
contrôle sans faire le travail que ce contrôle réclamait, et sans laisser de
trace — un contournement muet est indiscernable d'un oubli. Audit du parc au
2026-08-28 : 28 tickets partis en test ou en clôture avec ZÉRO critère coché,
dont 24 fermés ainsi.

Le placeholder `- [ ] (à compléter)` est distingué à dessein : là, il n'y a rien
à cocher, il y a des critères à écrire. 409 tickets du parc sont dans ce cas, et
les confondre avec les 28 précédents brouillerait le diagnostic.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_tsu", str(_HERE / "pm-task-status-update.py"))
tsu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsu)

VIDE = "## Critères\n\n- [ ] un\n- [ ] deux\n- [ ] trois\n"
PARTIEL = "## Critères\n\n- [x] un\n- [x] deux\n- [ ] trois\n"
COMPLET = "## Critères\n\n- [x] un\n- [x] deux\n"
PLACEHOLDER = "## Critères d'acceptation\n\n- [ ] (à compléter)\n"
PLACEHOLDER_PLUS = "## Critères\n\n- [ ] (à compléter)\n- [ ] un vrai critère\n"
AUCUNE = "## Contexte\n\nPas de checklist ici.\n"

_fails = []


def check(label, got, want):
    if got != want:
        _fails.append(f"{label} : attendu {want!r}, obtenu {got!r}")
    print(f"[{'OK ' if got == want else 'KO '}] {label}")


def main():
    check("vide : 3 non cochés", tsu.count_unchecked(VIDE), 3)
    check("vide : 0 coché", tsu.count_checked(VIDE), 0)
    check("partiel : 1 non coché", tsu.count_unchecked(PARTIEL), 1)
    check("partiel : 2 cochés", tsu.count_checked(PARTIEL), 2)
    check("complet : 0 non coché", tsu.count_unchecked(COMPLET), 0)
    check("aucune checklist : 0/0", (tsu.count_unchecked(AUCUNE), tsu.count_checked(AUCUNE)), (0, 0))

    # Le placeholder est un cas à part : rien à cocher, tout à écrire.
    check("placeholder reconnu", tsu.checklist_is_placeholder(PLACEHOLDER), True)
    check("vrais critères ≠ placeholder", tsu.checklist_is_placeholder(VIDE), False)
    check("placeholder + vrai critère ≠ placeholder pur",
          tsu.checklist_is_placeholder(PLACEHOLDER_PLUS), False)
    check("description vide ≠ placeholder", tsu.checklist_is_placeholder(""), False)
    check("None ne casse pas", tsu.count_unchecked(None), 0)

    print()
    if _fails:
        for f in _fails:
            print("ÉCHEC :", f)
        return 1
    print("Tous les cas passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
