#!/usr/bin/env python3
"""Tests de l'identité PAR UTILISATEUR — T1/RM2497 (chantier convergence RM2438).

Lancer : python3 scripts/test_multiuser_identity.py

Vérifie :
- `redmine_utils.redmine_creds()` préfère la clé perso (`REDMINE_API_KEY`) et
  retombe sur karl (`REDMINE_USER_MAIN_API_KEY`) sinon ; sys.exit si aucune.
- `pm_paths._user_env()` résout l'override `PM_USER_ENV`.
- `pm_paths._load_env_file()` n'écrase pas l'existant → l'ordre user-avant-instance
  donne bien la priorité au `.env` utilisateur (et la session prime sur tout).
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, str(_HERE / f"{mod}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


pm_paths = _load("pm_paths")
redmine_utils = _load("redmine_utils")

_KEYS = ("REDMINE_URL", "REDMINE_API_KEY", "REDMINE_USER_MAIN_API_KEY",
         "PM_USER_ENV", "XDG_CONFIG_HOME")


def _clean_env():
    for k in _KEYS:
        os.environ.pop(k, None)


def test_creds_prefer_user_key():
    _clean_env()
    os.environ["REDMINE_URL"] = "https://r.example/"
    os.environ["REDMINE_USER_MAIN_API_KEY"] = "KARL"
    os.environ["REDMINE_API_KEY"] = "ALICE"
    url, key = redmine_utils.redmine_creds()
    assert url == "https://r.example" and key == "ALICE", (url, key)


def test_creds_fallback_karl():
    _clean_env()
    os.environ["REDMINE_URL"] = "https://r.example"
    os.environ["REDMINE_USER_MAIN_API_KEY"] = "KARL"
    _, key = redmine_utils.redmine_creds()
    assert key == "KARL", key


def test_creds_missing_exits():
    _clean_env()
    os.environ["REDMINE_URL"] = "https://r.example"  # pas de clé
    try:
        redmine_utils.redmine_creds()
        raise AssertionError("attendu SystemExit")
    except SystemExit:
        pass


def test_user_env_override():
    _clean_env()
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "perso.env"
        f.write_text("REDMINE_API_KEY=X\n", encoding="utf-8")
        os.environ["PM_USER_ENV"] = str(f)
        assert pm_paths._user_env() == f, pm_paths._user_env()
    # override pointant un fichier absent → None
    os.environ["PM_USER_ENV"] = str(Path(d) / "absent.env")
    assert pm_paths._user_env() is None


def test_load_order_user_wins_over_instance():
    _clean_env()
    with tempfile.TemporaryDirectory() as d:
        user = Path(d) / "user.env"
        inst = Path(d) / "instance.env"
        user.write_text("REDMINE_API_KEY=USERVAL\n", encoding="utf-8")
        inst.write_text("REDMINE_API_KEY=INSTVAL\n", encoding="utf-8")
        # ordre réel de load() : user d'abord, instance ensuite
        pm_paths._load_env_file(user)
        pm_paths._load_env_file(inst)
        assert os.environ["REDMINE_API_KEY"] == "USERVAL", os.environ["REDMINE_API_KEY"]


def test_session_wins_over_files():
    _clean_env()
    os.environ["REDMINE_API_KEY"] = "SESSION"
    with tempfile.TemporaryDirectory() as d:
        user = Path(d) / "user.env"
        user.write_text("REDMINE_API_KEY=USERVAL\n", encoding="utf-8")
        pm_paths._load_env_file(user)
        assert os.environ["REDMINE_API_KEY"] == "SESSION", os.environ["REDMINE_API_KEY"]


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    fails = 0
    for fn in CASES:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  ✗ {fn.__name__} — ERREUR {type(e).__name__}: {e}")
    _clean_env()
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
