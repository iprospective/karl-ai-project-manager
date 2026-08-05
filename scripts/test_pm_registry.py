#!/usr/bin/env python3
"""Tests offline de pm_registry — registre + résolution d'instance (P0/RM2542).

Lancer : python3 scripts/test_pm_registry.py
Couvre : construction du registre (+ garde-fous de cohérence), priorité de
résolution (providers > legacy > default) pour les 3 axes, rétro-compat des
blocs redmine:/gitlab:, interpolation ${VAR} des URLs. Aucun réseau.
"""
import importlib.util
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_registry", str(_HERE / "pm_registry.py"))
pm_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_registry)

Registry = pm_registry.Registry
resolve = pm_registry.resolve_instance
RegistryError = pm_registry.RegistryError


def _cfg():
    """Config `providers:` représentative, hermétique (indépendante du réel)."""
    return {
        "defaults": {"task": "redmine-ipro", "forge": "gitlab-ipro", "doc": "redmine-wiki"},
        "servers": {
            "gitlab-ipro":    {"axis": "forge", "type": "gitlab", "url": "https://gl.example/"},
            "gogs-matnat":    {"axis": "forge", "type": "gogs", "url": "https://gogs.example", "ssh_port": 28022},
            "redmine-ipro":   {"axis": "task", "type": "redmine", "url": "${REDMINE_URL:-https://tasks.example}"},
            "redmine-matnat": {"axis": "task", "type": "redmine", "url": "https://tasks.matnat"},
            "redmine-wiki":   {"axis": "doc", "type": "redmine_wiki", "url": "https://tasks.example"},
        },
    }


def test_from_config_basic():
    reg = Registry.from_config(_cfg())
    assert reg.default_for("task").name == "redmine-ipro"
    assert reg.default_for("forge").type == "gitlab"
    assert reg.get("gogs-matnat").options.get("ssh_port") == 28022
    assert {i.name for i in reg.by_axis("task")} == {"redmine-ipro", "redmine-matnat"}


def test_url_env_expansion():
    os.environ["REDMINE_URL"] = "https://tasks.iprospective.fr"
    reg = Registry.from_config(_cfg())
    # ${REDMINE_URL} interpolé + trailing slash retiré
    assert reg.get("redmine-ipro").url == "https://tasks.iprospective.fr"
    assert reg.get("gitlab-ipro").url == "https://gl.example"  # slash final retiré


def test_from_config_bad_default():
    cfg = _cfg()
    cfg["defaults"]["task"] = "nexiste-pas"
    try:
        Registry.from_config(cfg)
        raise AssertionError("attendu RegistryError (défaut absent)")
    except RegistryError:
        pass


def test_from_config_axis_mismatch_default():
    cfg = _cfg()
    cfg["defaults"]["task"] = "gitlab-ipro"  # instance forge posée en défaut task
    try:
        Registry.from_config(cfg)
        raise AssertionError("attendu RegistryError (axe incohérent)")
    except RegistryError:
        pass


def test_from_config_unknown_axis():
    cfg = _cfg()
    cfg["servers"]["weird"] = {"axis": "chat", "type": "x"}
    try:
        Registry.from_config(cfg)
        raise AssertionError("attendu RegistryError (axis inconnu)")
    except RegistryError:
        pass


def test_resolve_providers_block():
    reg = Registry.from_config(_cfg())
    meta = {"providers": {"task": {"instance": "redmine-matnat", "project_id": 42}}}
    res = resolve(meta, "task", reg)
    assert res.instance.name == "redmine-matnat" and res.source == "providers"
    assert res.params == {"project_id": 42}


def test_resolve_legacy_redmine_default_instance():
    reg = Registry.from_config(_cfg())
    # bloc historique : instance null → défaut task, project_id conservé
    meta = {"redmine": {"instance": None, "project_id": "pm-ai-agents", "subprojects": []}}
    res = resolve(meta, "task", reg)
    assert res.instance.name == "redmine-ipro" and res.source == "legacy"
    assert res.params == {"project_id": "pm-ai-agents"}


def test_resolve_legacy_redmine_named_instance():
    reg = Registry.from_config(_cfg())
    meta = {"redmine": {"instance": "redmine-matnat", "project_id": 7}}
    res = resolve(meta, "task", reg)
    assert res.instance.name == "redmine-matnat" and res.source == "legacy"
    assert res.params == {"project_id": 7}


def test_resolve_legacy_gitlab():
    reg = Registry.from_config(_cfg())
    meta = {"gitlab": {"repo": "grp/repo", "group": "grp", "default_branch": "main"}}
    res = resolve(meta, "forge", reg)
    assert res.instance.name == "gitlab-ipro" and res.source == "legacy"
    assert res.params == {"repo": "grp/repo", "group": "grp", "default_branch": "main"}


def test_resolve_default_when_empty():
    reg = Registry.from_config(_cfg())
    for axis, want in (("task", "redmine-ipro"), ("forge", "gitlab-ipro"), ("doc", "redmine-wiki")):
        res = resolve({}, axis, reg)
        assert res.instance.name == want and res.source == "default", (axis, res)


def test_resolve_doc_ignores_legacy_blocks():
    # un projet avec redmine:/gitlab: mais rien pour doc → défaut doc
    reg = Registry.from_config(_cfg())
    meta = {"redmine": {"project_id": 1}, "gitlab": {"repo": "a/b"}}
    res = resolve(meta, "doc", reg)
    assert res.instance.name == "redmine-wiki" and res.source == "default"


def test_resolve_unknown_axis():
    reg = Registry.from_config(_cfg())
    try:
        resolve({}, "chat", reg)
        raise AssertionError("attendu RegistryError")
    except RegistryError:
        pass


def test_resolve_providers_axis_mismatch():
    reg = Registry.from_config(_cfg())
    meta = {"providers": {"task": {"instance": "gitlab-ipro"}}}  # forge posé en task
    try:
        resolve(meta, "task", reg)
        raise AssertionError("attendu RegistryError (axe incohérent)")
    except RegistryError:
        pass


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
