#!/usr/bin/env python3
"""Tests offline de `same_project()` dans `pm-task-import` (RM2784).

Lancer : python3 scripts/test_pm_task_import_same_project.py
Aucun réseau : le provider est une doublure qui compte ses appels.

Contexte du bug : `GET /issues/<id>.json` ne rend du projet que `{id, name}` —
jamais son `identifier`. La comparaison se faisait pourtant sur cet identifier
absent, ce qui mettait en faux négatif TOUTE fiche déclarant `project_id` sous sa
forme textuelle (`calicote-dolibarr`, `matnat-infra`… soit le cas normal). Seules
les fiches déclarant l'id numérique passaient. L'adoption exigeait donc `--force`
dans le cas nominal, ce qui vidait le garde-fou de son sens : `--force` est censé
signaler un écart *voulu*, pas être la façon habituelle de faire.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("pm_task_import", str(_HERE / "pm-task-import.py"))
pti = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pti)


class FakeProvider:
    """Rend l'identifier que la forge connaît, et compte les appels."""

    def __init__(self, by_id=None, boom=False):
        self.by_id = by_id or {}
        self.boom = boom
        self.calls = 0

    def fetch_project(self, project_id):
        self.calls += 1
        if self.boom:
            raise RuntimeError("forge muette")
        return self.by_id.get(int(project_id), {})


CALICOTE = {"id": 11, "name": "Calicote Dolibarr"}          # tel que rendu par /issues
SFY = {"id": 2, "name": "SFY Dolibarr"}
FORGE = {11: {"id": 11, "identifier": "calicote-dolibarr"},
         2: {"id": 2, "identifier": "sfy-dolibarr"}}

_failures = []


def check(label, got, want):
    if got != want:
        _failures.append(f"{label} : attendu {want!r}, obtenu {got!r}")
    print(f"[{'OK ' if got == want else 'KO '}] {label}")


def main():
    # Le cas du bug : forme textuelle déclarée, identifier absent du ticket.
    p = FakeProvider(FORGE)
    check("forme textuelle, bon projet",
          pti.same_project("calicote-dolibarr", dict(CALICOTE), provider=p), True)
    check("  un seul appel projet", p.calls, 1)

    # Forme numérique : tranchée sans appel réseau, comme avant le correctif.
    p = FakeProvider(FORGE)
    check("forme numérique, bon projet",
          pti.same_project("11", dict(CALICOTE), provider=p), True)
    check("  aucun appel projet", p.calls, 0)

    # Un écart réel doit rester refusé — le correctif ne doit rien laisser passer.
    p = FakeProvider(FORGE)
    check("forme textuelle, mauvais projet",
          pti.same_project("calicote-dolibarr", dict(SFY), provider=p), False)

    # Rien de déclaré : on ne tranche pas (l'appelant émet un warning).
    check("rien de déclaré",
          pti.same_project(None, dict(CALICOTE), provider=FakeProvider(FORGE)), None)

    # Sans provider (appelant qui ne le passe pas) : comportement historique.
    check("sans provider, forme textuelle",
          pti.same_project("calicote-dolibarr", dict(CALICOTE)), False)

    # Forge en échec : on refuse plutôt que de laisser passer à l'aveugle.
    p = FakeProvider(FORGE, boom=True)
    check("forge muette", pti.same_project("calicote-dolibarr", dict(CALICOTE), provider=p), False)

    # L'identifier résolu est mémorisé dans le dict, pour le message d'erreur.
    ip = dict(SFY)
    pti.same_project("calicote-dolibarr", ip, provider=FakeProvider(FORGE))
    check("identifier mémorisé pour le message", ip.get("identifier"), "sfy-dolibarr")

    # Un ticket dont la réponse porte DÉJÀ l'identifier ne déclenche aucun appel.
    p = FakeProvider(FORGE)
    check("identifier déjà présent",
          pti.same_project("calicote-dolibarr",
                           {"id": 11, "name": "X", "identifier": "calicote-dolibarr"},
                           provider=p), True)
    check("  aucun appel projet", p.calls, 0)

    print()
    if _failures:
        for f in _failures:
            print("ÉCHEC :", f)
        return 1
    print("Tous les cas passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
