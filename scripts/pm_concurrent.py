"""pm_concurrent — qui travaille DÉJÀ sur ce ticket. RM3086 (lot L3 de RM3015).

RM2818 avertissait au bouton « nouvelle session » du cockpit. Tout le reste passait sans un mot :
une session lancée depuis un terminal, un `pm-task-take`, un passage en `en_cours`. C'est pourtant
là que le conflit se paie — deux agents sur le même ticket se disputent la fiche (optimistic
locking), la branche et le statut, et on ne s'en aperçoit qu'après.

Ce module répond à la question, à partir du registre PARTAGÉ des sessions (`var/sessions`, RM2034,
étendu d'un `tickets[]` par RM3086 — D020). Il **avertit, il n'interdit pas** : reprendre un ticket
dont la session est finie est le cas normal, et c'est l'état VIVANT de l'autre session qui décide.

Stdlib seulement.
"""
from __future__ import annotations


def _live(session_id, engine="claude") -> bool:
    """Cette session tourne-t-elle encore ? Faux si on ne peut pas le savoir : mieux vaut taire un
    avertissement que d'en crier un sur une session morte — un signal qui se trompe cesse d'être lu."""
    if not session_id:
        return False
    try:
        from pm_proclive import live_session_pids
        return bool(live_session_pids(str(session_id), engine or "claude"))
    except Exception:      # noqa: BLE001
        return False


def concurrentes(rm_id, *, me=None, records=None, live=None) -> list:
    """Les AUTRES sessions vivantes qui portent ce ticket, la plus récente d'abord.

    `me` : l'id de session courante (jamais listée). `records` / `live` sont injectables — c'est ce
    qui rend la fonction testable sans registre ni processus."""
    try:
        import pm_session
    except Exception:      # noqa: BLE001
        return []
    idx = records if records is not None else pm_session.all_records()
    est_vivante = live or _live
    out = []
    for rec in pm_session.sessions_of_ticket(rm_id, idx):
        sid = rec.get("claude_session_id")
        if me and sid == me:
            continue
        if not est_vivante(sid):
            continue
        out.append({"seq": rec.get("seq"), "session_id": sid, "machine": rec.get("machine"),
                    "branches": list(rec.get("branches") or []),
                    "worktrees": list(rec.get("worktrees") or [])})
    return out


def avertissement(rm_id, sessions) -> str:
    """Le texte à afficher, ou "" s'il n'y a rien à dire. Pure — c'est elle qui est testée.

    Dit QUI, et ce qu'il faut regarder (la branche) ; propose de rejoindre plutôt que d'ouvrir.
    N'interdit rien : la phrase se termine sur le fait, pas sur une consigne d'arrêt."""
    if not sessions:
        return ""
    lignes = [f"⚠ RM{rm_id} est déjà porté par {len(sessions)} session(s) vivante(s) :"]
    for s in sessions:
        bout = f"  · session #{s['seq']}"
        if s.get("branches"):
            bout += f" — branche {s['branches'][0]}"
        if s.get("machine"):
            bout += f" ({s['machine']})"
        lignes.append(bout)
    lignes.append("  Deux sessions sur un ticket se disputent sa fiche, sa branche et son statut.")
    lignes.append("  Rejoins-la (cockpit, ou `claude --resume`) plutôt que d'en ouvrir une seconde —")
    lignes.append("  si c'est voulu (reprise, second lot), continue : rien n'est bloqué.")
    return "\n".join(lignes)
