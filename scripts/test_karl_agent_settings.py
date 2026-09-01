#!/usr/bin/env python3
"""Tests RM2386 — rubrique de config front + type `enum` de la whitelist (RM2213).

Unitaire (sans serveur ni réseau) : _pm_settings (lecture + repli sur le défaut),
op_pm_settings_set (validation enum, écriture ciblée dans pm.config.local.yml),
_ui_theme (valeur servie au front par /cockpit-config).
Lancer : python3 scripts/test_karl_agent_settings.py
"""
import importlib.util
import pathlib
import sys
import tempfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def setting(key):
    return next((e for e in ka._pm_settings() if e["key"] == key), None)


def write_conf(root, canonical, local=None):
    (root / "pm.config.yml").write_text(yaml.safe_dump(canonical), encoding="utf-8")
    lp = root / "pm.config.local.yml"
    if local is None:
        lp.unlink(missing_ok=True)      # sinon la surcharge d'un cas précédent fuite
    else:
        lp.write_text(yaml.safe_dump(local), encoding="utf-8")
    # pm.pricing.yml : _pm_settings le lit aussi (groupes Tarifs) — un fichier
    # minimal suffit, on ne teste pas cette branche ici.
    (root / "pm.pricing.yml").write_text("human_hourly_rate_eur: 60\nmodels: {}\n", encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    orig_root = ka.REPO_ROOT
    ka.REPO_ROOT = root
    try:
        # — la rubrique existe et est bien déclarée en enum —
        write_conf(root, {"ui": {"theme": "auto"}})
        s = setting("conf:ui.theme")
        check("la rubrique « Design front » expose conf:ui.theme",
              s is not None and s["group"] == "Design front")
        check("type enum + options dark/light/auto",
              s["type"] == "enum" and s["options"] == ["dark", "light", "auto"])
        check("valeur lue depuis pm.config.yml", s["value"] == "auto")

        # — surcharge locale prioritaire (merge _conf_merged) —
        write_conf(root, {"ui": {"theme": "auto"}}, local={"ui": {"theme": "light"}})
        check("pm.config.local.yml surcharge le canonique", setting("conf:ui.theme")["value"] == "light")

        # — robustesse : valeur aberrante éditée à la main → repli sur le défaut —
        write_conf(root, {"ui": {"theme": "solarized"}})
        check("valeur hors options → repli sur le défaut", setting("conf:ui.theme")["value"] == "auto")
        write_conf(root, {})
        check("section ui absente → repli sur le défaut", setting("conf:ui.theme")["value"] == "auto")

        # — _ui_theme : ce que /cockpit-config sert au front —
        write_conf(root, {"ui": {"theme": "dark"}})
        check("_ui_theme reflète la conf", ka._ui_theme() == "dark")

        # — écriture : valeur valide persistée dans pm.config.local.yml —
        write_conf(root, {"ui": {"theme": "auto"}})
        res = ka.op_pm_settings_set({"key": "conf:ui.theme", "value": "light", "confirm": True})
        local = yaml.safe_load((root / "pm.config.local.yml").read_text(encoding="utf-8"))
        check("écriture ciblée dans pm.config.local.yml", local == {"ui": {"theme": "light"}})
        check("réponse ok", res == {"key": "conf:ui.theme", "value": "light", "ok": True})
        check("relecture cohérente", setting("conf:ui.theme")["value"] == "light")

        # — écriture : le canonique n'est JAMAIS touché —
        canonical = yaml.safe_load((root / "pm.config.yml").read_text(encoding="utf-8"))
        check("pm.config.yml intact", canonical == {"ui": {"theme": "auto"}})

        # — validation : valeur hors options rejetée en 400 —
        def rejected(payload):
            try:
                ka.op_pm_settings_set(payload)
                return False
            except ka.ApiError as e:
                return e.code == 400
            except Exception:
                return False

        check("valeur hors options rejetée (400)",
              rejected({"key": "conf:ui.theme", "value": "solarized", "confirm": True}))
        check("confirmation obligatoire",
              rejected({"key": "conf:ui.theme", "value": "dark"}))
        check("clé hors whitelist rejetée",
              rejected({"key": "conf:ui.font_size", "value": "12", "confirm": True}))
        # la valeur rejetée ne doit pas avoir été écrite
        check("aucune écriture après rejet", setting("conf:ui.theme")["value"] == "light")

        # — non-régression : les types bool/number cohabitent avec enum —
        write_conf(root, {"git": {"autocommit": True}, "ui": {"theme": "auto"}})
        check("bool toujours lu correctement", setting("conf:git.autocommit")["value"] is True)
        ka.op_pm_settings_set({"key": "conf:git.autocommit", "value": False, "confirm": True})
        check("bool toujours écrit correctement", setting("conf:git.autocommit")["value"] is False)
    finally:
        ka.REPO_ROOT = orig_root

print(("ÉCHECS : " + ", ".join(fails)) if fails else "OK — tous les tests réglages passent")
sys.exit(1 if fails else 0)
