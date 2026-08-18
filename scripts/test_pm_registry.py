#!/usr/bin/env python3
"""Tests offline de pm_registry — registre + résolution d'instance (P0/RM2542).

Lancer : python3 scripts/test_pm_registry.py
Couvre : construction du registre (+ garde-fous de cohérence), priorité de
résolution (providers > legacy > client > default), rétro-compat des blocs
redmine:/gitlab:, interpolation ${VAR} des URLs, axes déclaratifs et cascade
client (RM2682/L1). Aucun réseau.
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


# ── Axe secret, axes déclaratifs, cascade client (RM2682/L1) ─────────────────
def _cfg_secret():
    """Config avec l'axe `secret` : deux vaults déclarés, un défaut."""
    cfg = _cfg()
    cfg["defaults"]["secret"] = "vw-ipro"
    cfg["servers"]["vw-ipro"] = {"axis": "secret", "type": "vaultwarden",
                                 "url": "https://vault.example"}
    cfg["servers"]["kdbx-perso"] = {"axis": "secret", "type": "keepass",
                                    "file": "~/vaults/ipro.kdbx"}
    cfg["servers"]["vw-clientx"] = {"axis": "secret", "type": "vaultwarden",
                                    "url": "https://vault.client-x.tld"}
    return cfg


def test_axe_secret_declarable():
    reg = Registry.from_config(_cfg_secret())
    assert "secret" in reg.axes
    assert reg.default_for("secret").type == "vaultwarden"
    assert {i.name for i in reg.by_axis("secret")} == {"vw-ipro", "kdbx-perso", "vw-clientx"}
    assert reg.get("kdbx-perso").options.get("file") == "~/vaults/ipro.kdbx"


def test_axes_declaratifs_extension():
    """Un axe nouveau (monitoring) s'active en conf, sans toucher au code."""
    cfg = _cfg_secret()
    cfg["axes"] = ["monitoring"]
    cfg["servers"]["zabbix-ipro"] = {"axis": "monitoring", "type": "zabbix",
                                     "url": "https://zabbix.example"}
    cfg["defaults"]["monitoring"] = "zabbix-ipro"
    reg = Registry.from_config(cfg)
    assert "monitoring" in reg.axes
    assert reg.default_for("monitoring").type == "zabbix"
    # …et il est résoluble comme les autres.
    res = resolve({}, "monitoring", reg)
    assert res.instance.name == "zabbix-ipro" and res.source == "default", res


def test_axes_livres_toujours_valides():
    """Déclarer `axes:` n'ampute jamais les axes livrés (casserait des appelants)."""
    cfg = _cfg_secret()
    cfg["axes"] = ["monitoring"]          # ne mentionne aucun axe livré
    reg = Registry.from_config(cfg)
    for axe in ("task", "forge", "doc", "secret"):
        assert axe in reg.axes, axe


def test_axe_non_declare_refuse():
    cfg = _cfg_secret()
    cfg["servers"]["zabbix-ipro"] = {"axis": "monitoring", "type": "zabbix"}
    try:
        Registry.from_config(cfg)          # `monitoring` absent de providers.axes
    except RegistryError as e:
        assert "monitoring" in str(e) and "providers.axes" in str(e), e
    else:
        raise AssertionError("un axe non déclaré doit être refusé")


def test_cascade_client_applique():
    """Le client impose son vault à tous ses projets qui ne surchargent pas."""
    reg = Registry.from_config(_cfg_secret())
    client = {"providers": {"secret": {"instance": "vw-clientx"}}}
    res = resolve({}, "secret", reg, client_meta=client)
    assert res.instance.name == "vw-clientx" and res.source == "client", res


def test_cascade_projet_gagne_sur_client():
    reg = Registry.from_config(_cfg_secret())
    client = {"providers": {"secret": {"instance": "vw-clientx"}}}
    projet = {"providers": {"secret": {"instance": "kdbx-perso"}}}
    res = resolve(projet, "secret", reg, client_meta=client)
    assert res.instance.name == "kdbx-perso" and res.source == "providers", res


def test_cascade_client_ignoree_si_projet_legacy():
    """Documenté : sur task/forge, le bloc legacy du projet reste plus spécifique."""
    reg = Registry.from_config(_cfg_secret())
    client = {"providers": {"task": {"instance": "redmine-matnat"}}}
    projet = {"redmine": {"project_id": "p"}}          # legacy → instance par défaut
    res = resolve(projet, "task", reg, client_meta=client)
    assert res.instance.name == "redmine-ipro" and res.source == "legacy", res


def test_cascade_defaut_si_rien():
    reg = Registry.from_config(_cfg_secret())
    res = resolve({}, "secret", reg, client_meta={})
    assert res.instance.name == "vw-ipro" and res.source == "default", res


def test_client_meta_omis_iso_comportement():
    """Sans `client_meta`, la résolution est exactement celle d'avant L1."""
    reg = Registry.from_config(_cfg_secret())
    for axe, meta in (("task", {"redmine": {"project_id": "p"}}),
                      ("forge", {"gitlab": {"repo": "g/r"}}),
                      ("doc", {}),
                      ("secret", {})):
        avec = resolve(meta, axe, reg, client_meta=None)
        sans = resolve(meta, axe, reg)
        assert avec == sans, (axe, avec, sans)


def test_cascade_client_axe_incoherent():
    """Une instance d'un autre axe côté client doit lever, pas être retenue."""
    reg = Registry.from_config(_cfg_secret())
    client = {"providers": {"secret": {"instance": "gitlab-ipro"}}}
    try:
        resolve({}, "secret", reg, client_meta=client)
    except RegistryError as e:
        assert "gitlab-ipro" in str(e), e
    else:
        raise AssertionError("instance d'axe incohérent côté client doit lever")


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
