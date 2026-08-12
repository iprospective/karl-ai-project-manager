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
resolve_all = pm_registry.resolve_instances
secondaries = pm_registry.secondaries
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


# ── Primaire + secondaires (RM2653/L0, CDC RM2626 § 5.1) ───────────────────

def _meta_two_providers(policy="required"):
    return {"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary", "project_id": "pm-ai-agents"},
        {"instance": "redmine-matnat", "role": "secondary", "project_id": 12,
         "link": {"policy": policy},
         "sync": {"pull": {"notes": True}, "push": {"on": ["ferme"]}}},
    ]}}


def test_resolve_instances_list_primary_first():
    reg = Registry.from_config(_cfg())
    out = resolve_all(_meta_two_providers(), "task", reg)
    assert [r.instance.name for r in out] == ["redmine-ipro", "redmine-matnat"]
    assert out[0].is_primary and not out[1].is_primary
    assert out[0].params == {"project_id": "pm-ai-agents"}
    # les règles vivent sur le secondaire, hors des params projet
    assert out[1].params == {"project_id": 12}
    assert out[1].link == {"policy": "required"}
    assert out[1].sync["push"] == {"on": ["ferme"]}


def test_resolve_instance_returns_primary_of_a_list():
    """L'entrée historique ne voit QUE le primaire — non-régression des ~20 appelants."""
    reg = Registry.from_config(_cfg())
    res = resolve(_meta_two_providers(), "task", reg)
    assert res.instance.name == "redmine-ipro" and res.is_primary
    assert not res.link and not res.sync


def test_secondaries_helper():
    reg = Registry.from_config(_cfg())
    sec = secondaries(_meta_two_providers(), "task", reg)
    assert [r.instance.name for r in sec] == ["redmine-matnat"]
    # un projet mono-provider n'a aucun secondaire
    assert secondaries({"redmine": {"project_id": 1}}, "task", reg) == []
    assert secondaries({}, "forge", reg) == []


def test_list_order_preserved_for_secondaries():
    reg = Registry.from_config(_cfg())
    meta = {"providers": {"task": [
        {"instance": "redmine-matnat", "role": "secondary"},
        {"instance": "redmine-ipro", "role": "primary"},
    ]}}
    out = resolve_all(meta, "task", reg)
    # primaire remonté en tête même déclaré en second
    assert [r.instance.name for r in out] == ["redmine-ipro", "redmine-matnat"]


def test_single_entry_list_defaults_to_primary():
    reg = Registry.from_config(_cfg())
    meta = {"providers": {"task": [{"instance": "redmine-matnat", "project_id": 3}]}}
    out = resolve_all(meta, "task", reg)
    assert len(out) == 1 and out[0].is_primary and out[0].params == {"project_id": 3}


def test_dict_form_still_works():
    """Forme dict (P0) : inchangée, un seul primaire."""
    reg = Registry.from_config(_cfg())
    out = resolve_all({"providers": {"task": {"instance": "redmine-matnat"}}}, "task", reg)
    assert len(out) == 1 and out[0].is_primary and out[0].source == "providers"


def test_legacy_and_default_yield_single_primary():
    reg = Registry.from_config(_cfg())
    for meta, want, src in (
        ({"redmine": {"project_id": "x"}}, "redmine-ipro", "legacy"),
        ({}, "redmine-ipro", "default"),
    ):
        out = resolve_all(meta, "task", reg)
        assert len(out) == 1 and out[0].is_primary
        assert out[0].instance.name == want and out[0].source == src


def _expect_error(meta, axis, reg, why):
    try:
        resolve_all(meta, axis, reg)
        raise AssertionError(f"attendu RegistryError ({why})")
    except RegistryError:
        pass


def test_reject_two_primaries():
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary"},
        {"instance": "redmine-matnat", "role": "primary"},
    ]}}, "task", reg, "deux primaires")


def test_reject_no_primary():
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "secondary"},
        {"instance": "redmine-matnat", "role": "secondary"},
    ]}}, "task", reg, "aucun primaire")


def test_reject_sync_on_primary():
    """Le primaire est la source de vérité : il ne se synchronise avec personne."""
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary", "sync": {"pull": {"notes": True}}},
    ]}}, "task", reg, "sync sur le primaire")
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary", "link": {"policy": "required"}},
    ]}}, "task", reg, "link sur le primaire")


def test_reject_duplicate_instance():
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary"},
        {"instance": "redmine-ipro", "role": "secondary"},
    ]}}, "task", reg, "instance dupliquée")


def test_reject_unknown_role_and_missing_instance():
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "master"},
    ]}}, "task", reg, "role inconnu")
    _expect_error({"providers": {"task": [{"project_id": 4}]}}, "task", reg,
                  "instance manquante")


def test_reject_axis_mismatch_in_list():
    reg = Registry.from_config(_cfg())
    _expect_error({"providers": {"task": [
        {"instance": "redmine-ipro", "role": "primary"},
        {"instance": "gitlab-ipro", "role": "secondary"},   # forge posé en task
    ]}}, "task", reg, "axe incohérent sur un secondaire")


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
