#!/usr/bin/env python3
"""Le verrou de pm-wiki-sync ne vit pas dans le volume PM versionné (RM2825).

Lancer : python3 scripts/test_pm_wiki_sync_lock_hors_git.py

Le dossier d'état `.mmi-pm/.wiki-sync/` est versionné. Y déposer un `.lock` en fait un
fichier que git peut créer, supprimer ou restaurer sous les pieds du processus qui le
détient — et deux workers parallèles produisent des commits qui se marchent dessus sur un
fichier qui n'a aucune raison d'être partagé.

On vérifie donc trois choses : le verrou est écrit ailleurs, le dossier d'état reçoit un
`.gitignore` de rattrapage, et la sérialisation fonctionne toujours.
"""
import importlib.util
import os
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load():
    spec = importlib.util.spec_from_file_location("pm_wiki_sync", SCRIPTS / "pm-wiki-sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = _load()

    with tempfile.TemporaryDirectory() as d:
        # on imite la disposition réelle : <projet PM>/.mmi-pm/.wiki-sync/
        etat = Path(d) / "un-projet" / ".mmi-pm" / ".wiki-sync"

        with m.ProjectLock(etat) as verrou:
            # 1. le verrou n'est PAS dans le dossier versionné
            assert not (etat / ".lock").exists(), \
                "un .lock subsiste dans le dossier d'état : %s" % (etat / ".lock")
            assert etat not in verrou.path.parents, \
                "le verrou est encore sous le dossier d'état : %s" % verrou.path
            assert verrou.path.exists(), "le verrou n'a pas été créé : %s" % verrou.path

            # 2. le dossier d'état porte un .gitignore de rattrapage
            ignore = etat / ".gitignore"
            assert ignore.exists(), "pas de .gitignore de rattrapage dans le dossier d'état"
            assert ".lock" in ignore.read_text(encoding="utf-8")

        # 3. la sérialisation marche toujours, et deux projets ne partagent pas leur verrou
        autre = Path(d) / "un-autre-projet" / ".mmi-pm" / ".wiki-sync"
        with m.ProjectLock(etat) as a, m.ProjectLock(autre) as b:
            assert a.path != b.path, "deux projets partagent le même verrou : %s" % a.path

        # 4. un chemin explicite reste respecté (utile aux tests et au dépannage)
        impose = Path(d) / "impose.lock"
        with m.ProjectLock(etat, lock_path=impose) as v:
            assert v.path == impose

    print("OK — verrou hors du volume versionné, .gitignore de rattrapage, un verrou par projet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
