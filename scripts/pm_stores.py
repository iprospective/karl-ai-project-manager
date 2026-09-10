"""pm_stores — où vivent les données de SESSION, résolu une seule fois. RM3085 (lot L5 de RM3015).

Quatre stores, et jusqu'ici autant de résolutions que d'appelants — d'où trois pannes silencieuses
relevées à l'inventaire du 2026-09-08 :

  - `pm_scope.py` lisait le worklog par un chemin **codé en dur** : dès que `PM_SESSION_WORKLOG_DIR`
    est posée (instance de test, cockpit de test), la garde de périmètre RM2274 lisait un dossier
    vide, `_seen_in_session()` rendait `True` « dans le doute », et **la garde ne gardait plus rien
    sans le dire** ;
  - le MÊME dossier a deux variables (`PM_SESSION_WORKLOG_DIR` côté scripts PM,
    `KARL_AGENT_WORKLOG_DIR` côté cockpit) : n'en poser qu'une fait diverger l'écrivain du lecteur ;
  - `KARL_AGENT_STATE_DIR` était résolu quatre fois, dont une **sans son repli** sur
    `KARL_AGENT_LOG_DIR` (`karl-move-session`) : sur un poste qui n'utilise que la seconde, l'outil
    visait un store inexistant et le 3ᵉ ancrage d'une session échouait — le symptôme de RM2391, que
    cet outil est précisément censé réparer.

Ce module est la réponse : **une fonction par store**, qui accepte les deux noms de variable quand
l'histoire en a laissé deux. Il ne DÉCIDE de rien (D020 : la cible du worklog est l'affaire de
RM2992) — il rend seulement la résolution unique, donc corrigeable en un endroit.

Stdlib seulement : `karl-agent.py` l'importe.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Le worklog de session. Deux variables pour un seul dossier : la première posée gagne, et le
#: défaut est commun — c'est ce qui empêche l'écrivain et le lecteur de diverger.
WORKLOG_VARS = ("PM_SESSION_WORKLOG_DIR", "KARL_AGENT_WORKLOG_DIR")
WORKLOG_DEFAULT = "~/.claude/session-worklogs"
#: L'état de karl-agent (stores de spawn, jonctions, journaux). `KARL_AGENT_LOG_DIR` est le repli
#: historique : l'oublier fait viser un dossier vide (RM2391).
STATE_VARS = ("KARL_AGENT_STATE_DIR", "KARL_AGENT_LOG_DIR")
STATE_DEFAULT = "~/.local/state/karl-agent"
#: Les transcripts claude — liste de dossiers, séparés par « : ».
CLAUDE_STORE_VARS = ("PM_CLAUDE_STORES", "KARL_AGENT_CLAUDE_STORES")
CLAUDE_STORE_DEFAULT = "~/.claude/projects"
#: L'historique des demandes, hors périmètre du nettoyage de Claude Code (RM2997).
HISTORY_VARS = ("PM_CLAUDE_HISTORY",)
HISTORY_DEFAULT = "~/.claude/history.jsonl"
#: Les chronos et curseurs par tour, jusqu'ici codés en dur dans trois scripts.
TURN_VARS = ("PM_TURN_STATE_DIR",)
TURN_DEFAULT = "~/.claude/logs"


def _first(names, default, env=None) -> str:
    e = env if env is not None else os.environ
    for n in names:
        v = (e.get(n) or "").strip()
        if v:
            return v
    return default


def _path(names, default, env=None) -> Path:
    return Path(os.path.expanduser(_first(names, default, env)))


def worklog_dir(env=None) -> Path:
    """Le dossier des worklogs de session. À utiliser PARTOUT — un chemin écrit à la main ici
    désarme la garde de périmètre là-bas."""
    return _path(WORKLOG_VARS, WORKLOG_DEFAULT, env)


def worklog_file(session_id: str, env=None) -> Path:
    return worklog_dir(env) / f"{session_id}.json"


def state_dir(env=None) -> Path:
    """L'état de karl-agent, avec son repli historique."""
    return _path(STATE_VARS, STATE_DEFAULT, env)


def claude_stores(env=None) -> list:
    """Les dossiers de transcripts, dans l'ordre ; jamais vide."""
    raw = _first(CLAUDE_STORE_VARS, CLAUDE_STORE_DEFAULT, env)
    out = [Path(os.path.expanduser(p)) for p in raw.split(":") if p.strip()]
    return out or [Path(os.path.expanduser(CLAUDE_STORE_DEFAULT))]


def transcript(session_id: str, env=None):
    """Le transcript d'une session, ou None. Résolution unique, partagée par les scripts et le
    cockpit : deux globs différents finissaient par déclarer une conversation « perdue » alors
    qu'elle était là (RM2949)."""
    if not session_id:
        return None
    for root in claude_stores(env):
        if not root.is_dir():
            continue
        for p in root.glob(f"*/{session_id}.jsonl"):
            return p
    return None


def history_file(env=None) -> Path:
    return _path(HISTORY_VARS, HISTORY_DEFAULT, env)


def turn_dir(env=None) -> Path:
    return _path(TURN_VARS, TURN_DEFAULT, env)


#: Slugification du `cwd` telle que le CLI la fait (vérifiée dans le binaire, cf. RM3057) : TOUT ce
#: qui n'est ni lettre ni chiffre devient un tiret. Deux règles coexistaient — l'autre ne remplaçait
#: que `/` et `.`, si bien qu'un chemin contenant `_` produisait deux slugs différents et que la
#: reprise ne retrouvait jamais son dossier.
def cwd_slug(path) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]", "-", str(path or ""))
