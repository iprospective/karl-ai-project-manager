#!/usr/bin/env python3
"""Tests RM2376 — watchdog auth SSH GitLab de karl (« peut-il pousser ? »).

Unitaire : le classement pur de l'état (`gitlab_push_check_line`, qui pilote la
couleur/la remédiation au cockpit) et la résolution du chemin d'état du script de
check. Le check SSH réel (run_check) fait de l'I/O réseau — non testé ici.

Lancer : python3 scripts/test_karl_agent_gitlab_watchdog.py
"""
import importlib.util
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ka = _load("karl_agent", "karl-agent.py")
chk = _load("pm_gitlab_push_check", "pm-gitlab-push-check.py")

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


L = ka.gitlab_push_check_line

# — état absent → warn, pointe vers le script —
lvl, det, fix = L(None, None)
check("état absent → warn", lvl == "warn")
check("état absent → propose de lancer le check", "pm-gitlab-push-check" in fix)

# — OK récent → vert, sans remédiation —
lvl, det, fix = L({"ok": True, "detail": "auth OK (@karl-dev)"}, 120)
check("OK récent → ok", lvl == "ok" and fix == "")
check("OK récent → âge affiché", "min" in det)

# — OK mais périmé (> 1 h) → warn + relance —
lvl, det, fix = L({"ok": True, "detail": "auth OK"}, 4000)
check("OK périmé → warn", lvl == "warn")
check("OK périmé → mention (périmé)", "périmé" in det)
check("OK périmé → propose de relancer", "pm-gitlab-push-check" in fix)

# — KO → rouge + remédiation portée par l'état —
lvl, det, fix = L({"ok": False, "detail": "Permission denied (publickey)",
                   "remediation": "regénérer la clé (RM2158)"}, 60)
check("KO → error", lvl == "error")
check("KO → détail conservé", "Permission denied" in det)
check("KO → remédiation de l'état utilisée", "RM2158" in fix)

# — KO sans remédiation → repli RM2158 —
lvl, det, fix = L({"ok": False, "detail": "timeout"}, None)
check("KO sans remédiation → repli RM2158", "RM2158" in fix)

# — âge None sur un OK → pas de « il y a … » trompeur —
lvl, det, fix = L({"ok": True, "detail": "auth OK"}, None)
check("OK sans âge → pas de mention d'âge", "il y a" not in det and lvl == "ok")

# — state_path : override explicite prioritaire —
prev = dict(os.environ)
try:
    os.environ["KARL_GITLAB_CHECK_STATE"] = "/tmp/x/gitlab-push.json"
    check("state_path : override respecté", str(chk.state_path()) == "/tmp/x/gitlab-push.json")
    del os.environ["KARL_GITLAB_CHECK_STATE"]
    os.environ["KARL_AGENT_STATE_DIR"] = "/tmp/sd"
    check("state_path : dérivé de STATE_DIR", str(chk.state_path()) == "/tmp/sd/gitlab-push.json")
finally:
    os.environ.clear()
    os.environ.update(prev)

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests gitlab-watchdog passent")
