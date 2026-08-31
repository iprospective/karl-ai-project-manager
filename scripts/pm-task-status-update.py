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
    pm-task-status-update.py 1670 --list-next            # transitions valides (texte)
    pm-task-status-update.py 1670 --list-next --json     # idem, sortie machine (cockpit, RM2888)

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
from pm_output import out
import pm_reporting
import pm_git
import pm_scope
import redmine_utils
from pm_lock import ticket_lock, atomic_write  # verrou par ticket + écriture atomique (T7/RM2551)

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
    """Items de checklist RÉELS et non cochés (RM2789).

    Passe par `pm_markdown` plutôt que par un `findall` à l'aveugle : une description qui
    CITE une checklist en exemple, dans un bloc de code, comptait des cases fantômes
    (c'est déjà la raison d'être de RM2540). Et les gabarits « (à compléter) » ne sont pas
    des critères — les compter bloquait la livraison sans recours proportionné.
    """
    from pm_markdown import real_checklist_lines
    return sum(1 for _, m in real_checklist_lines(description or "")
               if m.group(2).strip() == "")


def has_criteria(description):
    """La description définit-elle au moins un critère RÉEL ? (gabarits exclus)"""
    from pm_markdown import real_checklist_lines
    return bool(real_checklist_lines(description or ""))


CHECKED_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]", re.M)


def count_checked(description):
    """Nombre d'items de checklist cochés dans la description Redmine."""
    return len(CHECKED_RE.findall(description or ""))


def count_placeholders(description):
    """Nombre de GABARITS de critère (« (à compléter) », « à définir », « TBD »)."""
    from pm_markdown import placeholder_lines
    return len(placeholder_lines(description or ""))


def placeholder_gate(rm_id, description, quoi):
    """Message de refus quand un gabarit de critère traîne encore (RM2789).

    Volontairement NON contournable par `--allow-unchecked` : ce drapeau existe pour des
    critères réels qu'on assume de ne pas cocher (hors périmètre, abandonnés). Un gabarit,
    lui, n'est pas un critère — le laisser passer, c'est livrer un ticket dont personne ne
    saura jamais ce qu'il devait satisfaire. Deux issues, toutes deux explicites.
    """
    return (
        f"ERREUR : RM{rm_id} porte encore un gabarit de critère « à compléter », "
        f"refus de {quoi}.\n"
        f"  Deux issues, au choix — et il en FAUT une :\n"
        f"  → écrire les vrais critères : "
        f"pm-task-description-update.py {rm_id} --set-from-file <fichier>\n"
        f"  → assumer qu'il n'y en a pas : "
        f"pm-task-description-update.py {rm_id} --drop-placeholders\n"
        f"  (--allow-unchecked ne s'applique PAS ici : il est fait pour de vrais critères "
        f"qu'on renonce à cocher, pas pour un gabarit que personne ne peut cocher.)"
    )


FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def _git_out(repo, *args, timeout=20):
    """git dans <repo>, stdout strippé ('' si erreur) — jamais d'exception."""
    try:
        r = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — garde best-effort
        return ""


def unmerged_ticket_branches(md_path, rm_id):
    """RM2319 : branches du ticket non mergées dans la branche d'intégration.

    Cherche par PRÉFIXE `<rm_id>-` (locales + distantes) dans le repo du
    workspace co-localisé — le frontmatter git.branch peut être tronqué/périmé
    (cas RM2238). Retourne (repo, integration, [branches non mergées]) ou None
    si rien à vérifier (pas de workspace/repo résoluble, aucune branche).
    Best-effort : toute résolution impossible ⇒ None (on ne bloque jamais sur
    un problème d'infra), le réseau n'est pas requis (fetch tenté, non exigé).
    """
    try:
        real = md_path.resolve()
        ws = next((d.parent for d in real.parents if d.name == ".mmi-pm"), None)
        if ws is None:
            return None
        repos = (yaml.safe_load((ws / ".mmi-pm" / "meta.yml").read_text(
            encoding="utf-8")) or {}).get("repos") or []
        if len(repos) != 1:   # multi-repo : ambigu → hors garde (comme le hook env)
            return None
        integration = repos[0].get("integration_branch") or "dev"
        bare = ws / "repos" / f"{repos[0].get('name')}.git"
        repo = bare if bare.is_dir() else (ws if (ws / ".git").exists() else None)
        if repo is None:
            return None
        # refs fraîches si le réseau le permet (silencieux sinon)
        _git_out(repo, "fetch", "origin", "--prune", timeout=25)
        refs = _git_out(repo, "for-each-ref", "--format=%(refname:short)",
                        f"refs/heads/{rm_id}-*", f"refs/remotes/origin/{rm_id}-*")
        branches = [r for r in refs.splitlines() if r.strip()]
        if not branches:
            return None
        target = (f"origin/{integration}"
                  if _git_out(repo, "rev-parse", "--verify", "--quiet",
                              f"refs/remotes/origin/{integration}") else integration)
        unmerged = []
        for br in branches:
            ok = subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", br, target],
                capture_output=True, timeout=20).returncode == 0
            if not ok:
                unmerged.append(br)
        # une même branche vue en local ET en origin/ : dédoublonner par nom court
        seen, uniq = set(), []
        for br in unmerged:
            short = br.removeprefix("origin/")
            if short not in seen:
                seen.add(short)
                uniq.append(br)
        return (repo, integration, uniq) if uniq else None
    except Exception:  # noqa: BLE001 — garde best-effort
        return None


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
            return          # opt-out global assumé : silence voulu, pas une panne
        # workspace = parent du .mmi-pm contenant la tâche (co-location RM1949)
        real = md_path.resolve()
        ws = next((d.parent for d in real.parents if d.name == ".mmi-pm"), None)
        if ws is None:
            return
        repos = (yaml.safe_load((ws / ".mmi-pm" / "meta.yml").read_text(
            encoding="utf-8")) or {}).get("repos") or []
        if not repos:
            # RM2578 : ces sorties étaient MUETTES, et `out.info` n'émet qu'en
            # --verbose. On ne pouvait donc pas distinguer « le hook n'a pas
            # tourné » de « il a tourné sans rien faire » — un ticket a conclu
            # au premier alors que rien ne le prouvait.
            out.warn(f"env de session non créé pour RM{rm_id} : aucun `repos:` "
                     f"au manifeste ({ws}/.mmi-pm/meta.yml)")
            return
        if len(repos) > 1:
            out.warn(f"env de session non auto ({len(repos)} repos au manifeste) : "
                     f"pm-env-session.py create {rm_id} --repo <name>")
            return
        name = repos[0].get("name")
        if not name:
            out.warn(f"env de session non créé pour RM{rm_id} : le premier `repos:` "
                     f"du manifeste n'a pas de `name`")
            return
        if not (ws / "repos" / f"{name}.git").is_dir():
            out.warn(f"env de session non créé pour RM{rm_id} : bare absent "
                     f"({ws}/repos/{name}.git) — workspace hors layout RM1993 ?")
            return
        if new_status == "en_cours":
            verb = "create"
        elif new_status == "ferme" and (ws / "envs" / f"{name}-rm{rm_id}").is_dir():
            verb = "teardown"
        else:
            return
        if verb == "teardown":
            # RM2356 : une éventuelle instance cockpit de test se démonte aussi
            cte = Path(__file__).resolve().parent / "pm-cockpit-test-env.py"
            subprocess.run([sys.executable, str(cte), "teardown", str(rm_id), str(ws),
                            "--if-exists"], capture_output=True, timeout=60)
        tool = Path(__file__).resolve().parent / "pm-env-session.py"
        # En TTY, passthrough : pm-env-session pose la question du clone BDD
        # (défaut projet db_clone_default) directement à l'utilisateur.
        tty = sys.stdin.isatty() and sys.stderr.isatty()
        r = subprocess.run([sys.executable, str(tool), verb, str(rm_id), str(ws)],
                           capture_output=not tty, text=True, timeout=600)
        hook_out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            last = hook_out.splitlines()[-1] if hook_out else f"✓ {verb} ok"
            # RM2578 : VISIBLE, pas réservé au --verbose. Savoir si le worktree
            # est exécutable (runtime appliqué) fait partie du contrat du take.
            out.op("env-session", rm=rm_id, extra=f"{verb} — {last}")
        else:
            # teardown refusé (worktree sale) ou runtime KO : on n'empêche JAMAIS
            # la transition de statut — l'env se gère à la main.
            out.warn(f"env de session ({verb}) non appliqué (non bloquant) : "
                     + " | ".join(hook_out.splitlines()[-4:]))
    except Exception as e:  # noqa: BLE001 — hook best-effort
        out.warn(f"hook env de session en échec (non bloquant) : {e}")


def fetch_issue_basic(rm_id):
    """Récupère subject + author (id, name) du ticket. Retourne dict ou None."""
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
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
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
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
        out.info("  → notif mail désactivée (pm.config.yml : notifications.email_enabled=false)")
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
    out.info(f"  → notif mail : {reason}")
    if dry_run:
        print(f"  --dry-run : to={to_addr}, subject={subject!r}")
        return

    script = Path(__file__).resolve().parent / "karl-mail-send.py"
    cmd = [sys.executable, str(script), "--to", to_addr, "--subject", subject,
           "--body", body, "--rm-id", str(rm_id)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        out.warn(f"échec notif mail (non fatal) : {r.stderr.strip()[:200]}")
    else:
        # extraire le Message-ID de la sortie pour le log console
        mid = next((l for l in r.stdout.splitlines() if l.startswith("Mid")), "")
        out.info(f"  ✓ notif mail envoyée à {to_addr}  {mid}")


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


def next_transitions(rm_id, check_redmine=True):
    """Transitions NORMS valides depuis le statut courant du ticket, en structuré.

    RM2888 : `list_next` ne savait qu'imprimer, donc le cockpit ne pouvait pas
    proposer « ce qui est possible ici » et se rabattait sur les 14 statuts en dur.
    La règle reste ICI (source unique) ; l'affichage texte et la sortie `--json`
    ne sont plus que deux rendus de cette structure.

    `redmine_ok` vaut None quand la vérification live n'a pas eu lieu (API
    injoignable, pas de credentials, ou `check_redmine=False`) : un appelant ne
    doit pas confondre « refusé » et « pas vérifié ».
    """
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
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
    if check_redmine and url and key:
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

    seen, transitions = set(), []
    for tgt, cond in nexts:
        if tgt in seen:          # `en_pause`/`ferme` génériques peuvent doubler une règle
            continue
        seen.add(tgt)
        transitions.append({
            "status": tgt,
            "condition": cond,
            "redmine_ok": None if allowed_ids is None else (sids.get(tgt) in allowed_ids),
            # Ce que l'appelant doit réclamer AVANT de soumettre : le script refuse
            # `ferme` sans motif, autant que l'UI le demande plutôt que d'échouer.
            "needs_close_reason": tgt == "ferme",
            # Idem pour la note : certaines transitions l'exigent (réouverture).
            # La condition est écrite dans NORMS_TRANSITIONS, juste au-dessus — ce
            # n'est pas un contrat externe qu'on parserait à l'aveugle.
            "needs_note": "note obligatoire" in cond,
        })
    return {"rm_id": int(rm_id), "status": cur, "transitions": transitions,
            "redmine_checked": allowed_ids is not None,
            "close_reasons": sorted(VALID_CLOSE_REASONS)}


def list_next(rm_id, as_json=False):
    """Affiche les transitions NORMS valides depuis le statut courant du ticket
    (+ marque celles que le compte API peut réellement poser côté Redmine)."""
    data = next_transitions(rm_id)
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
        return
    print(f"RM{rm_id} — statut courant : {data['status']}")
    print("Transitions NORMS valides :")
    for t in data["transitions"]:
        mark = ""
        if t["redmine_ok"] is not None:
            mark = "  [Redmine OK]" if t["redmine_ok"] else "  [Redmine REFUSERA pour ce compte]"
        print(f"  → {t['status']:<26} {t['condition']}{mark}")
    if not data["redmine_checked"]:
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
    ap.add_argument("--json", action="store_true",
                    help="Avec --list-next : sortie machine (statut courant + transitions), "
                         "consommée par le cockpit (RM2888)")
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
    ap.add_argument("--allow-unchecked", metavar="MOTIF", nargs="?", const="",
                    help="Autorise le passage en a_tester_demandeur / a_mep / ferme:resolu malgré des "
                         "items de checklist non cochés — en DISANT pourquoi. Le motif est obligatoire "
                         "et rejoint la note Redmine et le journal (RM2884) : sans lui, l'option "
                         "servait à franchir le contrôle sans faire le travail qu'il réclamait. "
                         "Ex : --allow-unchecked \"critères 5 et 6 vérifiables seulement par le demandeur\".")
    ap.add_argument("--allow-unmerged", action="store_true",
                    help="Autorise a_mep / ferme:resolu même si une branche <id>-* du ticket "
                         "n'est pas mergée dans la branche d'intégration (sinon bloqué — "
                         "RM2319 : clore 'resolu' sans merger = code validé jamais livré).")
    out.add_args(ap)
    ap.add_argument("--no-commit", action="store_true",
                    help="Pas d'auto-commit git des fichiers écrits (RM1834)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out.configure(args)

    if args.list_next:
        list_next(args.rm_id, as_json=args.json)
        return
    if args.json:
        sys.exit("ERREUR : --json n'a de sens qu'avec --list-next")
    if not args.status:
        sys.exit("ERREUR : statut requis (ou --list-next pour voir les transitions valides)")

    if args.status not in VALID_STATUSES:
        sys.exit(f"ERREUR : statut invalide '{args.status}'. Valides : {sorted(VALID_STATUSES)}")
    # Normalise les alias dépréciés (a_tester_verifier → a_tester_demandeur) pour
    # que frontmatter, status_history et Redmine enregistrent la forme canonique.
    canon_status = redmine_utils.normalize_status(args.status)
    if canon_status != args.status:
        out.warn(f"statut déprécié '{args.status}' normalisé → '{canon_status}'")
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
            out.info("  · report-on-close : " + (lines[-1].strip() if lines else "(rien à pousser)"))
        except Exception as e:
            out.warn(f"report-on-close échoué (non bloquant) : {e}")

    # 1. Parse + update frontmatter — sous VERROU PAR TICKET (T7) : sérialise le RMW
    # du .md contre un autre writer du même ticket. Volontairement ÉTROIT (read→write
    # du .md), libéré juste après l'écriture, AVANT les sous-process (metrics-push) et
    # l'auto-commit → pas d'auto-blocage flock. Les sys.exit intermédiaires libèrent le
    # verrou via l'OS (flock noyau). Le .log (append-only) et le commit git suivent hors
    # verrou (git a son propre verrouillage) ; l'atomicité pleine du triplet = daemon (c).
    _tlock = ticket_lock(cfg.state_dir, args.rm_id)
    _tlock.__enter__()
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
        out.info("  · réouverture : close_reason purgé, cycle précédent conservé dans status_history")

    fm["status"] = args.status
    if args.close_reason:
        fm["close_reason"] = args.close_reason
    elif reopening:
        fm["close_reason"] = None
    fm["updated"] = now
    entry = {
        "status": args.status,
        "at": now,
        "by": args.by,
        "model": None,
        "tokens": None,
        "duration_minutes": None,
    }
    # RM2366 (S5) : l'historique complet vit dans le ledger annexe ; le
    # frontmatter garde une QUEUE (dernière entrée = statut courant, exigé par
    # validate-task). sweep() migre au passage les résidus (writers non migrés).
    hist = (fm.get("status_history") or []) + [entry]
    fm["status_history"] = hist
    try:
        pm_reporting.sweep(fm, md_path)
    except Exception as e:
        out.warn(f"ledger reporting non mis à jour (non bloquant) : {e}")

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
    # Note = bloc MÉCANIQUE templaté (RM2365, CDC RM2316 § S4 — templates/notes/
    # status_change.md) + éventuel AJOUT SÉMANTIQUE (--note). L'agent ne rédige
    # plus la partie mécanique ; assemblage final après résolution d'assignation.
    semantic_note = args.note
    # Lignes ajoutées à la note par les gardes elles-mêmes (RM2884 : le motif d'un
    # --allow-unchecked doit rester dans le ticket, sinon le contournement ne laisse
    # aucune trace et redevient indiscernable d'un oubli).
    extra_notes = []

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
    # RM2789 — le gabarit se résout, il ne se contourne pas. Contrôlé AVANT le garde-fou
    # des vrais critères, et hors de sa clause `--allow-unchecked`.
    if gate_status and issue and count_placeholders(issue.get("description")):
        sys.exit(placeholder_gate(args.rm_id, issue.get("description"), f"passer en '{args.status}'"))
    if gate_status and issue:
        desc = issue.get("description")
        # RM2789 : passe par pm_markdown — blocs de code ignorés, gabarits exclus (ils ont
        # leur propre garde, plus haut : un gabarit se résout, il ne se motive pas).
        n_unchecked = count_unchecked(desc)
        n_checked = count_checked(desc)
        motif = args.allow_unchecked            # None = option absente ; "" = passée sans motif
        if n_unchecked and motif is None:
            # Le ratio compte : « 0 coché sur 7 » est presque toujours un oubli,
            # « 6 sur 7 » un choix assumé. Le message doit les distinguer (RM2884).
            total = n_checked + n_unchecked
            if n_checked == 0:
                quoi = (f"AUCUN des {total} critères n'est coché — une description qui ne dit pas "
                        f"ce qui est fait rend le ticket illisible")
            else:
                quoi = f"{n_checked} coché(s) sur {total}, {n_unchecked} restant(s)"
            sys.exit(
                f"ERREUR : RM{args.rm_id} — {quoi}. Refus de passer en '{args.status}'.\n"
                f"  → Coche ce qui est fait : pm-task-description-update.py {args.rm_id} --check <n,...>\n"
                f"  → Ou dis pourquoi ça reste décoché : "
                f"--allow-unchecked \"<motif>\" (le motif est tracé dans la note et le journal)."
            )
        if n_unchecked and motif == "":
            sys.exit(
                f"ERREUR : --allow-unchecked exige un motif (RM2884).\n"
                f"  → Ex : --allow-unchecked \"critères 5 et 6 vérifiables seulement par le demandeur\"\n"
                f"  → Un contournement non motivé est indiscernable d'un oubli — c'est précisément "
                f"ce qui a laissé 28 tickets partir en test ou en clôture avec 0 critère coché."
            )
        if n_unchecked and motif:
            total = n_checked + n_unchecked
            grave = (args.status == "ferme" and n_checked == 0)
            print(f"{'⚠ ' if grave else 'ℹ '}checklist : {n_checked}/{total} coché(s), "
                  f"{n_unchecked} laissé(s) décoché(s) — motif : {motif}")
            if grave:
                print("  ⚠ fermeture avec AUCUN critère coché : le ticket ne gardera aucune trace "
                      "de ce qui a été fait. Vérifie que c'est bien voulu.")
            extra_notes.append(f"Checklist : {n_unchecked} item(s) laissé(s) décoché(s) "
                               f"({n_checked}/{total} coché(s)) — motif : {motif}")
        # RM2789 — « aucun critère jamais défini » n'est PAS « des critères non tenus » :
        # ça n'a rien à voir avec la qualité de la livraison. On avertit, on ne bloque pas.
        elif not has_criteria(desc):
            print(f"⚠ RM{args.rm_id} n'a AUCUN critère d'acceptation défini — livré quand même.\n"
                  f"  → pm-task-description-update.py {args.rm_id} --set-from-file <fichier>",
                  file=sys.stderr)
    # …et on le dit AU PLUS TÔT. Découvrir le gabarit à la livraison, c'est une embuscade :
    # le travail est fini, on veut rendre, et un détail de rédaction bloque. À la PRISE en
    # charge, il reste tout le temps de le traiter.
    if args.status == "en_cours" and issue and count_placeholders(issue.get("description")):
        print(f"⚠ RM{args.rm_id} porte un gabarit de critère « à compléter ». Traite-le "
              f"MAINTENANT, il bloquera la livraison :\n"
              f"  → pm-task-description-update.py {args.rm_id} --set-from-file <fichier>\n"
              f"  → ou pm-task-description-update.py {args.rm_id} --drop-placeholders",
              file=sys.stderr)
    # Merge gate (RM2319) : on ne passe pas un ticket en a_mep / ferme:resolu si une
    # branche <id>-* n'est pas mergée dans la branche d'intégration — c'est exactement
    # l'incident RM2302 (validé + fermé via le cockpit, code jamais livré). La garde
    # vit ICI (source unique des transitions), le cockpit en hérite via pm/run.
    merge_gate = args.status == "a_mep" or (
        args.status == "ferme" and args.close_reason == "resolu")
    if merge_gate and not args.allow_unmerged:
        found = unmerged_ticket_branches(md_path, args.rm_id)
        if found:
            repo, integration, branches = found
            sys.exit(
                f"ERREUR : branche(s) du ticket RM{args.rm_id} non mergée(s) dans "
                f"'{integration}' : {', '.join(branches)} — passer en "
                f"'{args.status}{':' + args.close_reason if args.close_reason else ''}' "
                f"livrerait un code validé mais jamais déployé "
                f"(incident RM2302 → RM2319).\n"
                f"  → Livrer d'abord : pm-mr create {args.rm_id} && pm-mr merge <iid>\n"
                f"  → Ou, si c'est volontaire (code abandonné / repris ailleurs) : "
                f"relance avec --allow-unmerged."
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
                out.warn(f"pas de protocole de test sur RM{args.rm_id} → pm-task-protocol.py {args.rm_id} --set -")
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
        out.info("  · auto-assign à l'agent courant (NORMS v1.12.0, --no-assign pour outrepasser)")
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

    tpl_path = Path(__file__).resolve().parent.parent / "templates" / "notes" / "status_change.md"
    try:
        tpl = tpl_path.read_text(encoding="utf-8").strip()
    except OSError:
        tpl = "Statut : {old} → {new}{close}{assign}{git}"
    git_fm = fm.get("git") or {}
    mech = tpl.format(
        old=old_status, new=args.status,
        close=f" ({args.close_reason})" if args.close_reason else "",
        assign=f" · assigné → {assigned_to_id}" if assigned_to_id is not None else "",
        git=(f"\nGit : branche={git_fm.get('branch')}"
             + (f" · MR {git_fm.get('mr_url')}" if git_fm.get("mr_url") else ""))
            if git_fm.get("branch") else "",
    ).strip()
    corps = "\n\n".join([x for x in ([semantic_note] if semantic_note else []) + extra_notes])
    note = mech + (f"\n\n{corps}" if corps else "")

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
    r = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    out.info((r.stdout or "").rstrip())
    if r.returncode != 0:
        detail = "\n".join(s.rstrip() for s in (r.stdout, r.stderr) if s and s.strip())
        out.fail(f"redmine-post-note (exit {r.returncode}) :\n{detail}",
                 remede="vérifier allowed_statuses (pm-task-blockers) ou relancer avec --verbose")
    # ligne dense unique (contrat T1) — le détail est en --verbose / log / Redmine
    out.op("statut", rm=args.rm_id,
           extra=f"{old_status}→{args.status}"
                 + (f" assign={assigned_to_id}" if assigned_to_id is not None else "")
                 + (f" close={args.close_reason}" if args.close_reason else ""))

    # 3. Write MD (atomique) puis LIBÈRE le verrou ticket — les sous-process suivants
    # (metrics-push, autocommit) reprennent leurs propres verrous sans nesting.
    atomic_write(md_path, new_content)
    _tlock.__exit__(None, None, None)
    out.info(f"✓ MD synchronisé : {md_path.relative_to(cfg.projects_root)}")

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
    out.info(f"✓ log appendé : {log_path.name}")

    # 5. Notif mail au demandeur (résolu via resolve_notif_target ; Manager IA
    # par défaut si author=karl ou email inaccessible).
    if not args.no_mail:
        if issue is None:
            out.warn("ticket Redmine non fetchable pour la notif mail (skip)")
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
                out.warn(f"push estimation à la prise échoué (exit {r2.returncode})")

    # 6bis. Hooks D1/D2 env de session (RM1834/RM1947) : en_cours → create,
    # ferme → teardown. Best-effort, jamais bloquant.
    if args.status in ("en_cours", "ferme") and old_status != args.status:
        env_session_hook(md_path, args.rm_id, args.status, old_status)

    # 6ter. Note de suivi chez les gestionnaires PARTENAIRES (RM2656) : seulement si
    # le projet déclare un secondaire dont `sync.push.on` contient ce statut. Inerte
    # partout ailleurs, et **jamais bloquant** — un partenaire injoignable ne doit pas
    # faire échouer une transition déjà écrite côté PM (même règle que 6bis / 7).
    if not args.dry_run and old_status != args.status:
        try:
            r = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "pm-task-partner.py"),
                 "push", str(args.rm_id), "--status", args.status, "--quiet",
                 "--no-commit"], check=False, capture_output=True, text=True, timeout=60)
            detail = (r.stdout + r.stderr).strip()
            if r.returncode != 0:
                # Anormal : sans partenaire configuré, le push sort en 0 sans rien dire.
                out.warn(f"note de suivi partenaire : échec (exit {r.returncode}) "
                         f"{detail.splitlines()[-1] if detail else ''}")
            for line in detail.splitlines():
                if line.strip():
                    out.info(f"  partenaire : {line.strip()}")
        except Exception as e:                                  # noqa: BLE001
            out.warn(f"note de suivi partenaire non poussée (best-effort) : {e}")

    # 7. Worklog de session (best-effort, no-op hors session Claude Code) : reflète
    # la transition pour que « il reste quoi à faire dans cette session » reste fidèle.
    # Upsert : crée l'item si le ticket n'avait pas été ouvert dans cette session. Cf RM1875.
    if not args.dry_run:
        # best-effort, JAMAIS bloquant (comme l'étape 6bis) : un checkout sans
        # pm_session_hook.py (branche antérieure à son ajout, checkout partiel)
        # ne doit pas planter la clôture APRÈS l'écriture du statut et faire
        # sauter l'auto-commit de l'étape 8 (incident RM2587).
        try:
            import pm_session_hook
            try:
                proj = md_path.relative_to(cfg.projects_root).parts[3]
            except (ValueError, IndexError):
                proj = None
            pm_session_hook.log_to_session(
                f"RM{args.rm_id}", label=fm.get("title"),
                status=args.status, project=proj)
        except Exception as e:
            out.warn(f"worklog de session non mis à jour (best-effort) : {e}")

    # 8. Auto-commit atomique des fichiers écrits (RM1834 piste A). Placé en
    # dernier : capture aussi l'écriture frontmatter du push d'estimation (étape 6).
    if not args.dry_run and not args.no_commit:
        pm_git.autocommit([md_path, log_path, pm_reporting.ledger_path(md_path)],
                          f"pm(status): RM{args.rm_id} {old_status} -> {args.status}")


if __name__ == "__main__":
    main()
