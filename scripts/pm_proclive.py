"""pm_proclive — « une session d'agent tourne-t-elle encore sur ce sid ? ». RM2810.

Source UNIQUE de la garde « session vivante », partagée par `karl-move-session.py`
et `karl-agent.py` (`_session_live`). Deux copies donneraient deux verdicts sur la
seule question qui compte avant de déplacer une session : peut-on y toucher ?

L'implémentation précédente était fausse dans les deux sens.

**Faux négatif — le cas dangereux.** Elle exigeait `--resume` sur la ligne de
commande. Or une session NEUVE tourne sous `claude --session-id <sid>`, sans
`--resume` : la garde ne la voyait pas et laissait déplacer une session en cours
d'écriture, ce qui la scinde (l'historique part dans le projet cible, la suite est
recréée à l'ancien emplacement). C'était exactement la situation à empêcher.

**Faux positif — le cas rencontré.** Elle testait `sid in ligne` sur toute sortie
de `pgrep -af claude`, sans vérifier que le process était bien un `claude`. Une
commande shell citant le sid suffisait à la déclencher — y compris celle lancée
pour diagnostiquer, ou l'appel au script lui-même.

D'où les deux règles ici : on ne regarde **pas** les drapeaux, et on n'accepte que
les process dont l'exécutable est l'agent.

Le ticket suggérait d'exclure en plus son propre PID et ses ancêtres. C'est une
piste écrite pour l'ancien matcher, et elle est nuisible ici : le filtre sur
l'exécutable suffit à écarter le shell appelant, tandis que l'exclusion des
ancêtres masquerait le `claude` qui a lancé le script — c'est-à-dire le cas où l'on
tente de déplacer SA PROPRE session vivante, le plus dangereux de tous. Vérifié :
sans exclusion, la session courante est bien vue comme vivante, et les lignes
`/bin/bash -c …` citant le sid restent écartées.

Stdlib seulement — `karl-agent.py` est un serveur sans dépendances.
"""
import os
from pathlib import Path

PROC = Path("/proc")


def _argv(pid: int):
    try:
        raw = (PROC / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]


def _is_engine(argv, engine: str) -> bool:
    """L'exécutable est-il l'agent lui-même ?

    On accepte `claude …` et `node /chemin/claude …` : le CLI est un script node,
    et selon la façon dont il a été lancé l'interpréteur peut occuper argv[0].
    On s'arrête à argv[1] — au-delà, `engine` n'est plus l'exécutable mais un
    argument, et on retomberait dans le faux positif que ce module corrige.
    """
    if not argv:
        return False
    if os.path.basename(argv[0]) == engine:
        return True
    if len(argv) > 1 and os.path.basename(argv[0]) in ("node", "nodejs", "bun", "deno"):
        return os.path.basename(argv[1]) == engine
    return False


def live_session_pids(session_id: str, engine: str = "claude") -> list:
    """PIDs des process `engine` portant ce sid dans leurs arguments.

    Aucun filtrage sur les drapeaux : `--resume`, `--session-id` ou rien du tout,
    une session vivante est une session vivante. Aucune exclusion de PID non plus :
    voir l'en-tête du module.
    """
    if not session_id:
        return []

    found = []
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        argv = _argv(pid)
        if not _is_engine(argv, engine):
            continue
        if any(session_id in arg for arg in argv[1:]):
            found.append(pid)
    return sorted(found)


def session_is_live(session_id: str, engine: str = "claude") -> bool:
    return bool(live_session_pids(session_id, engine))
