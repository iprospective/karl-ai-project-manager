#!/usr/bin/env python3
"""Tests RM2458 — santé du poste (page de statut de l'environnement).

Unitaire : les classifieurs purs (agrégat de niveaux, divergence git, PATH) et
les invariants qui garantissent que les DEUX incidents fondateurs (2026-07-30,
RM2455) sont attrapés : `bw` absent → erreur + commande d'install ; un repo en
divergence ahead/behind → erreur. On teste aussi que op_env_status rend une
structure exploitable (5 familles + résumé) et ne fuite aucun secret.

Lancer : python3 scripts/test_karl_agent_envstatus.py
"""
import importlib.util
import pathlib
import sys

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


# — git_divergence_level : le cœur de la détection d'incident —
lv, det = ka.git_divergence_level(9, 3, 0)
check("ahead+behind → error (divergence non-ff, l'incident pisceen)", lv == "error")
check("ahead+behind → détaille non poussés ET retard", "9" in det and "3" in det)
lv, det = ka.git_divergence_level(5, 0, 0)
check("ahead seul → warn (push différé)", lv == "warn" and "non poussé" in det)
lv, det = ka.git_divergence_level(0, 2, 0)
check("behind seul → warn", lv == "warn" and "retard" in det)
lv, det = ka.git_divergence_level(0, 0, 4)
check("dirty seul → warn", lv == "warn" and "modifié" in det)
lv, det = ka.git_divergence_level(0, 0, 0)
check("propre → ok", lv == "ok" and det == "à jour, propre")

# — path_local_bin_first —
home = "/home/karl"
lv, _ = ka.path_local_bin_first("/home/karl/.local/bin:/usr/bin", home)
check("~/.local/bin en tête → ok", lv == "ok")
lv, det = ka.path_local_bin_first("/usr/bin:/home/karl/.local/bin", home)
check("~/.local/bin après /usr/bin → warn", lv == "warn" and "après" in det)
lv, det = ka.path_local_bin_first("/usr/bin:/bin", home)
check("~/.local/bin absent → warn", lv == "warn" and "absent" in det)

# — envstatus_summary : agrégat + pire niveau —
groups = [
    {"name": "A", "checks": [{"level": "ok"}, {"level": "warn"}]},
    {"name": "B", "checks": [{"level": "error"}, {"level": "ok"}, {"level": "info"}]},
]
s = ka.envstatus_summary(groups)
check("summary compte par niveau", s["counts"] == {"ok": 2, "info": 1, "warn": 1, "error": 1})
check("summary worst = error", s["worst"] == "error")
check("summary sans error → worst=warn", ka.envstatus_summary(
    [{"name": "A", "checks": [{"level": "ok"}, {"level": "warn"}]}])["worst"] == "warn")
check("summary vide → worst=ok", ka.envstatus_summary([])["worst"] == "ok")
check("niveau inconnu compté en info", ka.envstatus_summary(
    [{"name": "A", "checks": [{"level": "zzz"}]}])["counts"]["info"] == 1)

# — incident #1 : bw doit être surveillé avec sa commande d'install exacte —
tools = dict(ka.ENV_TOOLS)
check("bw fait partie des outils surveillés", "bw" in tools)
check("bw : remédiation = npm i -g @bitwarden/cli", "@bitwarden/cli" in tools.get("bw", ""))

# — op_env_status : structure exploitable + aucun secret rendu —
report = ka.op_env_status()
names = [g["name"] for g in report["groups"]]
check("5 familles rendues", len(report["groups"]) == 5)
check("familles attendues présentes",
      {"Outils & dépendances", "Secrets", "Git / GitLab", "SSH", "PM"} <= set(names))
check("résumé présent (worst + counts)",
      "worst" in report["summary"] and "counts" in report["summary"])
# chaque check a la forme attendue, et un rouge/orange porte une remédiation quand utile
all_checks = [c for g in report["groups"] for c in g["checks"]]
check("chaque ligne a label + level", all(("label" in c and "level" in c) for c in all_checks))
# la famille Secrets ne rend jamais une valeur de secret (noms de variables seulement)
sec = next(g for g in report["groups"] if g["name"] == "Secrets")
blob = " ".join((c.get("detail", "") + c.get("fix", "")) for c in sec["checks"])
check("Secrets : aucune valeur de secret exposée (noms seulement)",
      "BW_CLIENTSECRET=" not in blob and "CLIENTSECRET:" not in blob)

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests envstatus passent")
