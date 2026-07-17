#!/usr/bin/env python3
"""Tests RM2327 — « Oui à tout » global + auto-oui par session (timeout).

Unitaire (sans tmux, réseau ni thread) : op_approve_all, op_auto_yes et
_auto_yes_tick (passe de boucle testée avec horloge injectée).
Lancer : python3 scripts/test_karl_agent_auto_yes.py
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

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


# — harnais : tmux/panes simulés, journal en tmpdir —
PANES = {}      # rm_id → contenu du pane
SENT = []       # (rm_id, touches)


def fake_tmux(*args, timeout=10):
    if args[0] == "capture-pane":
        rm = args[3].removeprefix("karl-RM").removeprefix("karl-")
        return 0, PANES.get(rm, "$ repos"), ""
    if args[0] == "send-keys":
        rm = args[2].removeprefix("karl-RM").removeprefix("karl-")
        SENT.append((rm, args[-1]))
        return 0, "", ""
    return 0, "", ""


ka._tmux = fake_tmux
ka._has_session = lambda rm_id: rm_id in PANES
ka._list_sessions = lambda: [{"rm_id": rm} for rm in PANES]
ka.ANSWERS_LOG = pathlib.Path(tempfile.mkdtemp()) / "answers.jsonl"

MENU = "Do you want to proceed?\n❯ 1. Yes\n  2. No"
CHOICE = "Quelle approche ?\n❯ 1. Refactor complet\n  2. Patch minimal"

# — états de session (RM2327) : oui/non → attention, choix multiple → choice —
PANES.update({"21": MENU, "22": CHOICE, "23": "$ idle"})
check("état : oui/non → attention", ka._session_state("21", "claude") == "attention")
check("état : choix multiple → choice", ka._session_state("22", "claude") == "choice")
check("état : rien → idle", ka._session_state("23", "claude") == "idle")
PANES.clear()
SENT.clear()

# — op_approve_all : répond aux sessions en question, ignore les autres —
PANES.update({"11": MENU, "12": "$ idle", "13": "Overwrite? (y/n)", "14": CHOICE})
r = ka.op_approve_all({})
check("tout : 2 sessions répondues", sorted(a["rm_id"] for a in r["approved"]) == ["11", "13"])
check("tout : sans question ET choix multiple ignorés (14 jamais auto-répondu)",
      sorted(r["skipped"]) == ["12", "14"])
check("tout : menu → « 1 », y/n → « y »",
      {a["rm_id"]: a["sent"] for a in r["approved"]} == {"11": "1", "13": "y"})

# — op_auto_yes : armement, bornes, désarmement —
ka._AUTO_YES.clear()
r = ka.op_auto_yes({"rm_id": "11", "minutes": 30})
check("auto : armé avec échéance", r["auto_yes_until"] and "11" in ka._AUTO_YES)
try:
    ka.op_auto_yes({"rm_id": "11", "minutes": 999})
    check("auto : borne max", False)
except ka.ApiError as e:
    check("auto : borne max (timeout obligatoire)", e.code == 400)
try:
    ka.op_auto_yes({"rm_id": "404", "minutes": 10})
    check("auto : session absente refusée", False)
except ka.ApiError as e:
    check("auto : session absente refusée", e.code == 404)
r = ka.op_auto_yes({"rm_id": "11", "minutes": 0})
check("auto : désarmé (minutes=0)", r["auto_yes_until"] is None and "11" not in ka._AUTO_YES)

# — _auto_yes_tick : répond, purge expirés et sessions disparues —
SENT.clear()
ka._AUTO_YES.clear()
ka._AUTO_YES.update({"11": 1000.0, "13": 1000.0, "12": 1000.0, "99": 1000.0, "old": 10.0})
ticked = ka._auto_yes_tick(now=100.0)   # 99 : session absente ; old : expiré
check("tick : répond aux questions armées", sorted(t[0] for t in ticked) == ["11", "13"])
check("tick : session sans question conservée (retentera)", "12" in ka._AUTO_YES)
check("tick : expiré purgé", "old" not in ka._AUTO_YES)
check("tick : session disparue purgée", "99" not in ka._AUTO_YES)

# — même passe re-jouée après réponse : la question a disparu → plus d'envoi —
PANES["11"] = PANES["13"] = "$ travail reparti"
SENT.clear()
check("tick : idempotent une fois la question partie",
      ka._auto_yes_tick(now=100.0) == [] and not SENT)

# — journal : provenance tracée (tout / auto) —
lines = [json.loads(ln) for ln in ka.ANSWERS_LOG.read_text().splitlines()]
check("journal : sources manuel/tout/auto tracées",
      {e["source"] for e in lines} == {"tout", "auto"} and len(lines) == 4)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests auto-oui RM2327 passent")
