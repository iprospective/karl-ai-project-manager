#!/usr/bin/env python3
"""Tests offline du dispatcher mmi-pm (RM2580 étape 3a).

Lancer : python3 scripts/test_mmi_pm.py
Couvre : résolution des candidats pm-<cmd>, liste des sous-commandes (exclut
modules pm_* et tests), routage via os.execv (monkeypatch, aucun exec réel),
sous-commande inconnue → SystemExit, override PM_CORE_DIR.
"""
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.pop("PM_CORE_DIR", None)  # hermétique : mmi-pm doit s'auto-localiser sur HERE


def _load(name="mmi_pm"):
    spec = importlib.util.spec_from_file_location(name, HERE / "mmi-pm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    mmi = _load()

    # 1. SCRIPTS auto-localisé sur le dossier du script (pas de PM_CORE_DIR)
    assert mmi.SCRIPTS == HERE, (mmi.SCRIPTS, HERE)
    print("✓ SCRIPTS auto-localisé sur le dossier des scripts")

    # 2. _candidates : pm-<cmd>.py puis pm-<cmd>
    cands = mmi._candidates("task-add")
    assert cands == [HERE / "pm-task-add.py", HERE / "pm-task-add"], cands
    print("✓ _candidates = [pm-<cmd>.py, pm-<cmd>]")

    # 3. _list_commands : contient les commandes réelles, exclut les modules pm_*
    #    et les fichiers de test. RM2749 : le filtre portait sur « test » n'importe
    #    où dans le nom et masquait des VERBES réels (`test`, `cockpit-test-env`) —
    #    utilisables mais invisibles, donc introuvables pour qui ne les connaît pas.
    cmds = mmi._list_commands()
    assert "task-add" in cmds and "session-status" in cmds, cmds[:5]
    assert "test" in cmds and "cockpit-test-env" in cmds, "les verbes réels sont listés"
    assert not any(c.startswith("_") or c.startswith("test_") for c in cmds), cmds
    assert "paths" not in cmds  # pm_paths.py = module (underscore), pas une commande
    print(f"✓ _list_commands ({len(cmds)}) : commandes connues présentes, modules/tests exclus")

    # 4. routage : main(['task-show','2580']) → os.execv(python, [python, pm-task-show.py, 2580])
    calls = []
    def fake_execv(path, argv):
        calls.append((path, argv))
        raise SystemExit(0)  # simule le remplacement de process
    mmi.os.execv = fake_execv
    try:
        mmi.main(["task-show", "2580"])
    except SystemExit:
        pass
    assert len(calls) == 1, calls
    path, argv = calls[0]
    assert path == sys.executable and argv[1] == str(HERE / "pm-task-show.py") and argv[2] == "2580", (path, argv)
    print("✓ routage os.execv → pm-task-show.py 2580 (args conservés)")

    # 5. sous-commande inconnue → SystemExit (message), aucun execv
    calls.clear()
    try:
        mmi.main(["pas-une-commande"])
        raise AssertionError("aurait dû SystemExit")
    except SystemExit as e:
        assert e.code and "inconnue" in str(e.code), e.code
    assert not calls
    print("✓ sous-commande inconnue → SystemExit, aucun exec")

    # 6. --help / vide → 0 ; --list → 0 sans exec
    assert mmi.main(["--help"]) == 0 and mmi.main([]) == 0
    assert mmi.main(["--list"]) == 0
    print("✓ --help / vide / --list : rc 0, pas d'exec")

    # 7. override PM_CORE_DIR : SCRIPTS suit l'env (recharge du module)
    os.environ["PM_CORE_DIR"] = "/tmp/nope"
    try:
        mmi2 = _load("mmi_pm_override")
        assert mmi2.SCRIPTS == Path("/tmp/nope/scripts"), mmi2.SCRIPTS
        print("✓ PM_CORE_DIR override : SCRIPTS = $PM_CORE_DIR/scripts")
    finally:
        os.environ.pop("PM_CORE_DIR", None)

    print("\nOK — tous les tests mmi-pm passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
