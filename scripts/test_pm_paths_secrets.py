#!/usr/bin/env python3
"""Tests de la scission des secrets (RM2438 T1) : 3ᵉ niveau `pm.env` + tolérance perm.

Lancer : python3 scripts/test_pm_paths_secrets.py

Le split user/instance à 2 niveaux (`_user_env`) date de RM2497. Ce module couvre
l'AJOUT RM2438 T1 : le fichier d'instance NON-secret `pm.env` (`_instance_env`) chargé
ENTRE le user et le `.env` secret, et la tolérance `PermissionError` (dev non-admin ne
peut pas lire le `.env` secret). Ordre final :
    os.environ (session) > user (~/.config) > pm.env (instance) > .env (fallback karl).
"""
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from pm_paths import _user_env, _instance_env, _load_env_file  # noqa: E402


def _clean(*keys):
    for k in keys:
        os.environ.pop(k, None)


def test_instance_locator(tmp):
    """`_instance_env` = `pm.env` dans pm_dir, sinon via PM_CORE_DIR ; None si absent."""
    d = tmp / "core"
    d.mkdir()
    assert _instance_env(d) is None, "absent → None (rétrocompat monolithique)"
    (d / "pm.env").write_text("REDMINE_URL=x\n")
    assert _instance_env(d) == d / "pm.env", "présent → pm.env de pm_dir"
    _clean("REDMINE_URL")
    print("✓ _instance_env : pm.env (non-secret) à côté de pm.config.yml")


def test_user_still_primes(tmp):
    """`_user_env` (RM2497) suit XDG_CONFIG_HOME et reste prioritaire."""
    xdg = tmp / "xdg"
    os.environ["XDG_CONFIG_HOME"] = str(xdg)
    os.environ.pop("PM_USER_ENV", None)
    try:
        assert _user_env() is None
        f = xdg / "mmi-pm" / ".env"
        f.parent.mkdir(parents=True)
        f.write_text("X=1\n")
        assert _user_env() == f
    finally:
        _clean("XDG_CONFIG_HOME", "X")
    print("✓ _user_env (RM2497) intact : ~/.config/mmi-pm/.env")


def test_priority_order(tmp):
    """os.environ > user > pm.env(instance) > .env(secret). Simule l'ordre de load()."""
    secret = tmp / "secret.env"
    secret.write_text("SHARED=secret\nONLY_SECRET=s\n")
    inst = tmp / "pm.env"
    inst.write_text("SHARED=instance\nONLY_INST=i\n")
    user = tmp / "user.env"
    user.write_text("SHARED=user\nONLY_USER=u\n")

    _clean("SHARED", "ONLY_SECRET", "ONLY_INST", "ONLY_USER")
    os.environ["SHARED"] = "session"
    _load_env_file(user)      # user (prime)
    _load_env_file(inst)      # instance (pm.env)
    _load_env_file(secret)    # secret (fallback)
    assert os.environ["SHARED"] == "session", "os.environ bat tout"
    assert os.environ["ONLY_USER"] == "u"
    assert os.environ["ONLY_INST"] == "i"
    assert os.environ["ONLY_SECRET"] == "s"
    _clean("SHARED", "ONLY_SECRET", "ONLY_INST", "ONLY_USER")

    _load_env_file(user); _load_env_file(inst); _load_env_file(secret)
    assert os.environ["SHARED"] == "user", "user > instance > secret"
    _clean("SHARED", "ONLY_SECRET", "ONLY_INST", "ONLY_USER")

    _load_env_file(inst); _load_env_file(secret)
    assert os.environ["SHARED"] == "instance", "instance (pm.env) > secret (.env)"
    _clean("SHARED", "ONLY_SECRET", "ONLY_INST", "ONLY_USER")
    print("✓ résolution : os.environ > user > pm.env (instance) > .env (karl)")


def test_permission_tolerance(tmp):
    """Un `.env` secret illisible est ignoré sans lever (dev non-admin)."""
    secret = tmp / "unreadable.env"
    secret.write_text("KARL_SECRET=zzz\n")
    os.chmod(secret, 0o000)
    try:
        _clean("KARL_SECRET")
        _load_env_file(secret)  # ne doit PAS lever
        if not os.access(secret, os.R_OK):
            assert "KARL_SECRET" not in os.environ, "secret illisible → non chargé"
            print("✓ tolérance PermissionError : secret admin-only illisible → ignoré")
        else:
            print("~ tolérance PermissionError : root contourne la perm — no-raise validé")
    finally:
        os.chmod(secret, 0o644)
        _clean("KARL_SECRET")


def test_retrocompat(tmp):
    """Sans pm.env ni user, seul le `.env` monolithique alimente l'env (karl inchangé)."""
    inst = tmp / "core2"
    inst.mkdir()
    assert _instance_env(inst) is None, "pas de pm.env → None"
    mono = tmp / "mono.env"
    mono.write_text("KARL_ONLY=karl\n")
    _clean("KARL_ONLY")
    _load_env_file(mono)
    assert os.environ["KARL_ONLY"] == "karl"
    _clean("KARL_ONLY")
    print("✓ rétrocompat : sans pm.env, .env monolithique seul (karl inchangé)")


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_instance_locator(tmp)
        test_user_still_primes(tmp)
        test_priority_order(tmp)
        test_permission_tolerance(tmp)
        test_retrocompat(tmp)
    print("\nOK — scission secrets 3 niveaux (pm.env + tolérance perm) validée")
    return 0


if __name__ == "__main__":
    sys.exit(main())
