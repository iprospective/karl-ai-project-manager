#!/usr/bin/env python3
"""Tests RM2808 — le prompt initial n'est jamais injecté à l'aveugle.

Régression corrigée : ENGINES["claude"]["ready_markers"] contenait « ❯ », qui
matche le « ❯ 1. Yes, I trust this folder » de l'écran de confiance de dossier
de Claude Code. `_wait_engine_ready` croyait donc le TUI prêt alors qu'un écran
MODAL était affiché : le prompt partait en send-keys (avalé, le dialogue n'a pas
de champ de saisie) et l'Enter qui suit VALIDAIT « Yes, I trust this folder ».
Double dégât : prompt perdu en silence, et confiance du dossier — donc les
permissions pré-approuvées de son settings.local.json — accordée sans décision
humaine (incident du 2026-08-21, session karl-RM1905).

Unitaire (sans tmux, sans réseau) : tmux est doublé par un faux pane scripté,
c'est la VRAIE _wait_engine_ready / _send_initial_prompt / op_spawn qui tourne.
Lancer : python3 scripts/test_karl_agent_prompt_injection.py
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


# Écrans réels, recopiés du log de l'incident (~/.local/state/karl-agent/karl-RM1905.log).
TRUST_SCREEN = """Accessing workspace:
/zfs/workspaces/calicote/infra
Quick safety check: Is this a project you created or one you trust?
⚠ This folder pre-approves 12 tool permissions in .claude/settings.local.json
❯ 1. Yes, I trust this folder
  2. No, exit
Enter to confirm · Esc to cancel"""

READY_TUI = """╭─── Claude Code v2.1.238 ───╮
│ /zfs/workspaces/calicote/infra │
╰────────────────────────────────╯
❯ Try "edit <filepath> to..."
⏵⏵ auto mode on (shift+tab to cycle) · ← for agents"""


def harness(panes):
    """Double tmux : `panes` est la suite d'écrans que capture-pane renverra.
    Le dernier écran persiste. Retourne le journal des touches envoyées."""
    keys = []
    state = {"i": 0}

    def fake_tmux(*args):
        if args[0] == "capture-pane":
            seq = panes[min(state["i"], len(panes) - 1)]
            state["i"] += 1
            return 0, seq, ""
        if args[0] == "send-keys":
            keys.append(args[-1])
        return 0, "", ""

    ka._tmux = fake_tmux
    ka.time.sleep = lambda s: None
    return keys


# ── 1. Le marqueur « ❯ » de l'écran de confiance ne doit PLUS valoir « prêt » ──
harness([TRUST_SCREEN])
check("écran de confiance seul → 'blocked' (et non 'ready')",
      ka._wait_engine_ready("demo", "claude", timeout=0.5) == "blocked")

check("« ❯ » nu n'est plus un marqueur de disponibilité",
      "❯" not in ka.ENGINES["claude"]["ready_markers"])

# ── 2. Bloqué ⇒ RIEN n'est tapé (ni texte, ni Enter : c'est l'Enter qui trustait) ──
keys = harness([TRUST_SCREEN])
state = ka._send_initial_prompt("demo", "claude", "traite la tâche RM1905")
check("écran de confiance → prompt différé, pas envoyé", state == "differe-dialogue")
check("écran de confiance → AUCUNE touche envoyée (pas d'auto-trust)", keys == [])

# ── 3. TUI réellement prêt ⇒ le prompt part, texte puis Enter ──
keys = harness([READY_TUI, READY_TUI, READY_TUI + "\ntraite la tâche RM1905"])
state = ka._send_initial_prompt("demo", "claude", "traite la tâche RM1905")
check("TUI prêt → prompt envoyé", state == "envoye")
check("TUI prêt → texte puis Enter", keys == ["traite la tâche RM1905", "Enter"])

# ── 4. Dialogue PUIS TUI prêt ⇒ on attend, puis on écrit ──
keys = harness([TRUST_SCREEN, READY_TUI, READY_TUI, READY_TUI + "\nbonjour"])
check("dialogue puis TUI prêt → 'ready' après attente",
      ka._send_initial_prompt("demo", "claude", "bonjour") == "envoye")

# ── 5. Pane immobile après le send-keys ⇒ pas d'Enter à l'aveugle ──
keys = harness([READY_TUI])
state = ka._send_initial_prompt("demo", "claude", "perdu dans le vide")
check("pane inchangé après frappe → 'non-pris'", state == "non-pris")
check("pane inchangé après frappe → pas d'Enter envoyé", "Enter" not in keys)

# ── 6. op_spawn remonte l'état du prompt au client (plus de perte silencieuse) ──
# `_has_session` : False à l'entrée d'op_spawn (garde du 409), True ensuite —
# la session tmux existe une fois créée, et c'est elle que op_send vérifie.
_seen = {"n": 0}
ka._has_session = lambda rm_id: _seen.__setitem__("n", _seen["n"] + 1) or _seen["n"] > 1
ka._start_session_tmux = lambda *a, **k: None
ka._resolve_cwd = lambda c: pathlib.Path(c or "/zfs/workspaces")
ka._record_run = lambda *a, **k: None
ka._record_key = lambda *a, **k: None
ka._auto_join_current_set = lambda sid, ctx=None: {"group": "d", "joined": True}

_seen["n"] = 0
harness([TRUST_SCREEN])
res = ka.op_spawn({"rm_id": "demo", "engine": "claude", "cwd": "/zfs/workspaces",
                   "prompt": "traite la tâche"}, {"user": None})
check("op_spawn : prompt non livré → l'état le dit",
      res.get("prompt") == "differe-dialogue")

_seen["n"] = 0
harness([READY_TUI, READY_TUI, READY_TUI + "\ntraite la tâche"])
res = ka.op_spawn({"rm_id": "demo", "engine": "claude", "cwd": "/zfs/workspaces",
                   "prompt": "traite la tâche"}, {"user": None})
check("op_spawn : prompt livré → 'envoye'", res.get("prompt") == "envoye")

_seen["n"] = 0
harness([READY_TUI])
res = ka.op_spawn({"rm_id": "demo", "engine": "claude", "cwd": "/zfs/workspaces"},
                  {"user": None})
check("op_spawn sans prompt → 'absent'", res.get("prompt") == "absent")

# ── 7. Non-régression : un moteur sans marqueur (shell) reste immédiat ──
harness([""])
check("shell (aucun marqueur) → 'ready' sans attente",
      ka._wait_engine_ready("demo", "shell", timeout=0.5) == "ready")

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : " + ", ".join(fails))
    sys.exit(1)
print("✓ tous les tests passent")
