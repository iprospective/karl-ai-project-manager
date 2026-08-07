#!/usr/bin/env python3
"""mark-session — calcule le titre de session Claude Code préfixé d'un statut.

IMPORTANT — pourquoi ce script N'ÉCRIT PAS le titre (corrigé 2026-06-07) :
  Sur une session VIVANTE, le CLi ré-émet en continu son `custom-title` tenu
  en mémoire (réglé par le `/rename` natif) : il réécrit une entrée
  {"type":"custom-title","customTitle":"<nom mémoire>"} à chaque tour. Tout
  `append` externe au transcript est donc ÉCRASÉ au tour suivant — le CLI a
  toujours le dernier mot, et c'est ce dernier `custom-title` que lit
  `claude --resume`. (Vérifié dans le transcript : chaque [WIP]/[DONE] appendé
  était suivi d'une réécriture du titre de base par le CLI. Re-vérifié le
  2026-08-07 : le CLI réécrit la même valeur à deux tours d'intervalle sans
  action utilisateur, et le titre n'est stocké nulle part ailleurs — ni
  ~/.claude.json, ni les fichiers de session.)
  => La seule façon fiable de changer le titre d'une session vivante est la
     commande native `/rename`, qui mute l'état mémoire du CLI.

Ce script se contente donc de CALCULER le nouveau titre (à partir du titre
courant, marqueur de statut précédent retiré) et d'imprimer la commande
`/rename` prête à coller. L'agent la relaie à l'utilisateur.

L'ID de session courant est lu depuis $CLAUDE_CODE_SESSION_ID (exposé par le CLI).

DEUX TITRES DISTINCTS (RM2570, 2026-08-07) :
  - le titre de session CLI, dans le transcript JSONL (`ai-title` auto-généré,
    `custom-title` posé par `/rename`) ;
  - le titre du worklog PM, dans ~/.claude/session-worklogs/<sid>.json, posé
    par `pm-session-status.py title`.
  Les deux ne communiquent pas. Ils ont divergé le 2026-08-07 : le worklog
  était titré « RM2557 — bons plans du blog… » alors que la session CLI
  s'appelait encore « Étudier et chiffrer la tâche RM2557 Calicote », et le
  skill proposait donc un `/rename` avec l'ancien nom. Depuis, le worklog PM
  sert de repli quand la session n'a jamais été renommée à la main.

Statuts :
    done   → "[DONE] <titre>"   (terminée)
    wip    → "[WIP] <titre>"    (à finir / reprise prévue)   alias: todo, afinir
    clear  → retire le préfixe de statut

Usage :
    mark-session.py done
    mark-session.py wip
    mark-session.py clear
    mark-session.py done --title "Texte de titre imposé"
"""
import argparse
import glob
import json
import os
import re
import sys

MARKERS = ("[DONE]", "[WIP]", "[TODO]")
STATUS_PREFIX = {
    "done": "[DONE]",
    "wip": "[WIP]",
    "todo": "[WIP]",
    "afinir": "[WIP]",
    "clear": None,
}
LEADING_TAG = re.compile(r"^\[[^\]]*\]")


def find_transcript(sid: str) -> str:
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not hits:
        sys.exit(f"ERREUR : transcript introuvable pour la session {sid}.")
    return hits[0]


def transcript_titles(path: str) -> tuple[str | None, str | None]:
    """(dernier custom-title, dernier ai-title) du transcript CLI."""
    custom = ai = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if '"custom-title"' not in line and '"ai-title"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "custom-title" and obj.get("customTitle"):
                custom = obj["customTitle"]
            elif obj.get("type") == "ai-title" and obj.get("aiTitle"):
                ai = obj["aiTitle"]
    return custom, ai


def worklog_title(sid: str) -> str | None:
    """Titre du worklog PM de la session (posé par pm-session-status.py title)."""
    p = os.path.expanduser(f"~/.claude/session-worklogs/{sid}.json")
    try:
        with open(p, encoding="utf-8") as f:
            title = json.load(f).get("title")
    except (OSError, json.JSONDecodeError):
        return None
    return title.strip() if isinstance(title, str) and title.strip() else None


def current_title(path: str, sid: str) -> tuple[str | None, str]:
    """Titre courant + provenance, par ordre de priorité décroissante.

    1. custom-title — renommage explicite par l'utilisateur, fait toujours foi.
       Y compris face à un `ai-title` plus récent : le CLI ré-émet les deux à
       chaque tour, la chronologie ne départage donc rien.
    2. worklog PM   — titre posé par l'agent, plus parlant que l'auto-généré et
       reflétant ce que la session a réellement fait.
    3. ai-title     — auto-généré depuis le premier message, en dernier recours :
       il fige l'intention de départ, qui a souvent été dépassée.
    """
    custom, ai = transcript_titles(path)
    if custom is not None:
        return custom, "custom-title (renommage utilisateur)"
    wl = worklog_title(sid)
    if wl is not None:
        return wl, "worklog PM"
    return ai, "ai-title (auto-généré)"


def strip_marker(title: str | None) -> str:
    """Retire les marqueurs de STATUT en tête, en préservant tous les autres.

    Un marqueur de statut en chasse un autre — mais le numéro de ticket est une
    identité, pas un statut : il doit survivre au marquage. On parcourt donc
    TOUS les marqueurs en tête, on retire ceux de statut où qu'ils soient dans
    la série, et on conserve les autres dans leur ordre.

        "[WIP] Machin"           -> "Machin"
        "[RM1222] [WIP] Machin"  -> "[RM1222] Machin"
        "[WIP] [RM1222] Machin"  -> "[RM1222] Machin"

    (L'ancienne version s'arrêtait au premier marqueur non reconnu : un
    "[RM1222]" en tête bloquait le nettoyage du "[WIP]" qui le suivait, d'où
    des empilements "[DONE] [RM1222] [WIP] Machin".)
    """
    s = (title or "").strip()
    kept: list[str] = []
    while True:
        m = LEADING_TAG.match(s)
        if not m:
            break
        tag = m.group(0)
        s = s[len(tag):].lstrip()
        if tag.upper() not in MARKERS:
            kept.append(tag)
    return " ".join(kept + [s]).strip() if kept else s


def main() -> None:
    ap = argparse.ArgumentParser(description="Préfixe le titre de la session Claude Code.")
    ap.add_argument("status", nargs="?", default="done",
                    choices=sorted(STATUS_PREFIX.keys()),
                    help="done | wip (todo/afinir) | clear")
    ap.add_argument("--title", help="Titre de base imposé (sinon réutilise le titre courant).")
    args = ap.parse_args()

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if not sid:
        sys.exit("ERREUR : $CLAUDE_CODE_SESSION_ID absent — exécuter depuis une session Claude Code.")
    path = find_transcript(sid)

    if args.title:
        # Nettoyé comme le titre lu : un statut passé par mégarde ne s'empile pas.
        base, source = strip_marker(args.title), "--title (imposé)"
    else:
        title, source = current_title(path, sid)
        base = strip_marker(title)
    if not base:
        base, source = "(session sans titre)", "aucune source"

    prefix = STATUS_PREFIX[args.status]
    new_title = base if prefix is None else f"{prefix} {base}"

    # Provenance sur stderr : ne pollue pas la ligne à coller, mais permet de
    # voir d'où sort le titre quand il surprend.
    print(f"titre de base : {source}", file=sys.stderr)

    # On N'ÉCRIT PAS le transcript : le CLI vivant écraserait au tour suivant.
    # On imprime la commande native à coller — seule voie fiable.
    print(f"/rename {new_title}")


if __name__ == "__main__":
    main()
