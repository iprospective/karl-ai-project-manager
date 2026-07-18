#!/usr/bin/env python3
"""pm-task-status-update — Change le statut d'une tâche (Redmine + MD frontmatter + log).

Usage :
    pm-task-status-update.py <RM-id> <new-status>             # statut NORMS
    pm-task-status-update.py 1670 en_cours                    # auto-assign à karl (cf. NORMS § Prise en charge)
    pm-task-status-update.py 1670 en_cours --no-assign        # désactive l'auto-assign
    pm-task-status-update.py 1670 en_cours --assign-to 5      # assigne à user 5 explicitement
    pm-task-status-update.py 1670 etude_chiffrage_a_valider   # étude/CDC finie → validation par le demandeur
    pm-task-status-update.py 1670 a_tester_dev                # test indépendant (testeur ≠ dev)
    pm-task-status-update.py 1670 a_tester_demandeur          # validation par le demandeur
    pm-task-status-update.py 1670 ferme --close-reason resolu --note "Livré dans commit abcd"

Statuts NORMS valides (source : redmine.reference.yml) :
    a_etudier_chiffrer | etude_chiffrage_en_cours | etude_chiffrage_a_valider | a_faire | en_cours
    a_tester_dev | a_tester_demandeur | a_mep | en_mep | en_pause | a_corriger | ferme
    (alias déprécié accepté : a_tester_verifier → a_tester_demandeur)

Réattribution au demandeur (author ; author==karl → Manager IA) :
    etude_chiffrage_a_valider et a_tester_demandeur soumettent le ticket au demandeur.

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
import pm_git
import pm_scope
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


def email_notifs_enabled():
    """Lit notifications.email_enabled de pm.config.yml (défaut False).

    Interrupteur global des notifs mail — distinct du --no-mail par appel.
    """
    root = Path(__file__).resolve().parent.parent
    val = False
    # pm.config.local.yml surcharge pm.config.yml (NORMS structure-reference) —
    # permet le réglage via le cockpit (RM2213) sans toucher au fichier commenté.
    for name in ("pm.config.yml", "pm.config.local.yml"):
        try:
            cfg = yaml.safe_load((root / name).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        notif = cfg.get("notifications") or {}
        if "email_enabled" in notif:
            val = bool(notif["email_enabled"])
    return val


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


def env_session_hook(md_path, rm_id, new_status, old_status):
    """Hooks D1/D2 env de session (RM1834/RM1947) — best-effort, JAMAIS bloquant.

    en_cours → crée l'env de session `envs/<repo>-rm<id>` (pm-env-session create) ;
    ferme    → teardown (vhost/logs/clone BDD ; branche et BDD partagée conservées).

    Ne s'applique qu'aux workspaces au layout RM1993 : tâche co-localisée
    (`<ws>/.mmi-pm/tasks/…`) + manifeste `repos:` + bare présent. Mono-repo
    seulement (multi-repo = ambigu → pm-env-session --repo à la main).
    Opt-out global : pm.config.yml :: env_runtime.auto_session: false.
    """
    try:
        cfg_path = Path(__file__).resolve().parent.parent / "pm.config.yml"
        env_cfg = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get(
            "env_runtime") or {}
        if not env_cfg.get("auto_session", True):
            return
        # workspace = parent du .mmi-pm contenant la tâche (co-location RM1949)
        real = md_path.resolve()
        ws = next((d.parent for d in real.parents if d.name == ".mmi-pm"), None)
        if ws is None:
            return
        repos = (yaml.safe_load((ws / ".mmi-pm" / "meta.yml").read_text(
            encoding="utf-8")) or {}).get("repos") or []
        if not repos:
            return
        if len(repos) > 1:
            print(f"  · env de session non auto ({len(repos)} repos au manifeste) : "
                  f"pm-env-session.py create {rm_id} --repo <name>", file=sys.stderr)
            return
        name = repos[0].get("name")
        if not name or not (ws / "repos" / f"{name}.git").is_dir():
            return
        if new_status == "en_cours":
            verb = "create"
        elif new_status == "ferme" and (ws / "envs" / f"{name}-rm{rm_id}").is_dir():
            verb = "teardown"
        else:
            return
        tool = Path(__file__).resolve().parent / "pm-env-session.py"
        # En TTY, passthrough : pm-env-session pose la question du clone BDD
        # (défaut projet db_clone_default) directement à l'utilisateur.
        tty = sys.stdin.isatty() and sys.stderr.isatty()
        r = subprocess.run([sys.executable, str(tool), verb, str(rm_id), str(ws)],
                           capture_output=not tty, text=True, timeout=600)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            last = out.splitlines()[-1] if out else f"✓ {verb} ok"
            print(f"  · env de session ({verb}) : {last}")
        else:
            # teardown refusé (worktree sale) ou runtime KO : on n'empêche JAMAIS
            # la transition de statut — l'env se gère à la main.
            print(f"  ⚠ env de session ({verb}) non appliqué (non bloquant) :\n"
                  + "\n".join(f"    {ln}" for ln in out.splitlines()[-4:]),
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — hook best-effort
        print(f"  ⚠ hook env de session en échec (non bloquant) : {e}", file=sys.stderr)


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
    if not email_notifs_enabled():
        print("  → notif mail désactivée (pm.config.yml : notifications.email_enabled=false)")
        return
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


# ── Transitions NORMS (source : module status-workflow, § « Transitions valides ») ──
# {statut courant: [(cible, condition), ...]}. S'ajoutent les règles génériques :
# tout état actif → en_pause ; tout état → ferme (close_reason requis) ;
# en_pause → reprise à l'état précédent (lu dans status_history).
NORMS_TRANSITIONS = {
    "nouveau": [
        ("a_etudier_chiffrer", "tri : besoin d'étude/chiffrage"),
        ("a_faire", "tri : prêt à coder tel quel"),
        ("en_cours", "tri : prise immédiate (auto-assignation)"),
    ],
    "a_etudier_chiffrer": [
        ("etude_chiffrage_en_cours", "assigned_to renseigné"),
    ],
    "etude_chiffrage_en_cours": [
        ("etude_chiffrage_a_valider", "CDC + estimate.* complets → soumis au demandeur"),
    ],
    "etude_chiffrage_a_valider": [
        ("a_faire", "validé par le demandeur → prêt à coder"),
        ("etude_chiffrage_en_cours", "retour demandeur (ajustements)"),
    ],
    "a_faire": [
        ("en_cours", "création branche <RMid>-<desc> + CF GIT Branche (pm-branch-start)"),
    ],
    "en_cours": [
        ("a_tester_dev", "dev terminé + requires_agent_test résolu à 'oui'"),
        ("a_tester_demandeur", "dev terminé + requires_agent_test résolu à 'non' (bypass)"),
        ("a_etudier_chiffrer", "périmètre modifié"),
    ],
    "a_tester_dev": [
        ("a_tester_demandeur", "test dev OK"),
        ("a_corriger", "problèmes (note dans journal)"),
    ],
    "a_tester_demandeur": [
        ("a_mep", "validé : MR branche→integration_branch (CF GIT PR) puis mergée"),
        ("a_corriger", "rejet (note dans journal)"),
        ("ferme", "ticket sans code à déployer — close_reason: resolu"),
    ],
    "a_mep": [
        ("en_mep", "integration_branch déployée en preprod"),
    ],
    "en_mep": [
        ("ferme", "tests preprod OK + merge → prod_branch + pull prod — close_reason: resolu"),
        ("a_corriger", "régression preprod (note dans journal)"),
    ],
    "a_corriger": [
        ("en_cours", "reprise du dev"),
    ],
    # RM2285 : réouverture d'un ticket fermé — retour au backlog uniquement
    # (a_faire), note motivée obligatoire, close_reason purgé ; status_history
    # conserve le cycle précédent (append-only).
    "ferme": [
        ("a_faire", "réouverture : note obligatoire motivant la réouverture ; close_reason purgé"),
    ],
}
INACTIVE_STATUSES = {"ferme", "en_pause"}


def list_next(rm_id):
    """Affiche les transitions NORMS valides depuis le statut courant du ticket
    (+ marque celles que le compte API peut réellement poser côté Redmine)."""
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        sys.exit(f"ERREUR : fichier RM{rm_id}_*.md introuvable")
    m = FRONTMATTER_RE.match(md_path.read_text(encoding="utf-8"))
    fm = yaml.safe_load(m.group(2)) or {} if m else {}
    cur = redmine_utils.normalize_status(fm.get("status") or "?")

    # Transitions spécifiques + génériques
    nexts = list(NORMS_TRANSITIONS.get(cur, []))
    if cur == "en_pause":
        hist = [h.get("status") for h in (fm.get("status_history") or [])
                if h.get("status") and h.get("status") != "en_pause"]
        prev = redmine_utils.normalize_status(hist[-1]) if hist else None
        if prev:
            nexts.append((prev, "reprise à l'état précédent (déblocage)"))
    if cur not in INACTIVE_STATUSES:
        nexts.append(("en_pause", "blocage tiers"))
    if cur != "ferme":
        nexts.append(("ferme", "close_reason requis (--close-reason)"))

    # Côté Redmine : statuts réellement posables par CE compte API sur CE ticket.
    allowed_ids = None
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if url and key:
        try:
            req = urllib.request.Request(
                f"{url}/issues/{rm_id}.json?include=allowed_statuses",
                headers={"X-Redmine-API-Key": key, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                iss = json.loads(r.read()).get("issue") or {}
            allowed_ids = {s["id"] for s in iss.get("allowed_statuses") or []} or None
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            allowed_ids = None
    sids = redmine_utils.status_ids()

    print(f"RM{rm_id} — statut courant : {cur}")
    print("Transitions NORMS valides :")
    for tgt, cond in nexts:
        mark = ""
        if allowed_ids is not None:
            ok = sids.get(tgt) in allowed_ids
            mark = "  [Redmine OK]" if ok else "  [Redmine REFUSERA pour ce compte]"
        print(f"  → {tgt:<26} {cond}{mark}")
    if allowed_ids is None:
        print("  (vérification live Redmine indisponible — transitions NORMS seules)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("status", nargs="?",
                    help=f"Nouveau statut NORMS : {', '.join(sorted(VALID_STATUSES))} "
                         f"(omis si --list-next)")
    ap.add_argument("--list-next", action="store_true",
                    help="Liste les transitions NORMS valides depuis le statut courant "
                         "(+ celles que le compte API peut réellement poser côté Redmine)")
    ap.add_argument("--close-reason", help=f"Si statut=ferme : {', '.join(sorted(VALID_CLOSE_REASONS))}")
    ap.add_argument("--note", help="Note Redmine optionnelle (sinon : 'Statut → <new>')")
    ap.add_argument("--cross-project", action="store_true", help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
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
    ap.add_argument("--no-commit", action="store_true",
                    help="Pas d'auto-commit git des fichiers écrits (RM1834)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.list_next:
        list_next(args.rm_id)
        return
    if not args.status:
        sys.exit("ERREUR : statut requis (ou --list-next pour voir les transitions valides)")

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
    pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-status-update")

    # report-on-close (RM2035) : à la clôture, pousser la conso (time_entries + CF17)
    # MAINTENANT, tant que le ticket est ouvert/trouvable — le batch `--all` ignore les
    # fermés (cas vécu RM1963). Lancé AVANT la lecture du MD ci-dessous pour que le ledger
    # écrit par le report soit relu et préservé. --no-commit : l'auto-commit de ce script
    # (plus bas) emporte le ledger. Best-effort : un échec ne bloque pas la clôture.
    if args.status == "ferme":
        rep = Path(__file__).resolve().parent / "pm-task-report.py"
        try:
            r = subprocess.run([sys.executable, str(rep), "--rm-id", str(args.rm_id),
                                "--apply", "--no-commit"],
                               capture_output=True, text=True, timeout=120)
            lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
            print("  · report-on-close : " + (lines[-1].strip() if lines else "(rien à pousser)"))
        except Exception as e:
            print(f"  ⚠ report-on-close échoué (non bloquant) : {e}", file=sys.stderr)

    # 1. Parse + update frontmatter
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    fm = yaml.safe_load(m.group(2)) or {}
    old_status = fm.get("status")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    # RM2285 : réouverture d'un ticket fermé — uniquement vers a_faire (retour
    # backlog, la reprise suit le flow normal), note motivée obligatoire,
    # close_reason purgé. status_history conserve le cycle précédent.
    reopening = (old_status == "ferme" and args.status != "ferme")
    if reopening:
        if args.status != "a_faire":
            sys.exit("ERREUR : réouverture d'un ticket fermé uniquement vers 'a_faire' "
                     "(NORMS § Transitions valides — la reprise suit ensuite le flow normal)")
        if not args.note:
            sys.exit("ERREUR : --note obligatoire pour rouvrir un ticket fermé "
                     "(motiver la réouverture)")
        print("  · réouverture : close_reason purgé, cycle précédent conservé dans status_history")

    fm["status"] = args.status
    if args.close_reason:
        fm["close_reason"] = args.close_reason
    elif reopening:
        fm["close_reason"] = None
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
    # `--note -` = stdin, résolu ICI (RM2229) : avant, le tiret littéral
    # partait au log local (seul redmine-post-note, qui hérite de stdin,
    # lisait le contenu) → les notes de livraison étaient absentes du
    # `.log.md`, donc invisibles de la fiche cockpit (protocole de test).
    if args.note == "-":
        args.note = sys.stdin.read().strip()
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
    # Protocole de test (RM2229) — WARNING non bloquant : une livraison en
    # vérification sans protocole rédigé (frontmatter test_protocol, miroir du
    # CF « Protocole de test ») prive le testeur du « quoi tester ». Rédaction
    # au fil de l'eau : pm-task-protocol.py <id> --set/--append.
    if gate_status:
        try:
            _fm_now = yaml.safe_load(FRONTMATTER_RE.match(
                md_path.read_text(encoding="utf-8")).group(2)) or {}
            if str(_fm_now.get("test_protocol") or "").strip() in ("", "None"):
                print(f"  ⚠ pas de protocole de test sur RM{args.rm_id} — le testeur n'a "
                      f"pas de « quoi tester ».\n"
                      f"    → pm-task-protocol.py {args.rm_id} --set -   (ou --append -)",
                      file=sys.stderr)
        except Exception:  # noqa: BLE001 — garde-fou informatif, jamais bloquant
            pass

    # Résolution de l'assignation Redmine.
    #
    # Priorité (du plus explicite au plus implicite) :
    #   1. --assign-to <value> (explicite, peut être 'me' / 'author' / id)
    #   2. status=en_cours sans flag explicite → 'me' par défaut
    #      (NORMS v1.12.0 § « Prise en charge d'une tâche » — auto-assignation
    #      indissociable de en_cours). --no-assign pour outrepasser.
    #   3. status=a_tester_demandeur / etude_chiffrage_a_valider / a_mep → override
    #      vers demandeur (author) / Manager IA (NORMS § « Règle d'attribution Redmine », RM1734).
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
    elif args.status in ("a_tester_demandeur", "etude_chiffrage_a_valider", "a_mep") and target:
        # NORMS : a_tester_demandeur          → demandeur (author) ; author==karl → Manager IA.
        #         etude_chiffrage_a_valider   → demandeur (author) : l'étude/CDC + chiffrage
        #                                       finis sont soumis à validation (même résolveur).
        #         a_mep                       → responsable MEP/intégration (par défaut Manager IA).
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

    # 6bis. Hooks D1/D2 env de session (RM1834/RM1947) : en_cours → create,
    # ferme → teardown. Best-effort, jamais bloquant.
    if args.status in ("en_cours", "ferme") and old_status != args.status:
        env_session_hook(md_path, args.rm_id, args.status, old_status)

    # 7. Worklog de session (best-effort, no-op hors session Claude Code) : reflète
    # la transition pour que « il reste quoi à faire dans cette session » reste fidèle.
    # Upsert : crée l'item si le ticket n'avait pas été ouvert dans cette session. Cf RM1875.
    if not args.dry_run:
        import pm_session_hook
        try:
            proj = md_path.relative_to(cfg.projects_root).parts[3]
        except (ValueError, IndexError):
            proj = None
        pm_session_hook.log_to_session(
            f"RM{args.rm_id}", label=fm.get("title"),
            status=args.status, project=proj)

    # 8. Auto-commit atomique des fichiers écrits (RM1834 piste A). Placé en
    # dernier : capture aussi l'écriture frontmatter du push d'estimation (étape 6).
    if not args.dry_run and not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(status): RM{args.rm_id} {old_status} -> {args.status}")


if __name__ == "__main__":
    main()
