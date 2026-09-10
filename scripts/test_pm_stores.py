#!/usr/bin/env python3
"""Tests RM3085 — les stores de session résolus une seule fois, et la garde qui refuse.

Le test qui compte est le premier : avant, `pm_scope` lisait le worklog par un chemin CODÉ EN DUR.
Dès que `PM_SESSION_WORKLOG_DIR` était posée, il lisait un dossier vide, `_seen_in_session()`
répondait « True, dans le doute » et la garde de périmètre RM2274 **laissait tout passer sans le
dire**. Une garde qui ne garde plus se remarque le jour où elle aurait dû arrêter quelque chose.

Le reste verrouille les autres pannes silencieuses de l'inventaire : deux variables pour un même
dossier, un repli oublié (RM2391), deux slugifications du `cwd`, et sept formats de journal.

Lancer : python3 scripts/test_pm_stores.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                       # noqa: E402
hermetic_core()
import pm_stores                                             # noqa: E402
import pm_task_log                                           # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ── 1. LA garde : le périmètre projet refuse toujours, worklog déplacé ou non ─
spec = importlib.util.spec_from_file_location("pm_scope", HERE / "pm_scope.py")
scope = importlib.util.module_from_spec(spec); spec.loader.exec_module(scope)

tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-stores-"))
wl = tmp / "ailleurs"; wl.mkdir()
sid = "sess-3085"
(wl / f"{sid}.json").write_text(json.dumps({"items": [{"ref": "RM111"}]}), encoding="utf-8")

import os
os.environ["CLAUDE_CODE_SESSION_ID"] = sid
os.environ["PM_SESSION_WORKLOG_DIR"] = str(wl)
check("le worklog déplacé est LU (la garde voit ce que la session a ouvert)", scope._seen_in_session(111) is True)
check("…et un ticket JAMAIS ouvert dans la session est refusé — c'est le cas qui se perdait",
      scope._seen_in_session(999) is False)
os.environ.pop("PM_SESSION_WORKLOG_DIR")
check("worklog introuvable : la garde laisse passer plutôt que de bloquer un humain",
      scope._seen_in_session(999) is True)

# ── 2. une variable ou l'autre, jamais deux vérités ─────────────────────────
E = {"PM_SESSION_WORKLOG_DIR": "/a/worklogs"}
check("PM_SESSION_WORKLOG_DIR reconnue", str(pm_stores.worklog_dir(E)) == "/a/worklogs")
check("KARL_AGENT_WORKLOG_DIR aussi (le cockpit et les scripts lisent le MÊME dossier)",
      str(pm_stores.worklog_dir({"KARL_AGENT_WORKLOG_DIR": "/b/worklogs"})) == "/b/worklogs")
check("la première posée gagne, jamais un mélange",
      str(pm_stores.worklog_dir({"PM_SESSION_WORKLOG_DIR": "/a", "KARL_AGENT_WORKLOG_DIR": "/b"})) == "/a")
check("défaut commun", str(pm_stores.worklog_dir({})).endswith(".claude/session-worklogs"))
check("fichier d'une session", pm_stores.worklog_file("abc", E).name == "abc.json")

# ── 3. le repli oublié qui reproduisait RM2391 ──────────────────────────────
check("KARL_AGENT_STATE_DIR", str(pm_stores.state_dir({"KARL_AGENT_STATE_DIR": "/s"})) == "/s")
check("…et son repli KARL_AGENT_LOG_DIR — l'oublier faisait viser un store vide (RM2391)",
      str(pm_stores.state_dir({"KARL_AGENT_LOG_DIR": "/l"})) == "/l")
check("les deux : la principale gagne",
      str(pm_stores.state_dir({"KARL_AGENT_STATE_DIR": "/s", "KARL_AGENT_LOG_DIR": "/l"})) == "/s")

# ── 4. transcripts : une liste, jamais vide ─────────────────────────────────
check("PM_CLAUDE_STORES, séparés par « : »",
      [str(p) for p in pm_stores.claude_stores({"PM_CLAUDE_STORES": "/x:/y"})] == ["/x", "/y"])
check("KARL_AGENT_CLAUDE_STORES est le même store vu du cockpit",
      [str(p) for p in pm_stores.claude_stores({"KARL_AGENT_CLAUDE_STORES": "/z"})] == ["/z"])
check("valeur vide : on retombe sur le défaut, jamais sur une liste vide",
      len(pm_stores.claude_stores({"PM_CLAUDE_STORES": "  "})) == 1)

# ── 5. une seule slugification du cwd ───────────────────────────────────────
check("tout ce qui n'est pas alphanumérique devient « - » (règle du CLI)",
      pm_stores.cwd_slug("/zfs/workspaces/.mmi-pm-core") == "-zfs-workspaces--mmi-pm-core")
check("…y compris le tiret bas — c'est LUI qui produisait deux slugs et perdait la reprise",
      pm_stores.cwd_slug("/a/mon_projet") == "-a-mon-projet")
check("la casse est préservée", pm_stores.cwd_slug("/A/Bc") == "-A-Bc")

srcs = {f.name: f.read_text(encoding="utf-8") for f in HERE.glob("*.py") if not f.name.startswith("test_")}
autres = [n for n, s in srcs.items() if 're.sub(r"[/.]", "-"' in s]
check("plus aucune seconde règle de slug dans les scripts", not autres, str(autres))

# ── 6. un seul format de journal de ticket ──────────────────────────────────
e = pm_task_log.entry("Essai (outil)", "corps", tokens=3, minutes=4, when="2026-09-10T12:00")
check("le format est celui que pm-task-log parse",
      e.startswith("\n## 2026-09-10T12:00 — Essai (outil)\nTokens : 3 | Durée : 4 min\n\n") and e.endswith("corps\n"), repr(e))
sheet = tmp / "RM1_x.md"; sheet.write_text("---\n---\n", encoding="utf-8")
log = pm_task_log.append(sheet, "Outil", "message")
check("écrit à côté de la fiche", log.name == "RM1_x.log.md" and "message" in log.read_text(encoding="utf-8"))
check("appelée sur le log lui-même : idempotent", pm_task_log.log_path(log) == log)
copies = [n for n, s in srcs.items() if "def append_log" in s and "pm_task_log.append" not in s]
check("plus de format de journal reconstruit à la main", not copies, str(copies))
manquantes = [n for n, s in srcs.items() if "pm_task_log.append" in s and "Tokens" in s.split("pm_task_log.append")[0][-200:]]
check("l'entrée de pm-env-expose porte enfin sa ligne « Tokens » (elle était invisible du parseur)",
      "pm_task_log.append(task_file" in srcs.get("pm-env-expose.py", ""))

# ── 7. le store mort a disparu ──────────────────────────────────────────────
ka = srcs.get("karl-agent.py", "")
check("`answers.jsonl` n'est plus écrit (aucun lecteur depuis RM2302) ; le journal structuré le remplace",
      "ANSWERS_LOG" not in ka and '_jlog("claude", "info", "réponse « Oui »' in ka)

# ── 8. les stores non bornés le sont ────────────────────────────────────────
import importlib.util, time as _t
spec = importlib.util.spec_from_file_location("ka3085", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec); sys.modules["ka3085"] = ka; spec.loader.exec_module(ka)
logs = tmp / "logs"; logs.mkdir()
ka.LOG_DIR = logs
vieux = logs / "karl-RM1.log"; vieux.write_text("x"); os.utime(vieux, (0, _t.time() - 60 * 86400))
frais = logs / "karl-RM2.log"; frais.write_text("x")
autre = logs / "pm-runs.jsonl"; autre.write_text("x"); os.utime(autre, (0, _t.time() - 60 * 86400))
check("les logs pipe-pane trop vieux sont purgés", ka.purge_tmux_logs(30) == 1 and not vieux.exists())
check("…le log d'une session récente est gardé", frais.exists())
check("…et rien d'autre n'est touché", autre.exists())
check("rétention à 0 : purge débrayée", ka.purge_tmux_logs(0) == 0)

spec2 = importlib.util.spec_from_file_location("pmsess", HERE / "pm_session.py")
pms = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(pms)
idx = {str(i): {"seq": i} for i in range(1, 21)}
pms.INDEX_KEEP = 5
check("le registre de sessions est borné aux plus récents", pms._trim(idx) and sorted(int(k) for k in idx) == [16, 17, 18, 19, 20])
check("sous la borne : rien n'est retiré", pms._trim(idx) is False)
pms.INDEX_KEEP = 0
big = {str(i): {} for i in range(30)}
check("borne à 0 : bornage débrayé", pms._trim(big) is False and len(big) == 30)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — stores de session et journal de ticket (RM3085)")
