#!/usr/bin/env python3
"""Poster une note sur un ticket Redmine (et optionnellement changer son statut).

Utilisé par les agents pour répondre à un ticket pendant le traitement d'une tâche.

Usage :
    ./scripts/redmine-post-note.py --issue 42 --note "Texte de la note"
    echo "Note multilignes" | ./scripts/redmine-post-note.py --issue 42 --note -
    ./scripts/redmine-post-note.py --issue 42 --note "Fait" --status 3   # 3 = Resolved
    ./scripts/redmine-post-note.py --issue 42 --note "Bloqué" --status 2 # 2 = In Progress

Statuts Redmine de l'instance iprospective :
    8 = A étudier / Qualifier    (NORMS a_etudier_chiffrer)
   14 = Etude en cours           (NORMS etude_chiffrage_en_cours)
   12 = A Faire                  (NORMS a_faire)
    2 = En cours                 (NORMS en_cours)
    9 = A tester/vérifier        (NORMS a_tester_verifier)
   11 = A corriger               (NORMS a_corriger)
    5 = Résolu/Fermé             (NORMS ferme + close_reason: resolu)
   10 = Abandonné                (NORMS ferme + close_reason: abandonne)
    6 = Rejeté                   (NORMS ferme + close_reason: wont_fix|hors_perimetre)
    7 = Pas un bug / Déjà existant (NORMS ferme + close_reason: invalide|doublon)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


NORMS_TO_REDMINE_STATUS = {
    "a_etudier_chiffrer": 8,
    "etude_chiffrage_en_cours": 14,
    "a_faire": 12,
    "en_cours": 2,
    "a_tester_verifier": 9,
    "a_corriger": 11,
    "ferme": 5,
    "ferme:resolu": 5,
    "ferme:abandonne": 10,
    "ferme:wont_fix": 6,
    "ferme:hors_perimetre": 6,
    "ferme:invalide": 7,
    "ferme:doublon": 7,
}


def load_env():
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue", type=int, required=True, help="ID du ticket")
    ap.add_argument("--note", required=True, help="Texte de la note (ou '-' pour lire stdin)")
    ap.add_argument("--status", type=int, help="ID Redmine du nouveau statut (optionnel)")
    ap.add_argument("--norms-status", help="Statut NORMS (a_etudier_chiffrer, en_cours, ...), "
                                            "ou 'ferme:<close_reason>'. Mappé automatiquement sur l'ID Redmine.")
    ap.add_argument("--private", action="store_true", help="Note privée (non visible client)")
    args = ap.parse_args()

    if args.norms_status:
        sid = NORMS_TO_REDMINE_STATUS.get(args.norms_status)
        if sid is None:
            print(f"ERREUR : statut NORMS '{args.norms_status}' inconnu", file=sys.stderr)
            sys.exit(1)
        args.status = sid

    load_env()
    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        print("ERREUR : $REDMINE_URL et $REDMINE_API_KEY requis (.env)", file=sys.stderr)
        sys.exit(1)

    note = sys.stdin.read() if args.note == "-" else args.note
    note = note.strip()
    if not note:
        print("ERREUR : note vide", file=sys.stderr)
        sys.exit(1)

    issue_payload = {"notes": note}
    if args.private:
        issue_payload["private_notes"] = True
    if args.status:
        issue_payload["status_id"] = args.status

    body = json.dumps({"issue": issue_payload}).encode("utf-8")
    full = f"{url.rstrip('/')}/issues/{args.issue}.json?key={key}"
    req = request.Request(full, data=body, method="PUT",
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as resp:
            resp.read()
    except error.HTTPError as e:
        print(f"ERREUR : HTTP {e.code} {e.reason}", file=sys.stderr)
        try:
            print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)

    print(f"✓ Note postée sur #{args.issue}" + (f" (statut → {args.status})" if args.status else ""))


if __name__ == "__main__":
    main()
