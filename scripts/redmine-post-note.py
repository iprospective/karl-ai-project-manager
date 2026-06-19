#!/usr/bin/env python3
"""Poster une note sur un ticket Redmine (et optionnellement changer son statut).

Utilisé par les agents pour répondre à un ticket pendant le traitement d'une tâche.

Usage :
    ./scripts/redmine-post-note.py --issue 42 --note "Texte de la note"
    echo "Note multilignes" | ./scripts/redmine-post-note.py --issue 42 --note -
    ./scripts/redmine-post-note.py --issue 42 --note "Fait" --status 3   # 3 = Resolved
    ./scripts/redmine-post-note.py --issue 42 --note "Bloqué" --status 2 # 2 = In Progress

Statuts Redmine de l'instance iprospective (source : redmine.reference.yml) :
    8 = A étudier / Qualifier       (NORMS a_etudier_chiffrer)
   14 = Etude en cours              (NORMS etude_chiffrage_en_cours)
   12 = A Faire                     (NORMS a_faire)
    2 = En cours                    (NORMS en_cours)
   19 = A tester/vérifier dev       (NORMS a_tester_dev)
    9 = A tester/vérifier demandeur (NORMS a_tester_demandeur ; alias déprécié a_tester_verifier)
    3 = Résolu/Validé/A MEP         (NORMS a_mep — non terminal)
   20 = MEP/Tester en preprod       (NORMS en_mep)
   13 = Attente retour / en pause   (NORMS en_pause)
   11 = A corriger/finir            (NORMS a_corriger)
   18 = Fermé                       (NORMS ferme, raison portée par CF Raison Fermé id=11)

CF Raison Fermé (id=11, enumeration) valeurs :
   10 = Résolu              (NORMS close_reason: resolu)
   11 = Rejeté              (NORMS close_reason: wont_fix | hors_perimetre)
   12 = Abandonné           (NORMS close_reason: abandonne)
   13 = Déjà existant       (NORMS close_reason: doublon)
   14 = Pas un bug          (NORMS close_reason: invalide)
"""

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Statuts Redmine (instance iprospective) — table NORMS → id chargée depuis la
# source unique `redmine.reference.yml` (via redmine_utils.status_map()), qui
# inclut les variantes `ferme:<raison>` et les alias dépréciés. Un seul statut
# terminal `Fermé` (id=18), la raison est portée par le CF 'Raison Fermé' (id=11).
try:
    from redmine_utils import status_map as _status_map
    NORMS_TO_REDMINE_STATUS = _status_map()
except Exception:  # réf indisponible → fallback hardcodé (transitions critiques)
    NORMS_TO_REDMINE_STATUS = {
        "a_etudier_chiffrer": 8, "etude_chiffrage_en_cours": 14, "a_faire": 12,
        "en_cours": 2, "a_tester_dev": 19, "a_tester_demandeur": 9, "a_mep": 3,
        "en_mep": 20, "en_pause": 13, "a_corriger": 11, "ferme": 18,
        "a_tester_verifier": 9,  # alias déprécié
        "ferme:resolu": 18, "ferme:abandonne": 18, "ferme:wont_fix": 18,
        "ferme:hors_perimetre": 18, "ferme:invalide": 18, "ferme:doublon": 18,
    }

# Mapping NORMS close_reason → CF 'Raison Fermé' (id=11) value (enumeration id).
# Asymétrie : wont_fix et hors_perimetre partagent la même valeur Rejeté
# (pas de valeur dédiée 'Hors périmètre' côté CF).
CF_RAISON_FERME_ID = 11
NORMS_CLOSE_REASON_TO_CF = {
    "resolu": "10",         # Résolu
    "abandonne": "12",      # Abandonné
    "wont_fix": "11",       # Rejeté
    "hors_perimetre": "11", # Rejeté (pas de valeur dédiée)
    "invalide": "14",       # Pas un bug / rien à faire
    "doublon": "13",        # Déjà existant
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


def open_subtasks(url, key, issue_id):
    """Sous-tâches NON fermées du ticket. Redmine refuse la transition d'un parent
    vers `Fermé` tant qu'un enfant reste ouvert — cause #1 d'un changement de statut
    silencieusement ignoré (cf. NORMS status-workflow, tripwire #4)."""
    try:
        u = f"{url.rstrip('/')}/issues.json?parent_id={issue_id}&status_id=open&limit=100&key={key}"
        with request.urlopen(request.Request(u, headers={"Accept": "application/json"}), timeout=10) as r:
            data = json.loads(r.read())
        return [(i["id"], i["status"]["name"], i.get("subject", "")) for i in data.get("issues", [])]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue", type=int, required=True, help="ID du ticket")
    ap.add_argument("--note", required=True, help="Texte de la note (ou '-' pour lire stdin)")
    ap.add_argument("--status", type=int, help="ID Redmine du nouveau statut (optionnel)")
    ap.add_argument("--norms-status", help="Statut NORMS (a_etudier_chiffrer, en_cours, ...), "
                                            "ou 'ferme:<close_reason>'. Mappé automatiquement sur l'ID Redmine.")
    ap.add_argument("--assign-to", help="Réattribuer à un user : <id> | 'author' (demandeur du ticket) | "
                                         "'me' (compte API). Automatique sur --norms-status=a_tester_verifier (→ author).")
    ap.add_argument("--attach", action="append", help="Chemin d'un fichier à joindre (peut être répété)")
    ap.add_argument("--private", action="store_true", help="Note privée (non visible client)")
    args = ap.parse_args()

    cf_raison_value = None
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
        # ferme:<reason> → set aussi le CF 'Raison Fermé' (RM1742)
        if args.norms_status.startswith("ferme:"):
            reason = args.norms_status.split(":", 1)[1]
            cf_raison_value = NORMS_CLOSE_REASON_TO_CF.get(reason)
            if not cf_raison_value:
                print(f"ERREUR : close_reason '{reason}' sans mapping CF Raison Fermé", file=sys.stderr)
                sys.exit(1)

    load_env()
    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
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
    if cf_raison_value:
        issue_payload["custom_fields"] = [{"id": CF_RAISON_FERME_ID, "value": cf_raison_value}]

    # Uploads / pièces jointes
    if args.attach:
        uploads = []
        for fpath in args.attach:
            p = Path(fpath)
            if not p.is_file():
                print(f"ERREUR : fichier introuvable : {fpath}", file=sys.stderr)
                sys.exit(1)
            content_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            # Force markdown to be served as text/markdown
            if p.suffix == ".md":
                content_type = "text/markdown"
            try:
                upload_url = f"{url.rstrip('/')}/uploads.json?key={key}"
                up_req = request.Request(upload_url, data=p.read_bytes(), method="POST",
                                         headers={"Content-Type": "application/octet-stream",
                                                  "Accept": "application/json"})
                with request.urlopen(up_req, timeout=30) as r:
                    token = json.loads(r.read())["upload"]["token"]
            except error.HTTPError as e:
                print(f"ERREUR upload {p.name} : HTTP {e.code} {e.reason}", file=sys.stderr)
                try:
                    print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
                except Exception:
                    pass
                sys.exit(1)
            uploads.append({
                "token": token,
                "filename": p.name,
                "content_type": content_type,
            })
            print(f"  · upload {p.name} ({content_type}) → token={token[:12]}…")
        issue_payload["uploads"] = uploads

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

    full = f"{url.rstrip('/')}/issues/{args.issue}.json?key={key}"

    # --- Déverrouillage des transitions « assignee-only » ---
    # Certaines transitions du workflow Redmine (typiquement Etude/CDC en cours →
    # Etude/CDC à valider [14→21], et A tester demandeur) ne sont autorisées QUE
    # si le ticket est assigné au compte API courant. Or ces transitions
    # s'accompagnent justement d'une réattribution AU DEMANDEUR : si on pousse
    # statut + nouvel assigné dans le même PUT alors que le compte API n'est pas
    # (encore) l'assigné, Redmine évalue le workflow sur l'assigné AVANT update →
    # la transition est refusée *silencieusement* (PUT 204, statut inchangé).
    # Parade : s'auto-assigner d'abord (PUT préalable), ce qui débloque la
    # transition assignee-only, puis le PUT principal (statut + réattribution
    # finale au demandeur) passe. Cf. NORMS § « Transitions assignee-only ».
    if args.status:
        try:
            meta_url = f"{url.rstrip('/')}/issues/{args.issue}.json?include=allowed_statuses&key={key}"
            with request.urlopen(request.Request(meta_url, headers={"Accept": "application/json"}), timeout=10) as r:
                meta = json.loads(r.read())["issue"]
            allowed = {s["id"] for s in meta.get("allowed_statuses", [])}
            cur_assignee = (meta.get("assigned_to") or {}).get("id")
        except Exception:
            allowed, cur_assignee = None, None
        if allowed is not None and args.status not in allowed:
            try:
                cur_url = f"{url.rstrip('/')}/users/current.json?key={key}"
                with request.urlopen(request.Request(cur_url, headers={"Accept": "application/json"}), timeout=10) as r:
                    me_id = json.loads(r.read())["user"]["id"]
            except Exception:
                me_id = None
            if me_id is not None and cur_assignee != me_id:
                try:
                    pre_body = json.dumps({"issue": {"assigned_to_id": me_id}}).encode("utf-8")
                    pre_req = request.Request(full, data=pre_body, method="PUT",
                                              headers={"Content-Type": "application/json", "Accept": "application/json"})
                    with request.urlopen(pre_req, timeout=10) as r:
                        r.read()
                    print(f"  · auto-assignation préalable au compte API (id={me_id}) "
                          f"pour débloquer la transition assignee-only → statut {args.status}",
                          file=sys.stderr)
                except Exception as e:
                    print(f"  ⚠ pré-assignation pour transition assignee-only échouée : {e}", file=sys.stderr)

    body = json.dumps({"issue": issue_payload}).encode("utf-8")
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
            # Diagnostic : un parent ne se ferme pas tant qu'un enfant est ouvert.
            # On vérifie AVANT de supposer un manque de droits (cf. NORMS tripwire #4).
            subs = open_subtasks(url, key, args.issue) if args.status else []
            if subs:
                print("  Cause : sous-tâche(s) ouverte(s) — Redmine refuse de fermer le "
                      "parent tant qu'un enfant n'est pas fermé :", file=sys.stderr)
                for sid, sname, subj in subs:
                    print(f"    · #{sid} [{sname}] {subj[:70]}", file=sys.stderr)
                print("  → fermer/détacher ces sous-tâches d'abord (NORMS status-workflow).",
                      file=sys.stderr)
            else:
                print("  Cause probable : permission 'Edit issues' manquante pour le compte API.",
                      file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
