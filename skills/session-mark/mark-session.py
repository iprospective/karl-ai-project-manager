#!/usr/bin/env python3
"""mark-session — calcule le titre de session Claude Code préfixé d'un statut.

IMPORTANT — pourquoi ce script N'ÉCRIT PAS le titre (corrigé 2026-06-07) :
  Sur une session VIVANTE, le CLi ré-émet en continu son `custom-title` tenu
  en mémoire (réglé par le `/rename` natif) : il réécrit une entrée
  {"type":"custom-title","customTitle":"<nom mémoire>"} à chaque tour. Tout
  `append` externe au transcript est donc ÉCRASÉ au tour suivant — le CLI a
  toujours le dernier mot, et c'est ce dernier `custom-title` que lit
  `claude --resume`. (Vérifié dans le transcript : chaque [WIP]/[DONE] appendé
  était suivi d'une réécriture du titre de base par le CLI.)
  => La seule façon fiable de changer le titre d'une session vivante est la
     commande native `/rename`, qui mute l'état mémoire du CLI.

Ce script se contente donc de CALCULER le nouveau titre (à partir du titre
courant lu dans le transcript, marqueur précédent retiré) et d'imprimer la
commande `/rename` prête à coller. L'agent la relaie à l'utilisateur.

L'ID de session courant est lu depuis $CLAUDE_CODE_SESSION_ID (exposé par le CLI).

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
import sys

MARKERS = ("[DONE]", "[WIP]", "[TODO]")
STATUS_PREFIX = {
    "done": "[DONE]",
    "wip": "[WIP]",
    "todo": "[WIP]",
    "afinir": "[WIP]",
    "clear": None,
}


def find_transcript(sid: str) -> str:
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not hits:
        sys.exit(f"ERREUR : transcript introuvable pour la session {sid}.")
    return hits[0]


def current_title(path: str) -> str | None:
    """Titre courant : dernier custom-title si présent, sinon dernier ai-title."""
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
    return custom if custom is not None else ai


def strip_marker(title: str | None) -> str:
    """Enlève les préfixes de statut existants pour récupérer le titre de base."""
    s = (title or "").strip()
    changed = True
    while changed:
        changed = False
        for m in MARKERS:
            if s.upper().startswith(m):
                s = s[len(m):].strip()
                changed = True
    return s


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

    base = args.title.strip() if args.title else strip_marker(current_title(path))
    if not base:
        base = "(session sans titre)"

    prefix = STATUS_PREFIX[args.status]
    new_title = base if prefix is None else f"{prefix} {base}"

    # On N'ÉCRIT PAS le transcript : le CLI vivant écraserait au tour suivant.
    # On imprime la commande native à coller — seule voie fiable.
    print(f"/rename {new_title}")


if __name__ == "__main__":
    main()
