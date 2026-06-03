#!/usr/bin/env python3
"""pm-task-status-update — Change le statut d'une tâche (Redmine + MD frontmatter + log).

Usage :
    pm-task-status-update.py <RM-id> <new-status>             # statut NORMS
    pm-task-status-update.py 1670 en_cours                    # auto-assign à karl (cf. NORMS § Prise en charge)
    pm-task-status-update.py 1670 en_cours --no-assign        # désactive l'auto-assign
    pm-task-status-update.py 1670 en_cours --assign-to 5      # assigne à user 5 explicitement
    pm-task-status-update.py 1670 a_tester_dev                # test indépendant (testeur ≠ dev)
    pm-task-status-update.py 1670 a_tester_demandeur          # validation par le demandeur
    pm-task-status-update.py 1670 ferme --close-reason resolu --note "Livré dans commit abcd"

Statuts NORMS valides (source : redmine.reference.yml) :
    a_etudier_chiffrer | etude_chiffrage_en_cours | a_faire | en_cours
    a_tester_dev | a_tester_demandeur | a_mep | en_mep | en_pause | a_corriger | ferme
    (alias déprécié accepté : a_tester_verifier → a_tester_demandeur)

close_reason (si --status ferme) :
    resolu | abandonne | wont_fix | hors_perimetre | invalide | doublon

Assignation Redmine (NORMS v1.12.0 § « Prise en charge d'une tâche ») :
    Le passage à `en_cours` auto-assigne l'agent courant (karl, owner API key)
    sauf si --no-assign est passé. --assign-to <id|me|author> et --assign-to-me
    permettent de forcer une assignation explicite à tout autre statut.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

KARL_USER_ID = 79


def load_ia_manager():
    """Lit ia.default_manager de pm.config.yml (mémorisé par appel).

    Retourne dict {redmine_id, email, name}. Defaults si manquant.
    """
    cfg_path = Path(__file__).resolve().parent.parent / "pm.config.yml"
    defaults = {"redmine_id": 5, "email": "mathieu@iprospective.fr", "name": "Mathieu Moulin"}
    if not cfg_path.is_file():
        return defaults
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return defaults
    mgr = (cfg.get("ia") or {}).get("default_manager") or {}
    return {
        "redmine_id": mgr.get("redmine_id", defaults["redmine_id"]),
        "email": mgr.get("email", defaults["email"]),
        "name": mgr.get("name", defaults["name"]),
    }


IA_MANAGER = load_ia_manager()


# Statuts NORMS acceptés (canoniques + alias dépréciés) — source unique
# redmine.reference.yml via redmine_utils. Couvre le couple a_tester_dev /
# a_tester_demandeur (cf. NORMS § Synchronisation des statuts) + a_mep/en_mep/en_pause.
VALID_STATUSES = redmine_utils.valid_statuses()
VALID_CLOSE_REASONS = {"resolu", "abandonne", "wont_fix", "hors_perimetre", "invalide", "doublon"}

# Ligne de checklist Markdown non cochée dans la description.
UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[ \]\s", re.MULTILINE)


def count_unchecked(description):
    """Nombre d'items de checklist non cochés dans la description Redmine."""
    return len(UNCHECKED_RE.findall(description or ""))


FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def fetch_issue_basic(rm_id):
    """Récupère subject + author (id, name) du ticket. Retourne dict ou None."""
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        return None
    try:
        req = urllib.request.Request(
            f"{url}/issues/{rm_id}.json",
            headers={"X-Redmine-API-Key": key, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("issue")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def fetch_user_email(user_id):
    """Récupère l'email d'un user Redmine via API. None si inaccessible (droits, 404…)."""
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        return None
    try:
        req = urllib.request.Request(
            f"{url}/users/{user_id}.json",
            headers={"X-Redmine-API-Key": key, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return (json.loads(r.read()).get("user") or {}).get("mail")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def resolve_notif_target(issue):
    """Détermine (to_email, redmine_user_id, reason) pour la notif/assignation.

    Le `author` Redmine est la source de vérité du demandeur (modifié au POST
    par `pm-task-add` via PUT author_id, cf. RM1735). Le CF 'Demandeur' n'est
    plus consulté.

    Règles, par ordre de priorité :
    1. author == karl (cas légitime --initiator-agent : audit, bootstrap, ...) → Manager IA
    2. author ≠ karl avec email accessible → cet author
    3. author ≠ karl, email inaccessible → Manager IA (fallback)
    """
    issue = issue or {}
    mgr_id = IA_MANAGER["redmine_id"]
    mgr_email = IA_MANAGER["email"]
    author = issue.get("author") or {}
    author_id = author.get("id")
    author_name = author.get("name", "?")
    if author_id == KARL_USER_ID:
        return mgr_email, mgr_id, f"author=karl → Manager IA ({IA_MANAGER['name']})"
    email = fetch_user_email(author_id) if author_id else None
    if email:
        return email, author_id, f"author={author_name} <{email}>"
    return mgr_email, mgr_id, f"author={author_name} (email inaccessible) → Manager IA"


def send_status_notif(rm_id, old_status, new_status, note, issue, target=None, dry_run=False):
    """Envoie un mail via karl-mail-send.py. Échec non fatal.

    `target` peut être pré-résolu (to_email, redmine_uid, reason) pour éviter
    un double appel à resolve_notif_target ; sinon résolu ici.
    """
    if target is None:
        target = resolve_notif_target(issue)
    to_addr, _redmine_uid, reason = target
    title = (issue or {}).get("subject", "?")
    subject = f"[RM{rm_id}] {title} — {old_status} → {new_status}"
    redmine_url = os.environ.get("REDMINE_URL", "").rstrip("/")
    body_lines = [
        f"Statut du ticket RM{rm_id} mis à jour par l'agent.",
        "",
        f"Titre   : {title}",
        f"Avant   : {old_status}",
        f"Après   : {new_status}",
        "",
        "Note :",
        note.strip() or "(pas de note)",
        "",
        f"Ticket Redmine : {redmine_url}/issues/{rm_id}",
        "",
        "— Karl (notif automatique pm-task-status-update)",
    ]
    body = "\n".join(body_lines)
    print(f"  → notif mail : {reason}")
    if dry_run:
        print(f"  --dry-run : to={to_addr}, subject={subject!r}")
        return

    script = Path(__file__).resolve().parent / "karl-mail-send.py"
    cmd = [sys.executable, str(script), "--to", to_addr, "--subject", subject,
           "--body", body, "--rm-id", str(rm_id)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠ Échec notif mail (non fatal) : {r.stderr.strip()[:200]}", file=sys.stderr)
    else:
        # extraire le Message-ID de la sortie pour le log console
        mid = next((l for l in r.stdout.splitlines() if l.startswith("Mid")), "")
        print(f"  ✓ Notif mail envoyée à {to_addr}  {mid}")


def resolve_assign_value(value, issue):
    """Résout une valeur --assign-to (str) en redmine user_id (int).

    Accepte : 'me' (owner API key = karl), 'author' (demandeur du ticket),
    ou un id entier en str. Retourne None si non résolvable.
    """
    if value is None:
        return None
    if value == "me":
        return KARL_USER_ID
    if value == "author":
        return (issue or {}).get("author", {}).get("id")
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("status", help=f"Nouveau statut NORMS : {', '.join(sorted(VALID_STATUSES))}")
    ap.add_argument("--close-reason", help=f"Si statut=ferme : {', '.join(sorted(VALID_CLOSE_REASONS))}")
    ap.add_argument("--note", help="Note Redmine optionnelle (sinon : 'Statut → <new>')")
    ap.add_argument("--by", default="iprospective", help="Auteur du changement (défaut: iprospective)")
    ap.add_argument("--assign-to",
                    help="Assigner à un user Redmine : <id> | 'me' (owner API key = karl) | "
                         "'author' (demandeur du ticket). Exclusif avec --assign-to-me.")
    ap.add_argument("--assign-to-me", action="store_true",
                    help="Raccourci pour --assign-to me. Implicite si status=en_cours et "
                         "aucun --assign-to* explicite (NORMS v1.12.0 § « Prise en charge d'une tâche »).")
    ap.add_argument("--no-assign", action="store_true",
                    help="Désactive l'auto-assignation implicite sur en_cours. À utiliser uniquement "
                         "pour cas particuliers (rebascule, replanif…) — viole la règle NORMS sinon.")
    ap.add_argument("--no-mail", action="store_true",
                    help="Ne pas envoyer la notif mail (sinon : mail auto au creator, ou webmaster si creator=karl)")
    ap.add_argument("--allow-unchecked", action="store_true",
                    help="Autorise le passage en a_tester_demandeur / a_mep / ferme:resolu même si la "
                         "description contient des items de checklist non cochés (sinon bloqué — "
                         "NORMS § màj description : cocher au fil de l'eau).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.status not in VALID_STATUSES:
        sys.exit(f"ERREUR : statut invalide '{args.status}'. Valides : {sorted(VALID_STATUSES)}")
    # Normalise les alias dépréciés (a_tester_verifier → a_tester_demandeur) pour
    # que frontmatter, status_history et Redmine enregistrent la forme canonique.
    canon_status = redmine_utils.normalize_status(args.status)
    if canon_status != args.status:
        print(f"  · statut déprécié '{args.status}' normalisé → '{canon_status}'", file=sys.stderr)
        args.status = canon_status
    if args.status == "ferme" and not args.close_reason:
        sys.exit("ERREUR : --close-reason requis quand statut = ferme")
    if args.close_reason and args.close_reason not in VALID_CLOSE_REASONS:
        sys.exit(f"ERREUR : close_reason invalide. Valides : {sorted(VALID_CLOSE_REASONS)}")
    if args.assign_to and args.assign_to_me:
        sys.exit("ERREUR : --assign-to et --assign-to-me sont mutuellement exclusifs.")
    if args.assign_to_me:
        args.assign_to = "me"
    if args.assign_to and args.assign_to not in ("me", "author"):
        # Doit être un id entier
        try:
            int(args.assign_to)
        except ValueError:
            sys.exit(f"ERREUR : --assign-to attend un id entier, 'me' ou 'author' (reçu : {args.assign_to!r})")

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : fichier RM{args.rm_id}_*.md introuvable")

    # 1. Parse + update frontmatter
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    fm = yaml.safe_load(m.group(2)) or {}
    old_status = fm.get("status")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    fm["status"] = args.status
    if args.close_reason:
        fm["close_reason"] = args.close_reason
    fm["updated"] = now
    hist = fm.get("status_history") or []
    hist.append({
        "status": args.status,
        "at": now,
        "by": args.by,
        "model": None,
        "tokens": None,
        "duration_minutes": None,
    })
    fm["status_history"] = hist

    # 2. Push update Redmine via redmine-post-note.py
    norms_status = args.status
    if args.status == "ferme" and args.close_reason:
        norms_status = f"ferme:{args.close_reason}"
    note = args.note or f"Statut → {args.status}" + (f" ({args.close_reason})" if args.close_reason else "")

    # Fetch l'issue une fois (sert à la fois pour l'assignation Redmine et la
    # notif mail — éviter deux appels API).
    issue = fetch_issue_basic(args.rm_id)
    target = resolve_notif_target(issue) if issue else None

    # Garde-fou checklist (NORMS § màj description) : on ne passe pas une tâche en
    # vérification / clôture-résolue avec des items de checklist non cochés dans la
    # description. La checklist doit être tenue à jour au fil de l'eau.
    # NORMS § màj description : gate sur a_tester_demandeur, a_mep, ferme:resolu.
    gate_status = args.status in ("a_tester_demandeur", "a_mep") or (
        args.status == "ferme" and args.close_reason == "resolu")
    if gate_status and issue and not args.allow_unchecked:
        n_unchecked = count_unchecked(issue.get("description"))
        if n_unchecked:
            sys.exit(
                f"ERREUR : {n_unchecked} item(s) de checklist non coché(s) dans la description de "
                f"RM{args.rm_id}, refus de passer en '{args.status}'.\n"
                f"  → Coche les items terminés : pm-task-description-update.py {args.rm_id} --check <n,...>\n"
                f"  → Ou, si c'est volontaire (items hors périmètre, abandonnés…) : relance avec --allow-unchecked."
            )

    # Résolution de l'assignation Redmine.
    #
    # Priorité (du plus explicite au plus implicite) :
    #   1. --assign-to <value> (explicite, peut être 'me' / 'author' / id)
    #   2. status=en_cours sans flag explicite → 'me' par défaut
    #      (NORMS v1.12.0 § « Prise en charge d'une tâche » — auto-assignation
    #      indissociable de en_cours). --no-assign pour outrepasser.
    #   3. status=a_tester_demandeur ou a_mep → override vers Manager IA / author
    #      (NORMS § « Règle d'attribution Redmine », RM1734).
    #      a_tester_dev / en_mep / a_corriger → pas de défaut (testeur ≠ dev,
    #      testeur preprod humain, worker précédent) : attribution manuelle via
    #      --assign-to tant que l'orchestrateur n'est pas en place.
    #      en_pause / ferme → conserver l'attribution courante.
    #
    # `assign_override_value` est la valeur passée à redmine-post-note --assign-to
    # (peut être 'me' / 'author' / '<id>'). `assigned_to_id` est l'int résolu
    # pour la frontmatter MD.
    assign_override_value = None
    if args.assign_to:
        assign_override_value = args.assign_to
    elif args.status == "en_cours" and not args.no_assign:
        assign_override_value = "me"
        print("  · auto-assign à l'agent courant (NORMS v1.12.0 § « Prise en charge "
              "d'une tâche »). Utilise --no-assign pour outrepasser.", file=sys.stderr)
    elif args.status in ("a_tester_demandeur", "a_mep") and target:
        # NORMS : a_tester_demandeur → demandeur (author) ; author==karl → Manager IA.
        #         a_mep → responsable MEP/intégration (par défaut Manager IA).
        # On rend l'assignation explicite ici pour que MD frontmatter `assigned_to`
        # reflète la réalité Redmine.
        _, target_uid, _ = target
        author_id = (issue or {}).get("author", {}).get("id")
        if args.status == "a_mep":
            assign_override_value = str(IA_MANAGER["redmine_id"])
        elif target_uid and target_uid != author_id:
            assign_override_value = str(target_uid)
        elif author_id:
            assign_override_value = "author"

    assigned_to_id = resolve_assign_value(assign_override_value, issue)
    if assigned_to_id is not None:
        fm["assigned_to"] = assigned_to_id

    new_fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    new_content = f"{m.group(1)}{new_fm_yaml.rstrip()}{m.group(3)}{m.group(4)}"

    if args.dry_run:
        print(f"--dry-run : changerait {old_status} → {args.status}")
        print(f"--dry-run : Redmine note = {note!r}, norms-status = {norms_status}")
        if assign_override_value:
            print(f"--dry-run : assignation Redmine forcée → user_id={assign_override_value}")
        if not args.no_mail and issue:
            send_status_notif(args.rm_id, old_status, args.status, note, issue, target=target, dry_run=True)
        return

    cmd = [sys.executable, str(Path(__file__).parent / "redmine-post-note.py"),
           "--issue", str(args.rm_id), "--note", note, "--norms-status", norms_status]
    if assign_override_value:
        cmd.extend(["--assign-to", str(assign_override_value)])
    env = os.environ.copy()
    main = env.get("REDMINE_USER_MAIN_API_KEY")
    if main:
        env["REDMINE_API_KEY"] = main
    r = subprocess.run(cmd, env=env, check=False)
    if r.returncode != 0:
        sys.exit(f"ERREUR redmine-post-note (exit {r.returncode})")

    # 3. Write MD
    md_path.write_text(new_content, encoding="utf-8")
    print(f"✓ MD synchronisé : {md_path.relative_to(cfg.projects_root)}")

    # 4. Append log
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    entry_lines = [
        f"\n## {now} — Statut : {old_status} → {args.status}",
        "Tokens : 0 | Durée : 0 min",
        "",
    ]
    if assigned_to_id is not None:
        entry_lines.append(f"Assigné à user_id={assigned_to_id} (via --assign-to "
                           f"{assign_override_value!r}).")
    entry_lines.extend(["", note, ""])
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry_lines))
    print(f"✓ Log appendé : {log_path.name}")

    # 5. Notif mail au demandeur (résolu via resolve_notif_target ; Manager IA
    # par défaut si author=karl ou email inaccessible).
    if not args.no_mail:
        if issue is None:
            print("  ⚠ Impossible de fetcher le ticket Redmine pour la notif mail (skip)", file=sys.stderr)
        else:
            send_status_notif(args.rm_id, old_status, args.status, note, issue, target=target)

    # 6. Prise de ticket (→ en_cours) : pousse l'estimation vers Redmine si elle
    # ne l'a jamais été (NORMS § ROI « estimer à la prise de ticket si manquante »).
    if args.status == "en_cours" and not (fm.get("metrics") or {}).get("estimate_pushed_at"):
        est = fm.get("estimate") or {}
        if any(est.get(k) is not None for k in ("tokens", "ai_time_minutes", "human_time_minutes", "estimated_model")):
            r2 = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "pm-task-metrics-push.py"),
                 "--rm-id", str(args.rm_id), "--estimate"], check=False)
            if r2.returncode != 0:
                print(f"  ⚠ push estimation à la prise échoué (exit {r2.returncode})", file=sys.stderr)


if __name__ == "__main__":
    main()
