#!/usr/bin/env python3
"""Tests offline de `redmine_utils.redmine_creds` — résolution multi-instance (RM2653/L0).

Lancer : python3 scripts/test_redmine_creds.py
Couvre : comportement mono-instance historique (inchangé), clé par instance
(`REDMINE__<INST>__API_KEY`), repli sur les clés globales quand l'instance déclarée
EST l'instance de travail, messages d'erreur bloquants. Aucun réseau.
"""
import contextlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils as ru
from pm_registry import Instance

_ENV_KEYS = ("REDMINE_URL", "REDMINE_API_KEY", "REDMINE_USER_MAIN_API_KEY",
             "REDMINE__REDMINE_MATNAT__API_KEY", "REDMINE__REDMINE_MATNAT__URL",
             "REDMINE__REDMINE_IPRO__API_KEY")


@contextlib.contextmanager
def env(**kv):
    """Env hermétique : toutes les clés Redmine connues sont remises à plat."""
    old = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in kv.items() if v is not None})
    try:
        yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def _exits(fn, why):
    try:
        fn()
        raise AssertionError(f"attendu SystemExit ({why})")
    except SystemExit:
        pass


def test_env_prefix_normalisation():
    assert ru.instance_env_prefix("redmine-matnat") == "REDMINE__REDMINE_MATNAT__"
    assert ru.instance_env_prefix("redmine.ipro 2") == "REDMINE__REDMINE_IPRO_2__"


def test_mono_instance_unchanged():
    with env(REDMINE_URL="https://tasks.example/", REDMINE_API_KEY="perso"):
        assert ru.redmine_creds() == ("https://tasks.example", "perso")


def test_mono_instance_falls_back_to_service_account():
    with env(REDMINE_URL="https://tasks.example", REDMINE_USER_MAIN_API_KEY="karl"):
        assert ru.redmine_creds() == ("https://tasks.example", "karl")


def test_mono_instance_missing_creds_exits():
    with env(REDMINE_URL="https://tasks.example"):
        _exits(ru.redmine_creds, "aucune clé")
    with env(REDMINE_API_KEY="perso"):
        _exits(ru.redmine_creds, "aucune URL")


def test_instance_uses_its_own_url_and_key():
    inst = Instance("redmine-matnat", "task", "redmine", "https://tasks.matnat")
    with env(REDMINE_URL="https://tasks.example", REDMINE_API_KEY="perso",
             REDMINE__REDMINE_MATNAT__API_KEY="k-matnat"):
        assert ru.redmine_creds(inst) == ("https://tasks.matnat", "k-matnat")


def test_instance_accepts_a_plain_name():
    """Un nom d'instance suffit — l'URL vient alors de l'env dédiée."""
    with env(REDMINE_URL="https://tasks.example", REDMINE_API_KEY="perso",
             REDMINE__REDMINE_MATNAT__URL="https://tasks.matnat",
             REDMINE__REDMINE_MATNAT__API_KEY="k-matnat"):
        assert ru.redmine_creds("redmine-matnat") == ("https://tasks.matnat", "k-matnat")


def test_declared_instance_of_working_redmine_reuses_global_key():
    """`redmine-ipro` pointe l'instance de travail : pas de clé dédiée à poser."""
    inst = Instance("redmine-ipro", "task", "redmine", "https://tasks.example")
    with env(REDMINE_URL="https://tasks.example", REDMINE_API_KEY="perso"):
        assert ru.redmine_creds(inst) == ("https://tasks.example", "perso")


def test_dedicated_key_wins_over_global():
    inst = Instance("redmine-ipro", "task", "redmine", "https://tasks.example")
    with env(REDMINE_URL="https://tasks.example", REDMINE_API_KEY="perso",
             REDMINE__REDMINE_IPRO__API_KEY="dediee"):
        assert ru.redmine_creds(inst) == ("https://tasks.example", "dediee")


def test_foreign_instance_without_key_exits():
    """Pas de repli silencieux sur la clé iProspective vers une instance tierce."""
    inst = Instance("redmine-matnat", "task", "redmine", "https://tasks.matnat")
    with env(REDMINE_URL="https://tasks.example", REDMINE_API_KEY="perso"):
        _exits(lambda: ru.redmine_creds(inst), "clé d'instance manquante")


def test_instance_without_any_url_exits():
    inst = Instance("redmine-ailleurs", "task", "redmine", "")
    with env(REDMINE_API_KEY="perso"):
        _exits(lambda: ru.redmine_creds(inst), "aucune URL résolue")


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
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
