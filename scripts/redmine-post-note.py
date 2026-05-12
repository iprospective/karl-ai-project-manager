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
    ap.add_argument("--assign-to", help="Réattribuer à un user : <id> | 'author' (demandeur du ticket) | "
                                         "'me' (compte API). Automatique sur --norms-status=a_tester_verifier (→ author).")
    ap.add_argument("--private", action="store_true", help="Note privée (non visible client)")
    args = ap.parse_args()

    if args.norms_status:
        sid = NORMS_TO_REDMINE_STATUS.get(args.norms_status)
        if sid is None:
            print(f"ERREUR : statut NORMS '{args.norms_status}' inconnu", file=sys.stderr)
            sys.exit(1)
        args.status = sid
        # Règle NORMS : un passage en a_tester_verifier réattribue automatiquement
        # au demandeur (auteur du ticket) si aucun --assign-to explicite n'a été donné.
        if args.norms_status == "a_tester_verifier" and not args.assign_to:
            args.assign_to = "author"

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

    # Résoudre --assign-to en assigned_to_id (entier)
    if args.assign_to:
        if args.assign_to == "author":
            # Fetch l'issue pour récupérer l'auteur
            try:
                fetch_url = f"{url.rstrip('/')}/issues/{args.issue}.json?key={key}"
                with request.urlopen(request.Request(fetch_url, headers={"Accept": "application/json"}), timeout=10) as r:
                    author_id = json.loads(r.read())["issue"]["author"]["id"]
                issue_payload["assigned_to_id"] = author_id
            except Exception as e:
                print(f"ERREUR : résolution author : {e}", file=sys.stderr)
                sys.exit(1)
        elif args.assign_to == "me":
            try:
                fetch_url = f"{url.rstrip('/')}/users/current.json?key={key}"
                with request.urlopen(request.Request(fetch_url, headers={"Accept": "application/json"}), timeout=10) as r:
                    me_id = json.loads(r.read())["user"]["id"]
                issue_payload["assigned_to_id"] = me_id
            except Exception as e:
                print(f"ERREUR : résolution me : {e}", file=sys.stderr)
                sys.exit(1)
        else:
            try:
                issue_payload["assigned_to_id"] = int(args.assign_to)
            except ValueError:
                print(f"ERREUR : --assign-to attend un id entier, 'author' ou 'me' (reçu : {args.assign_to})", file=sys.stderr)
                sys.exit(1)

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

    # Vérification post-PUT : Redmine renvoie 204 même si certains attributs ont été
    # silencieusement ignorés (permissions insuffisantes). On refetch pour confirmer.
    print(f"✓ Note postée sur #{args.issue}")

    if args.status or "assigned_to_id" in issue_payload:
        try:
            check = f"{url.rstrip('/')}/issues/{args.issue}.json?key={key}"
            with request.urlopen(request.Request(check, headers={"Accept": "application/json"}), timeout=10) as r:
                actual = json.loads(r.read())["issue"]
        except Exception as e:
            print(f"⚠ Impossible de vérifier l'état post-PUT : {e}", file=sys.stderr)
            sys.exit(2)

        warned = False
        if args.status:
            actual_sid = actual["status"]["id"]
            if actual_sid == args.status:
                print(f"✓ Statut changé → {args.status}")
            else:
                print(f"⚠ Statut PAS changé (toujours {actual_sid}, demandé {args.status})", file=sys.stderr)
                warned = True
        if "assigned_to_id" in issue_payload:
            expected_aid = issue_payload["assigned_to_id"]
            actual_aid = (actual.get("assigned_to") or {}).get("id")
            if actual_aid == expected_aid:
                print(f"✓ Assigné à user id={expected_aid}")
            else:
                print(f"⚠ Assigné PAS changé (actuel={actual_aid}, demandé={expected_aid})", file=sys.stderr)
                warned = True
        if warned:
            print("  Cause probable : permission 'Edit issues' manquante pour le compte API.", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
