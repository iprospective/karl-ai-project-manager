#!/usr/bin/env python3
"""Tests RM2951 — un spawn ne valide plus l'invite de confiance du moteur.

Incident (RM2950, client matnat) : session lancée sur un dossier que claude
n'avait jamais ouvert. Le TUI s'arrête alors sur son garde-fou — « Quick safety
check: Is this a project you created or one you trust? », avec le curseur sur
« ❯ No, exit ». Or `ready_markers` de claude contient « ❯ » : karl-agent croyait
le TUI prêt, envoyait le prompt PUIS Enter — donc validait « No, exit ». Claude
quittait, la session tmux mourait, et `POST /spawn` répondait quand même 201 :
clé et entité écrites pour une session qui n'a jamais vécu, invisible partout.

Ce qu'on protège :
  - le blocage PRIME sur les marqueurs de prêt (le pane contient les deux) ;
  - un pane bloqué ne reçoit ni prompt ni Enter, et la réponse le DIT ;
  - une session morte aussitôt ne rend plus 201 en silence ;
  - le chemin nominal (TUI prêt) envoie toujours le prompt.

Unitaire (sans tmux ni réseau) : tmux et les écritures d'index sont doublés,
c'est la VRAIE op_spawn qui est appelée.
Lancer : python3 scripts/test_karl_agent_spawn_trust.py
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


# Le pane tel que claude le rend sur un dossier jamais approuvé — « ❯ » compris.
PANE_TRUST = """
────────────────────────────────────────────────────────────
 Accessing workspace:

 /zfs/workspaces/matnat/erp_old

 Quick safety check: Is this a project you created or one you trust?

 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
"""
PANE_READY = "\n ❯ \n ? for shortcuts                            accept edits on\n"
PANE_BOOT = "\n Welcome to Claude Code\n loading…\n"

# ── 1. lire le pane : bloqué / prêt / en démarrage ───────────────────────────
check("l'invite de confiance est reconnue MALGRÉ le « ❯ » de prêt",
      ka.engine_pane_state(PANE_TRUST, "claude") == "blocked",
      ka.engine_pane_state(PANE_TRUST, "claude"))
check("un TUI prêt reste prêt", ka.engine_pane_state(PANE_READY, "claude") == "ready")
check("un TUI qui démarre n'est ni prêt ni bloqué",
      ka.engine_pane_state(PANE_BOOT, "claude") == "starting")
check("un moteur sans marqueur (shell) est prêt d'emblée",
      ka.engine_pane_state("", "shell") == "ready")
check("moteur inconnu : prêt plutôt que bloqué (on ne fabrique pas un refus)",
      ka.engine_pane_state(PANE_TRUST, "inconnu") == "ready")

# ── harnais : rien ne sort du process ────────────────────────────────────────
PANE = {"txt": PANE_READY}
ALIVE = {"live": set()}
sent, keys, enters = [], [], []
ka._has_session = lambda rm_id: False          # garde d'entrée : rien ne tourne encore
ka._session_started = lambda rm_id: rm_id in ALIVE["live"]      # RM2951 : a-t-elle survécu ?
ka._start_session_tmux = lambda rm_id, cmd, cwd, w, h, env: ALIVE["live"].add(rm_id)
ka._resolve_cwd = lambda c: pathlib.Path(c or "/zfs/workspaces")
ka._record_run = lambda *a, **k: None
ka._record_key = lambda *a, **k: keys.append(a)
ka._auto_join_active_set = lambda sid, ctx=None: {"group": "default", "joined": True}
ka._apply_memory_limits = lambda name: None
ka.op_send = lambda payload: sent.append(payload)
ka._tmux = lambda *a: (enters.append(a) or (0, PANE["txt"], "")) if a[0] == "capture-pane" \
    else (enters.append(a) or (0, "", ""))


def spawn(prompt="fais X"):
    """op_spawn de zéro : la session n'existe pas encore, elle naît au démarrage."""
    ALIVE["live"] = set()
    sent.clear(); enters.clear(); keys.clear()
    return ka.op_spawn({"rm_id": "2950", "engine": "claude",
                        "cwd": "/zfs/workspaces/matnat/erp_old", "prompt": prompt},
                       {"user": None})


# ── 2. pane bloqué : aucun prompt, aucun Enter, et on le dit ─────────────────
PANE["txt"] = PANE_TRUST
ka.ENGINE_READY_TIMEOUT = 0.2          # pas d'attente réelle en test
res = spawn()
check("bloqué : le prompt n'est PAS envoyé", sent == [], sent)
check("bloqué : aucune touche Enter n'est expédiée",
      not any(a[0] == "send-keys" for a in enters), enters)
check("bloqué : la réponse dit que le prompt n'est pas parti",
      res.get("prompt_sent") is False, res)
check("bloqué : la réponse dit POURQUOI",
      "approbation" in (res.get("blocked") or "").lower()
      or "confiance" in (res.get("blocked") or "").lower(), res.get("blocked"))
check("bloqué : la session tourne toujours (on ne la tue pas)",
      res.get("created") is True and ka._session_started("2950"))

# ── 3. chemin nominal : le prompt part ───────────────────────────────────────
PANE["txt"] = PANE_READY
res = spawn()
check("prêt : le prompt est envoyé", len(sent) == 1, sent)
check("prêt : l'Enter suit", any(a[0] == "send-keys" and a[-1] == "Enter" for a in enters), enters)
check("prêt : la réponse l'atteste",
      res.get("prompt_sent") is True and res.get("blocked") is None, res)

# ── 4. session morte aussitôt : plus de 201 muet ─────────────────────────────
PANE["txt"] = PANE_READY
ka._start_session_tmux = lambda rm_id, cmd, cwd, w, h, env: None   # naît et meurt
try:
    spawn()
    check("morte-née : refus explicite au lieu d'un 201", False)
except ka.ApiError as e:
    check("morte-née : refus explicite au lieu d'un 201",
          e.code >= 500 and ("arrêtée" in e.msg or "morte" in e.msg), f"{e.code} {e.msg}")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests spawn/confiance RM2951 passent")
