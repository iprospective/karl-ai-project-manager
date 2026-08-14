#!/usr/bin/env python3
"""Tests RM2690 — plafond mémoire des scopes tmux de session.

Unitaire (sans serveur, sans tmux, sans systemd) : parsing des limites,
précédence env > conf > défaut, exposition/écriture du réglage cockpit
(whitelist RM2213), et non-blocage de _apply_memory_limits quand la scope
est introuvable.
Lancer : python3 scripts/test_karl_agent_memlimit.py
"""
import importlib.util
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stderr

import yaml

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []
GIB = 1024 ** 3


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def setting(key):
    return next((e for e in ka._pm_settings() if e["key"] == key), None)


def write_conf(root, sessions=None, local=None):
    conf = {"ui": {"theme": "auto"}}
    if sessions is not None:
        conf["sessions"] = sessions
    (root / "pm.config.yml").write_text(yaml.safe_dump(conf), encoding="utf-8")
    lp = root / "pm.config.local.yml"
    if local is None:
        lp.unlink(missing_ok=True)
    else:
        lp.write_text(yaml.safe_dump(local), encoding="utf-8")
    (root / "pm.pricing.yml").write_text("human_hourly_rate_eur: 60\nmodels: {}\n",
                                         encoding="utf-8")


def unset_env():
    for v in ka.MEM_LIMIT_ENV.values():
        os.environ.pop(v, None)


# — parsing (indépendant de la conf) —
check("GiB numériques (conf/cockpit)", ka._mem_bytes(6) == 6 * GIB)
check("fraction de GiB", ka._mem_bytes(0.5) == GIB // 2)
check("suffixe systemd G", ka._mem_bytes("6G") == 6 * GIB)
check("suffixe systemd M", ka._mem_bytes("6144M") == 6 * GIB)
check("suffixe GiB toléré", ka._mem_bytes("8GiB") == 8 * GIB)
check("octets nus", ka._mem_bytes("8589934592") == 8 * GIB)
check("0 = pas de limite", ka._mem_bytes(0) is None)
check("chaîne vide = pas de limite", ka._mem_bytes("") is None)
check("none = pas de limite", ka._mem_bytes("none") is None)
check("infinity = pas de limite", ka._mem_bytes("infinity") is None)
check("valeur illisible = pas de limite", ka._mem_bytes("beaucoup") is None)
check("booléen ignoré (piège YAML)", ka._mem_bytes(True) is None)

with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    orig_root = ka.REPO_ROOT
    ka.REPO_ROOT = root
    unset_env()
    try:
        # — précédence : conf > défaut —
        write_conf(root, {"memory_high_gib": 6, "memory_max_gib": 8})
        check("conf lue pour high", ka._mem_limit("high") == 6 * GIB)
        check("conf lue pour max", ka._mem_limit("max") == 8 * GIB)

        write_conf(root, {"memory_high_gib": 6, "memory_max_gib": 8},
                   local={"sessions": {"memory_max_gib": 12}})
        check("pm.config.local.yml surcharge le canonique",
              ka._mem_limit("max") == 12 * GIB)

        write_conf(root, None)
        check("clé absente → défaut du module",
              ka._mem_limit("high") == int(ka.MEM_LIMIT_DEFAULTS["high"] * GIB))

        write_conf(root, {"memory_high_gib": 0, "memory_max_gib": 0})
        check("0 en conf → fonctionnalité désactivée",
              ka._mem_limit("high") is None and ka._mem_limit("max") is None)

        # — précédence : env > conf —
        write_conf(root, {"memory_high_gib": 6, "memory_max_gib": 8})
        os.environ[ka.MEM_LIMIT_ENV["max"]] = "4G"
        check("variable d'env prioritaire sur la conf", ka._mem_limit("max") == 4 * GIB)
        os.environ[ka.MEM_LIMIT_ENV["max"]] = ""
        check("variable d'env vide → désactivé malgré la conf",
              ka._mem_limit("max") is None)
        unset_env()

        # — exposition cockpit (whitelist RM2213) —
        write_conf(root, {"memory_high_gib": 6, "memory_max_gib": 8})
        s = setting("conf:sessions.memory_high_gib")
        check("la rubrique « Sessions » expose le seuil de pression",
              s is not None and s["group"] == "Sessions" and s["type"] == "number")
        check("valeur servie en GiB", s["value"] == 6.0)
        check("non figé sans variable d'env", "pinned" not in s)
        check("plafond dur exposé aussi",
              setting("conf:sessions.memory_max_gib")["value"] == 8.0)

        os.environ[ka.MEM_LIMIT_ENV["high"]] = "10G"
        s = setting("conf:sessions.memory_high_gib")
        check("valeur servie = limite effective (env)", s["value"] == 10.0)
        check("marqué figé par la variable d'env",
              s.get("pinned") == ka.MEM_LIMIT_ENV["high"])

        def rejected(payload):
            try:
                ka.op_pm_settings_set(payload)
                return False
            except ka.ApiError as e:
                return e.code == 400
            except Exception:
                return False

        check("écriture refusée tant que le .env fige la valeur",
              rejected({"key": "conf:sessions.memory_high_gib", "value": 4, "confirm": True}))
        unset_env()

        # — écriture depuis le cockpit —
        res = ka.op_pm_settings_set({"key": "conf:sessions.memory_max_gib",
                                     "value": 10, "confirm": True})
        local = yaml.safe_load((root / "pm.config.local.yml").read_text(encoding="utf-8"))
        check("écriture ciblée dans pm.config.local.yml",
              local == {"sessions": {"memory_max_gib": 10.0}})
        check("réponse ok", res["ok"] is True and res["value"] == 10.0)
        check("relecture cohérente", ka._mem_limit("max") == 10 * GIB)
        check("le canonique n'est jamais réécrit",
              yaml.safe_load((root / "pm.config.yml").read_text(encoding="utf-8"))
              ["sessions"]["memory_max_gib"] == 8)
        check("0 accepté (désactivation depuis le cockpit)",
              ka.op_pm_settings_set({"key": "conf:sessions.memory_max_gib",
                                     "value": 0, "confirm": True})["value"] == 0.0)
        check("valeur hors bornes rejetée",
              rejected({"key": "conf:sessions.memory_high_gib", "value": 9999, "confirm": True}))
        check("confirmation obligatoire",
              rejected({"key": "conf:sessions.memory_high_gib", "value": 4}))

        # — non-blocage : session inexistante → warning, jamais d'exception —
        write_conf(root, {"memory_high_gib": 6, "memory_max_gib": 8})
        err = io.StringIO()
        with redirect_stderr(err):
            got = ka._apply_memory_limits("karl-RM-inexistante-" + "x" * 8)
        check("scope introuvable → None (session créée quand même)", got is None)
        check("scope introuvable → warning loggué", "plafond mémoire" in err.getvalue())

        # — désactivé : aucun appel systemd, aucun warning —
        write_conf(root, {"memory_high_gib": 0, "memory_max_gib": 0})
        err = io.StringIO()
        with redirect_stderr(err):
            got = ka._apply_memory_limits("karl-RM-inexistante")
        check("désactivé → pas de tentative ni de bruit",
              got is None and err.getvalue() == "")
    finally:
        ka.REPO_ROOT = orig_root
        unset_env()

print(("ÉCHECS : " + ", ".join(fails)) if fails
      else "OK — tous les tests plafond mémoire passent")
sys.exit(1 if fails else 0)
