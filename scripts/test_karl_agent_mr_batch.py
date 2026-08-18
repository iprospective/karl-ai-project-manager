#!/usr/bin/env python3
"""Tests RM2720 (suite) — merger un LOT de MR depuis le worklog.

Ce qu'on protège :
  - « dev » et « prod » ne sont PAS le même geste : dev merge la branche de
    CHAQUE ticket dans l'intégration ; prod promeut l'INTÉGRATION vers la
    production, une fois par dépôt (dix tickets du même repo = une MR, pas dix) ;
  - un ticket non résolu (jamais démarré, multi-repo, inconnu) est écarté AVEC
    sa raison, et n'emporte pas le lot ;
  - une session encore vivante est SIGNALÉE (merger sous les pieds d'un agent au
    travail doit se voir avant le clic, pas après) ;
  - rien ne part sans confirmation explicite, et `dry_run` ne merge rien ;
  - le merge passe par pm-mr.py — l'argv est construit ici, jamais un shell.

Lancer : python3 scripts/test_karl_agent_mr_batch.py
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


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def raises(code, fn):
    try:
        fn()
        return False
    except ka.ApiError as e:
        return e.code == code


R = [
    {"rm_id": "10", "repo": "/w/a.git", "branch": "10-x", "integration": "dev", "prod": "main"},
    {"rm_id": "11", "repo": "/w/a.git", "branch": "11-y", "integration": "dev", "prod": "main",
     "live": True},
    {"rm_id": "12", "repo": "/w/b.git", "branch": "12-z", "integration": "dev", "prod": "main"},
    {"rm_id": "13", "error": "RM13 : aucune branche au frontmatter (git.branch)"},
]

# — mode dev : une MR par ticket, vers l'intégration —
pd = ka.mr_batch_plan(R, "dev")
check("dev : une MR par ticket", [r["rm_ids"] for r in pd["runs"]] == [["10"], ["11"], ["12"]],
      str([r["rm_ids"] for r in pd["runs"]]))
check("dev : chacune part de la branche du ticket vers l'intégration",
      all(r["target"] == "dev" for r in pd["runs"]) and pd["runs"][0]["source"] == "10-x")

# — mode prod : une promotion par DÉPÔT —
pp = ka.mr_batch_plan(R, "prod")
check("prod : une seule MR par dépôt (pas une par ticket)",
      [r["rm_ids"] for r in pp["runs"]] == [["10", "11"], ["12"]],
      str([r["rm_ids"] for r in pp["runs"]]))
check("prod : elle promeut l'INTÉGRATION vers la production",
      all(r["source"] == "dev" and r["target"] == "main" for r in pp["runs"]))
check("prod : jamais la branche d'un ticket vers la production",
      all(r["source"] not in ("10-x", "11-y", "12-z") for r in pp["runs"]))

# — ce qui est écarté, et ce qui est signalé —
check("un ticket non résolu est écarté avec sa raison",
      [k["rm_id"] for k in pd["skipped"]] == ["13"]
      and "aucune branche" in pd["skipped"][0]["reason"])
check("…et n'emporte pas le lot", len(pd["runs"]) == 3)
check("une session vivante est SIGNALÉE (pas écartée)",
      pd["live"] == ["11"] and pp["live"] == ["11"])
check("aucun ticket vivant → rien à signaler",
      ka.mr_batch_plan([R[0]], "dev")["live"] == [])
check("liste vide tolérée", ka.mr_batch_plan([], "dev")["runs"] == []
      and ka.mr_batch_plan(None, "prod")["runs"] == [])

# — gardes de l'endpoint —
ka._mr_batch_resolve = lambda rm, mode: dict(
    {"10": R[0], "11": R[1], "12": R[2]}.get(rm, {"rm_id": rm, "error": "inconnu"}), rm_id=rm)
check("mode inconnu → 400", raises(400, lambda: ka.op_mr_batch({"mode": "zzz", "items": [{"rm_id": "10"}]})))
check("items vide → 400", raises(400, lambda: ka.op_mr_batch({"mode": "dev", "items": []})))
check("aucun ticket mergeable → 400",
      raises(400, lambda: ka.op_mr_batch({"mode": "dev", "items": [{"rm_id": "99"}]})))

runs = []
ka.subprocess.run = lambda argv, **kw: runs.append(argv) or type(
    "R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

dry = ka.op_mr_batch({"mode": "dev", "items": [{"rm_id": "10"}, {"rm_id": "11"}], "dry_run": True})
check("dry_run ne merge RIEN", dry["ran"] is False and not runs)
check("dry_run rend le plan complet", len(dry["runs"]) == 2 and "live" in dry)
check("sans confirmation, rien ne part",
      raises(400, lambda: ka.op_mr_batch({"mode": "dev", "items": [{"rm_id": "10"}]})))
check("…et toujours rien d'exécuté", not runs)

res = ka.op_mr_batch({"mode": "dev", "items": [{"rm_id": "10"}, {"rm_id": "10"}], "confirm": True})
check("un doublon ne merge qu'une fois", len(runs) == 1)
check("le merge passe par pm-mr.py (argv, jamais de shell)",
      "pm-mr.py" in " ".join(runs[0]) and isinstance(runs[0], list))
check("dev : argv = create <rm> --source <branche> --target <intégration> --merge",
      runs[0][3] == "10" and "--merge" in runs[0]
      and runs[0][runs[0].index("--source") + 1] == "10-x"
      and runs[0][runs[0].index("--target") + 1] == "dev")
check("le résultat porte le compte rendu par MR", res["ok"] is True and len(res["results"]) == 1)

runs.clear()
ka.op_mr_batch({"mode": "prod", "items": [{"rm_id": "10"}, {"rm_id": "11"}, {"rm_id": "12"}],
                "confirm": True})
check("prod : un run par dépôt", len(runs) == 2)
check("prod : la promotion est SANS ticket (elle n'appartient à aucun)",
      "--no-ticket" in runs[0])
check("prod : dev → main", runs[0][runs[0].index("--source") + 1] == "dev"
      and runs[0][runs[0].index("--target") + 1] == "main")
check("prod : le titre nomme les tickets emportés",
      any("RM10" in a and "RM11" in a for a in runs[0]))

runs.clear()
ka.subprocess.run = lambda argv, **kw: runs.append(argv) or type(
    "R", (), {"returncode": 1, "stdout": "conflit", "stderr": "boom"})()
ko = ka.op_mr_batch({"mode": "dev", "items": [{"rm_id": "10"}], "confirm": True})
check("un merge en échec est rendu tel quel (rc + sortie)",
      ko["ok"] is False and ko["failed"][0]["rc"] == 1 and "conflit" in ko["failed"][0]["stdout"])

# plafond : un lot de merges trop large se confirme explicitement — un merge
# raté au milieu d'une file de vingt laisse un état difficile à relire.
ka._mr_batch_resolve = lambda rm, mode: {"rm_id": rm, "repo": f"/w/{rm}.git",
                                         "branch": f"{rm}-x", "integration": "dev",
                                         "prod": "main"}
gros = [{"rm_id": str(200 + i)} for i in range(ka.MR_BATCH_MAX + 2)]
check("au-delà du plafond → 409",
      raises(409, lambda: ka.op_mr_batch({"mode": "dev", "confirm": True, "items": gros})))
check("…contournable seulement explicitement",
      ka.op_mr_batch({"mode": "dev", "confirm": True, "allow_large": True,
                      "items": gros})["count"] == ka.MR_BATCH_MAX + 2)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests lot de merges RM2720 passent")
