#!/usr/bin/env python3
"""Tests de la scission des secrets à 3 niveaux (RM2438 T1).

Lancer : python3 scripts/test_pm_paths_secrets.py

Prouve l'ordre de résolution `os.environ` > `~/.config/mmi-pm/.env` (par dev) >
`.env` d'instance (fallback karl), et la RÉTROCOMPAT : sans user env, seul
l'instance est chargé (comportement karl inchangé).
"""
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import pm_paths  # noqa: E402
from pm_paths import _user_secrets_env, _load_env_file  # noqa: E402


def _clean(*keys):
    for k in keys:
        os.environ.pop(k, None)


def test_user_locator(tmp):
    """`_user_secrets_env` suit XDG_CONFIG_HOME et exige l'existence du fichier."""
    xdg = tmp / "xdg"
    os.environ["XDG_CONFIG_HOME"] = str(xdg)
    try:
        assert _user_secrets_env() is None, "absent → None (rétrocompat)"
        f = xdg / "mmi-pm" / ".env"
        f.parent.mkdir(parents=True)
        f.write_text("X=1\n")
        assert _user_secrets_env() == f, "présent → chemin résolu sous XDG_CONFIG_HOME"
    finally:
        _clean("XDG_CONFIG_HOME", "X")
    print("✓ _user_secrets_env : suit XDG_CONFIG_HOME, None si absent")


def test_priority_order(tmp):
    """user > instance ; os.environ > tout. Simule l'ordre de chargement de load()."""
    inst = tmp / "instance.env"
    inst.write_text("SHARED=instance\nONLY_INST=inst\n")
    user = tmp / "user.env"
    user.write_text("SHARED=user\nONLY_USER=usr\n")

    # (a) os.environ posé AVANT tout chargement → gagne sur user ET instance
    _clean("SHARED", "ONLY_INST", "ONLY_USER")
    os.environ["SHARED"] = "session"
    _load_env_file(user)      # user d'abord (prioritaire sur instance)
    _load_env_file(inst)      # instance en fallback
    assert os.environ["SHARED"] == "session", "os.environ > user > instance"
    assert os.environ["ONLY_USER"] == "usr", "clé user chargée"
    assert os.environ["ONLY_INST"] == "inst", "clé instance en fallback"
    _clean("SHARED", "ONLY_INST", "ONLY_USER")

    # (b) sans override de session : user gagne sur instance (premier-écrit-gagne)
    _load_env_file(user)
    _load_env_file(inst)
    assert os.environ["SHARED"] == "user", "user > instance"
    _clean("SHARED", "ONLY_INST", "ONLY_USER")
    print("✓ résolution : os.environ > user (~/.config) > instance (fallback karl)")


def test_retrocompat(tmp):
    """Sans user env, seul l'instance alimente l'environnement (karl inchangé)."""
    xdg = tmp / "noxdg"  # répertoire sans mmi-pm/.env
    os.environ["XDG_CONFIG_HOME"] = str(xdg)
    inst = tmp / "instance2.env"
    inst.write_text("KARL_ONLY=karl\n")
    try:
        _clean("KARL_ONLY")
        assert _user_secrets_env() is None
        _load_env_file(inst)
        assert os.environ["KARL_ONLY"] == "karl", "fallback instance seul"
    finally:
        _clean("XDG_CONFIG_HOME", "KARL_ONLY")
    print("✓ rétrocompat : aucun user env → instance seul (comportement karl inchangé)")


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_user_locator(tmp)
        test_priority_order(tmp)
        test_retrocompat(tmp)
    print("\nOK — scission secrets 3 niveaux validée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
