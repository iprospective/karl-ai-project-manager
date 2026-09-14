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
l'histoire en a laissé deux. Il rend la résolution unique, donc corrigeable en un endroit — ce qui
a permis à **RM2992** de déplacer les stores en changeant ce seul fichier.

**RM2992 (2026-09-12) : les stores de PM vivent dans `var/` du repo PM, plus dans le home.** Ils y
étaient « par défaut d'avoir choisi », et c'est le home qui décidait de qui voit quoi : un agent ne
voyait pas le travail d'un autre, et le régime de partage dépendait du hasard des montages
(`~/.claude` partagé hôte↔conteneur, `~/.local/state` non — RM2391 s'est fait piéger dessus).
Quatre stores déménagent : worklogs de session, état de karl-agent, curseurs de tour, registre des
sessions. Les transcripts et `history.jsonl` restent où ils sont : **Claude Code les écrit**, nous
ne faisons que les lire. Le partage s'arrête à la machine : `var/` n'est pas versionné.

Chaque store garde son **repli d'hier** : là où la config PM ne se charge pas, le chemin du home
reprend la main plutôt que de planter. Ce repli n'écrit pourtant plus à côté, car
`pm-stores-migrate` remplace l'ancien dossier **par un lien** vers le nouveau : un écrivain resté en
arrière — instance non redémarrée, session ouverte avant la mise à jour, script lancé sans `.env` —
atterrit au bon endroit sans rien savoir du déplacement. La migration de l'existant est faite une
fois par `pm-stores-migrate` (appelé par `pm-core-update`).

Stdlib seulement : `karl-agent.py` l'importe ; `pm_paths` n'est tiré qu'à la demande, en cache.
"""
from __future__ import annotations

import os
from pathlib import Path

#: RM2992 — la RACINE des données de session, commune à tous les agents de la machine : le `var/`
#: du repo PM. Chaque store avait jusqu'ici son défaut dans le HOME de l'utilisateur, ce qui
#: rendait invisible à un agent le travail d'un autre — et faisait dépendre le régime de partage
#: du hasard des montages (`~/.claude` partagé hôte↔conteneur, `~/.local/state` non : RM2391).
#: `PM_STATE_DIR` la surcharge ; sinon elle est résolue par la config PM (`PMConfig.state_dir`).
#: **Le partage s'arrête à la machine** : ce dossier n'est pas versionné (`var/` est en .gitignore).
STATE_ROOT_VAR = "PM_STATE_DIR"

#: Le worklog de session. Deux variables pour un seul dossier : la première posée gagne, et le
#: défaut est commun — c'est ce qui empêche l'écrivain et le lecteur de diverger.
WORKLOG_VARS = ("PM_SESSION_WORKLOG_DIR", "KARL_AGENT_WORKLOG_DIR")
WORKLOG_SUB = "session-worklogs"
WORKLOG_LEGACY = "~/.claude/session-worklogs"
#: L'état de karl-agent (stores de spawn, jonctions, journaux). `KARL_AGENT_LOG_DIR` est le repli
#: historique : l'oublier fait viser un dossier vide (RM2391).
STATE_VARS = ("KARL_AGENT_STATE_DIR", "KARL_AGENT_LOG_DIR")
#: …et les LOGS d'instance, qui peuvent rester locaux quand l'état est partagé (RM2385).
LOG_VARS = ("KARL_AGENT_LOG_DIR",)
STATE_SUB = "karl-agent"
STATE_LEGACY = "~/.local/state/karl-agent"
#: Le registre des sessions (seq + index, RM2034) : déjà sous `var/`, mais le chemin était CALCULÉ
#: chez l'appelant. Paramétré ici (RM2992, demande du 2026-09-12 : « il y a des chances que le
#: dossier soit déplacé assez rapidement »).
SESSIONS_VARS = ("PM_SESSIONS_DIR",)
SESSIONS_SUB = "sessions"
#: Les chronos et curseurs par tour, jusqu'ici codés en dur dans trois scripts.
TURN_VARS = ("PM_TURN_STATE_DIR",)
TURN_SUB = "turns"
TURN_LEGACY = "~/.claude/logs"
#: Les transcripts claude — liste de dossiers, séparés par « : ». ÉCRITS PAR CLAUDE CODE, pas par
#: nous : on ne les déplace pas, on les lit là où ils sont (idem `history.jsonl`).
CLAUDE_STORE_VARS = ("PM_CLAUDE_STORES", "KARL_AGENT_CLAUDE_STORES")
CLAUDE_STORE_DEFAULT = "~/.claude/projects"
#: L'historique des demandes, hors périmètre du nettoyage de Claude Code (RM2997).
HISTORY_VARS = ("PM_CLAUDE_HISTORY",)
HISTORY_DEFAULT = "~/.claude/history.jsonl"

#: Les stores DÉPLAÇABLES, pour la migration (`pm-stores-migrate`) et pour les tests : ce que PM et
#: karl écrivent, par opposition à ce que Claude Code écrit. Chemin d'hier → sous-dossier d'aujourd'hui.
DEPLACABLES = ((WORKLOG_LEGACY, WORKLOG_SUB), (STATE_LEGACY, STATE_SUB), (TURN_LEGACY, TURN_SUB))

_ROOT_CACHE = {}


def _first(names, default, env=None) -> str:
    e = env if env is not None else os.environ
    for n in names:
        v = (e.get(n) or "").strip()
        if v:
            return v
    return default


def _path(names, default, env=None) -> Path:
    return Path(os.path.expanduser(_first(names, default, env)))


def state_root(env=None):
    """`var/` du repo PM, ou None si la config PM n'est pas résoluble ici (RM2992).

    L'import de `pm_paths` est PARESSEUX et mis en cache : ce module est importé par `karl-agent`
    et par des hooks qui doivent rendre la main tout de suite, et il doit rester utilisable là où
    la config PM ne se charge pas — auquel cas chaque store retombe sur son chemin d'hier, dans le
    home. Aucun appelant n'a donc à savoir si PM est chargeable : il demande son dossier."""
    e = env if env is not None else os.environ
    v = (e.get(STATE_ROOT_VAR) or "").strip()
    if v:
        return Path(os.path.expanduser(v))
    key = (e.get("PM_CORE_DIR") or "", e.get("PM_DIR") or "")
    if key not in _ROOT_CACHE:
        try:
            from pm_paths import PMConfig
            _ROOT_CACHE[key] = Path(PMConfig.load().state_dir)
        except Exception:      # noqa: BLE001 — PMConfigError (RM3119) ou conf illisible : on ne sait pas
            _ROOT_CACHE[key] = None
    return _ROOT_CACHE[key]


def _store(names, sub, legacy, env=None) -> Path:
    """Le dossier d'un store : la variable si elle est posée, sinon `var/<sub>`, sinon le chemin
    d'hier dans le home (quand la config PM ne se résout pas)."""
    v = _first(names, "", env)
    if v:
        return Path(os.path.expanduser(v))
    root = state_root(env)
    return (root / sub) if root else Path(os.path.expanduser(legacy))


def worklog_dir(env=None) -> Path:
    """Le dossier des worklogs de session. À utiliser PARTOUT — un chemin écrit à la main ici
    désarme la garde de périmètre là-bas."""
    return _store(WORKLOG_VARS, WORKLOG_SUB, WORKLOG_LEGACY, env)


def worklog_file(session_id: str, env=None) -> Path:
    return worklog_dir(env) / f"{session_id}.json"


def state_dir(env=None) -> Path:
    """L'état de karl-agent (keys/, sessions/, tasks/), avec son repli historique."""
    return _store(STATE_VARS, STATE_SUB, STATE_LEGACY, env)


def log_dir(env=None) -> Path:
    """Les LOGS d'instance de karl-agent (pipe-pane, pm-runs). `KARL_AGENT_STATE_DIR` ne les
    concerne pas (RM2385) : une instance de test partage l'ÉTAT sans mélanger ses journaux — d'où
    deux fonctions pour un même défaut, plutôt qu'une seule qu'il faudrait interpréter."""
    return _store(LOG_VARS, STATE_SUB, STATE_LEGACY, env)


def sessions_dir(env=None) -> Path:
    """Le registre des sessions (seq + index, RM2034). Sous `var/` comme les autres, et
    surchargeable comme les autres."""
    root = state_root(env)
    return _store(SESSIONS_VARS, SESSIONS_SUB, str((root or Path(".")) / SESSIONS_SUB), env)


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
    return _store(TURN_VARS, TURN_SUB, TURN_LEGACY, env)


#: Slugification du `cwd` telle que le CLI la fait (vérifiée dans le binaire, cf. RM3057) : TOUT ce
#: qui n'est ni lettre ni chiffre devient un tiret. Deux règles coexistaient — l'autre ne remplaçait
#: que `/` et `.`, si bien qu'un chemin contenant `_` produisait deux slugs différents et que la
#: reprise ne retrouvait jamais son dossier.
def cwd_slug(path) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]", "-", str(path or ""))
