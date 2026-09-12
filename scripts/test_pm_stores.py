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
check("défaut commun, désormais sous le `var/` du repo PM (RM2992) — le même pour les deux variables",
      str(pm_stores.worklog_dir({})) == str(pm_stores.state_root({}) / "session-worklogs"))
check("fichier d'une session", pm_stores.worklog_file("abc", E).name == "abc.json")

# ── 2b. RM2992 : la racine est le `var/` du repo PM, plus le home ───────────
import importlib as _il
_il.import_module("pm_stores")
pm_stores._ROOT_CACHE.clear()
check("PM_STATE_DIR impose la racine", str(pm_stores.state_root({"PM_STATE_DIR": "/r"})) == "/r")
E2 = {"PM_STATE_DIR": "/r"}
check("le worklog s'y range", str(pm_stores.worklog_dir(E2)) == "/r/session-worklogs")
check("l'état de karl aussi", str(pm_stores.state_dir(E2)) == "/r/karl-agent")
check("les curseurs de tour aussi — ils étaient dans ~/.claude/logs", str(pm_stores.turn_dir(E2)) == "/r/turns")
check("le registre des sessions aussi, et il est enfin PARAMÉTRABLE (demande du 2026-09-12)",
      str(pm_stores.sessions_dir(E2)) == "/r/sessions"
      and str(pm_stores.sessions_dir({"PM_SESSIONS_DIR": "/ailleurs"})) == "/ailleurs")
check("une variable de store reste prioritaire sur la racine",
      str(pm_stores.worklog_dir({"PM_STATE_DIR": "/r", "PM_SESSION_WORKLOG_DIR": "/w"})) == "/w")
# le repli : là où la config PM ne se charge pas, le chemin d'hier reprend la main plutôt que de planter
_vrai = pm_stores.state_root
pm_stores.state_root = lambda env=None: None
try:
    check("sans config PM résoluble, chaque store retombe sur son chemin d'hier (jamais d'exception)",
          str(pm_stores.worklog_dir({})).endswith(".claude/session-worklogs")
          and str(pm_stores.state_dir({})).endswith("state/karl-agent")
          and str(pm_stores.turn_dir({})).endswith(".claude/logs"))
finally:
    pm_stores.state_root = _vrai
check("les transcripts, eux, NE bougent PAS : Claude Code les écrit, on les lit",
      str(pm_stores.claude_stores({})[0]).endswith(".claude/projects")
      and str(pm_stores.history_file({})).endswith(".claude/history.jsonl"))
# RM2385 : l'ÉTAT peut être partagé pendant que les LOGS d'instance restent locaux
check("KARL_AGENT_STATE_DIR ne détourne pas les logs d'instance (RM2385)",
      str(pm_stores.log_dir({"KARL_AGENT_STATE_DIR": "/s", "PM_STATE_DIR": "/r"})) == "/r/karl-agent"
      and str(pm_stores.state_dir({"KARL_AGENT_STATE_DIR": "/s", "PM_STATE_DIR": "/r"})) == "/s")
check("…mais KARL_AGENT_LOG_DIR, lui, les détourne", str(pm_stores.log_dir({"KARL_AGENT_LOG_DIR": "/l"})) == "/l")

# ── 2c. RM2992 : la migration ───────────────────────────────────────────────
mig_spec = importlib.util.spec_from_file_location("pm_stores_migrate", HERE / "pm-stores-migrate.py")
mig = importlib.util.module_from_spec(mig_spec); mig_spec.loader.exec_module(mig)
mhome = tmp / "home"; mvar = tmp / "var"
(mhome / ".claude" / "session-worklogs").mkdir(parents=True)
(mhome / ".claude" / "logs").mkdir(parents=True)
(mhome / ".local" / "state" / "karl-agent" / "sessions").mkdir(parents=True)
(mhome / ".claude" / "session-worklogs" / "a.json").write_text("{}", encoding="utf-8")
(mhome / ".claude" / "session-worklogs" / "deja.json").write_text("nouveau", encoding="utf-8")
(mhome / ".claude" / "logs" / "turn-start-x.json").write_text("{}", encoding="utf-8")
(mhome / ".claude" / "logs" / "debug-de-claude-code.log").write_text("pas à nous", encoding="utf-8")
(mhome / ".local" / "state" / "karl-agent" / "sessions" / "s.json").write_text("{}", encoding="utf-8")
(mhome / ".local" / "state" / "karl-agent" / "answers.jsonl").write_text("mort", encoding="utf-8")
(mvar / "session-worklogs").mkdir(parents=True)
(mvar / "session-worklogs" / "deja.json").write_text("ANCIEN", encoding="utf-8")
os.environ["HOME"] = str(mhome)
import pathlib as _pl
mig.pm_stores.WORKLOG_LEGACY = str(mhome / ".claude" / "session-worklogs")
mig.pm_stores.STATE_LEGACY = str(mhome / ".local" / "state" / "karl-agent")
mig.pm_stores.TURN_LEGACY = str(mhome / ".claude" / "logs")
mig.pm_stores.DEPLACABLES = ((mig.pm_stores.WORKLOG_LEGACY, "session-worklogs"),
                             (mig.pm_stores.STATE_LEGACY, "karl-agent"),
                             (mig.pm_stores.TURN_LEGACY, "turns"))
ENVM = {"PM_STATE_DIR": str(mvar)}
avant = [(sub, src, dst) for sub, src, dst in mig.plan(ENVM)]
check("le plan ne retient que les stores qui existent encore", len(avant) == 3, str(avant))
tot = [mig.migrer(src, dst, sub, dry=True) for sub, src, dst in avant]
check("à blanc, rien ne bouge", (mvar / "session-worklogs" / "deja.json").read_text() == "ANCIEN"
      and (mhome / ".claude" / "session-worklogs" / "a.json").exists())
for sub, src, dst in avant:
    mig.migrer(src, dst, sub)
check("les fichiers arrivent, arborescence conservée",
      (mvar / "session-worklogs" / "a.json").exists() and (mvar / "karl-agent" / "sessions" / "s.json").exists()
      and (mvar / "turns" / "turn-start-x.json").exists())
check("un fichier DÉJÀ à destination n'est jamais remplacé — relancer la migration ne détruit rien",
      (mvar / "session-worklogs" / "deja.json").read_text() == "ANCIEN"
      and (mhome / ".claude" / "session-worklogs" / "deja.json").exists())
check("ce qui n'est pas à nous reste où c'est (dossier partagé avec Claude Code)",
      (mhome / ".claude" / "logs" / "debug-de-claude-code.log").exists()
      and not (mvar / "turns" / "debug-de-claude-code.log").exists())
check("un store MORT n'est pas emporté dans le dossier propre",
      (mhome / ".local" / "state" / "karl-agent" / "answers.jsonl").exists()
      and not (mvar / "karl-agent" / "answers.jsonl").exists())
check("le dossier créé est réellement partageable (setgid + écriture du groupe)",
      (mvar / "karl-agent").stat().st_mode & 0o2775 == 0o2775, oct((mvar / "karl-agent").stat().st_mode))
check("une trace reste dans l'ancien dossier, pour l'humain qui le retrouve",
      (mhome / ".claude" / "session-worklogs" / mig.TRACE).is_file())
again = [mig.migrer(src, dst, sub) for sub, src, dst in avant]
check("rejouer ne déplace plus rien (idempotent)", all(n == 0 for n, _d, _p in again), str(again))

# ── 2d. RM2992 : plus un seul script ne vise un store tout seul ─────────────
_STORES = ("session-worklogs", 'state" / "karl-agent', '"karl-agent"')
_EXEMPT = {"pm_stores.py", "pm-stores-migrate.py", "pm_log.py"}   # la résolution, la migration, et le journal (sa propre racine)
sans_import = []
for f in sorted(HERE.glob("*.py")):
    if f.name.startswith("test") or f.name in _EXEMPT:
        continue
    src = f.read_text(encoding="utf-8")
    corps = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    # `deploy/karl-agent/cockpit/…` est un chemin DU DÉPÔT, pas un store : ne pas le confondre
    corps = "\n".join(l for l in corps.splitlines() if "deploy" not in l and "cockpit" not in l)
    if any(m in corps for m in _STORES) and "pm_stores" not in corps:
        sans_import.append(f.name)
check("un script qui vise un store passe par pm_stores — sinon il continue de viser le home "
      "après le déplacement, et écrit seul dans son coin (RM2992)", not sans_import, str(sans_import))

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


# ── RM3088 : rattachement par RÉFÉRENCE, pas par texte ──────────────────────
import importlib.util as _iu
_spec = _iu.spec_from_file_location("brief", HERE / "pm-task-brief.py")
_brief = _iu.module_from_spec(_spec); _spec.loader.exec_module(_brief)
check("une notification --ref RM1234 est rattachée même si son texte ne cite pas le numéro",
      _brief.rattache({"ref": "RM1234", "message": "secret affiché dans un log"}, 1234) is True)
check("…et elle ne l'est pas à un AUTRE ticket qui figure dans son texte",
      _brief.rattache({"ref": "RM1234", "message": "vu pendant RM9999"}, 9999) is False)
check("sans référence, le texte sert de repli (les anciennes entrées restent trouvables)",
      _brief.rattache({"message": "problème sur RM777"}, 777) is True)
check("une demande porte son ticket dans `ticket`", _brief.rattache({"ticket": "RM55", "text": "faire X"}, 55) is True)
check("rien ne rattache une entrée muette", _brief.rattache({"message": "un fait"}, 1) is False)
_src_brief = (HERE / "pm-task-brief.py").read_text(encoding="utf-8")
check("le dossier de reprise restitue les demandes du ticket (il les ignorait)",
      '"requests": [' in _src_brief and "📥" in _src_brief)
_ka = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le worklog du cockpit sert « questions_open » — un seul canal (D021)",
      '"questions_open": _worklog_questions(items)' in _ka)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — stores de session et journal de ticket (RM3085)")
