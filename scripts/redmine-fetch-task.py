#!/usr/bin/env python3
"""Fetcher un ticket Redmine et générer le fichier MD correspondant.

Identifie automatiquement le projet MD via `redmine.project_id` dans
`project/overview.md`, ou prend entité/projet en argument. Génère le fichier
de tâche au chemin résolu par `pm.config.yml :: paths.task_file`, plus un
log initial, puis valide via validate-task.py.

Usage :
    ./scripts/redmine-fetch-task.py --issue 42
    ./scripts/redmine-fetch-task.py --issue 42 --client lemathou --project mathematicians-db
    ./scripts/redmine-fetch-task.py --issue 42 --dry-run
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import issue_is_ia_tagged, get_ia_cf_id, api_ts_local

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


TRACKER_TO_TYPE = {
    "bug": "bugfix",
    "anomalie": "bugfix",
    "feature": "feature",
    "fonctionnalité": "feature",
    "fonctionnalite": "feature",
    "évolution": "feature",
    "evolution": "feature",
    "support": "assistance",
    "task": "maintenance",
    "tâche": "maintenance",
    "tache": "maintenance",
    "documentation": "documentation",
    "audit": "audit",
    "research": "research",
    "recherche": "research",
}

PRIORITY_TO_NORMS = {
    "low": "low", "basse": "low",
    "normal": "normal", "normale": "normal",
    "high": "high", "haute": "high",
    "urgent": "urgent", "urgente": "urgent", "immediate": "urgent", "immédiate": "urgent",
}


def fetch_issue(url, key, issue_id):
    full = f"{url.rstrip('/')}/issues/{issue_id}.json?key={key}&include=description"
    req = request.Request(full, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["issue"]


def fetch_project_identifier(url, key, project_id):
    """Récupère l'identifier (slug) d'un projet à partir de son id numérique.
    L'API /issues/{id}.json ne renvoie que l'id+name du projet, pas l'identifier."""
    full = f"{url.rstrip('/')}/projects/{project_id}.json?key={key}"
    req = request.Request(full, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["project"].get("identifier")


def fetch_user_login(url, key, user_id):
    """Récupère le login d'un user à partir de son ID (l'API issues ne renvoie que name)."""
    try:
        full = f"{url.rstrip('/')}/users/{user_id}.json?key={key}"
        req = request.Request(full, headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["user"].get("login")
    except (error.HTTPError, error.URLError):
        return None


def now_iso(minutes=False):
    """Timestamp local courant, format ISO."""
    fmt = "%Y-%m-%dT%H:%M" if minutes else "%Y-%m-%d"
    return datetime.now().strftime(fmt)


FRENCH_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l",
    "à", "a", "au", "aux", "en", "dans", "par", "pour", "sur", "sous", "sans", "avec", "vers", "chez",
    "et", "ou", "ni", "mais", "donc", "or", "car",
    "ce", "cet", "cette", "ces", "ça", "cela",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "notre", "votre", "leur", "leurs",
    "que", "qui", "quoi", "dont", "où",
    "est", "sont", "etre", "être",
}
MAX_SLUG_LEN = 40


def slugify(s):
    """Slug court : enlève les stop-words FR/EN, tronque à MAX_SLUG_LEN au mot le plus proche."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", s.lower()) if w]
    filtered = [w for w in words if w not in FRENCH_STOPWORDS] or words
    slug = "-".join(filtered)
    if len(slug) <= MAX_SLUG_LEN:
        return slug or "untitled"
    truncated = []
    total = 0
    for w in filtered:
        add = len(w) + (1 if truncated else 0)
        if total + add > MAX_SLUG_LEN:
            break
        truncated.append(w)
        total += add
    return "-".join(truncated) or filtered[0][:MAX_SLUG_LEN]


def latest_journal_id(issue):
    journals = issue.get("journals") or []
    if not journals:
        return 0
    return max(j["id"] for j in journals)


def build_frontmatter(issue, author_login):
    tracker_name = (issue.get("tracker") or {}).get("name", "").strip().lower()
    task_type = TRACKER_TO_TYPE.get(tracker_name, "feature")
    # Taxonomie fine : si le CF « Task type » (CF20) porte une valeur mappée à un
    # type NORMS (ex. Documentation → documentation), elle prime sur le tracker
    # coarse. Symétrique de la pose côté pm-task-add.
    from redmine_utils import task_type_cf
    tt_cf_id, tt_values = task_type_cf()
    if tt_cf_id:
        rev = {str(v): k for k, v in tt_values.items()}
        for cf in (issue.get("custom_fields") or []):
            if cf.get("id") == tt_cf_id and str(cf.get("value")) in rev:
                task_type = rev[str(cf["value"])]
                break

    prio_name = (issue.get("priority") or {}).get("name", "").strip().lower()
    priority = PRIORITY_TO_NORMS.get(prio_name, "normal")

    author = author_login or (issue.get("author") or {}).get("login") or (issue.get("author") or {}).get("name") or "unknown"
    created_full = api_ts_local(issue.get("created_on"))
    created_date = created_full.split("T")[0] or now_iso()
    sh_at = created_full if "T" in created_full else now_iso(minutes=True)

    fm = {
        "schema_version": "1.5.2",
        "redmine_id": int(issue["id"]),
        "redmine_last_journal_id": latest_journal_id(issue),
        "redmine_last_checked_at": now_iso(minutes=True),
        "title": (issue.get("subject") or "").strip() or f"Ticket Redmine #{issue['id']}",
        "type": task_type,
        "parent_task": None,
        "sub_tasks": [],
        "creator": author,
        "team": [],
        "status": "a_etudier_chiffrer",
        "close_reason": None,
        "completion_pct": 0,
        "priority": priority,
        "roi": {"immediate_benefit": 3, "monthly_benefit": 2},
        "estimate": {
            "difficulty": None, "time_minutes": None, "tokens": None,
            "confidence": None, "estimated_by": None, "estimated_at": None,
        },
        "depends_on": [],
        "blocks": [],
        "refs": [],
        "test_url": None,
        "git": {"repo": None, "branch": None, "mr_url": None},
        "deploy_actions": [],
        "tokens_total": 0,
        "time_total_minutes": 0,
        "created": created_date,
        "due": None,
        "updated": now_iso(),
        "status_history": [{
            "status": "a_etudier_chiffrer",
            "at": sh_at,
            "by": author,
            "model": None,
            "tokens": None,
            "duration_minutes": None,
        }],
        "pistes": [],
        "tags": [],
    }

    if task_type == "bugfix":
        fm["bug"] = {
            "reproducibility": "always",
            "reproduce_steps": "1.\n2.\n",
            "conditions": "",
        }

    return fm


def render_md(fm, description, redmine_url, issue_id):
    desc = (description or "").strip() or "<!-- Description vide côté Redmine -->"
    body = (
        f"## Contexte\n\n{desc}\n\n"
        "## Critères d'acceptation\n- [ ]\n- [ ]\n\n"
        "## Instructions\n<!-- Étapes, contraintes, accès nécessaires -->\n\n"
        f"## Références\n- Redmine : {redmine_url.rstrip('/')}/issues/{issue_id}\n"
    )
    yaml_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False)
    return f"---\n{yaml_fm}---\n\n{body}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue", type=int, required=True, help="ID du ticket Redmine")
    ap.add_argument("--client", help="Slug client (sinon auto-détecté)")
    ap.add_argument("--project", help="Slug projet (sinon auto-détecté)")
    ap.add_argument("--overwrite", action="store_true", help="Écraser si fichier existe")
    ap.add_argument("--slug", help="Slug à utiliser pour le nom de fichier (sinon généré depuis le titre)")
    ap.add_argument("--dry-run", action="store_true", help="Afficher sans écrire")
    ap.add_argument("--force", action="store_true",
                    help="Bypasse le filtre tag IA (créer le MD même si le ticket n'est pas tagué)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")

    if not (url and key):
        print("ERREUR : $REDMINE_URL et $REDMINE_API_KEY requis (.env)", file=sys.stderr)
        sys.exit(1)

    try:
        # On inclut les journaux pour pouvoir initialiser redmine_last_journal_id
        # à la dernière entrée existante (évite de re-traiter le passé).
        # custom_fields est inclus par défaut dans la réponse d'un issue.
        full = f"{url.rstrip('/')}/issues/{args.issue}.json?key={key}&include=description,journals"
        req = request.Request(full, headers={"Accept": "application/json"})
        with request.urlopen(req, timeout=10) as resp:
            issue = json.loads(resp.read())["issue"]
    except error.HTTPError as e:
        print(f"ERREUR Redmine : HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    # Filtre IA : refuser les tickets non tagués (sauf --force ou si CF non configuré)
    if not args.force and get_ia_cf_id() is not None and not issue_is_ia_tagged(issue):
        print(f"ERREUR : ticket #{args.issue} non tagué 'IA' côté Redmine. ", file=sys.stderr)
        print(f"        Utiliser scripts/redmine-tag-ia.py {args.issue} pour le tagger, ", file=sys.stderr)
        print(f"        ou --force pour bypasser le filtre (déconseillé).", file=sys.stderr)
        sys.exit(2)

    if args.client and args.project:
        entity_slug, project_slug = args.client, args.project
        project_dir = cfg.path("project", entity=entity_slug, project=project_slug)
        if not project_dir.is_dir():
            print(f"ERREUR : {project_dir} introuvable", file=sys.stderr)
            sys.exit(1)
    else:
        proj = issue.get("project") or {}
        rm_project = proj.get("identifier")
        if not rm_project and proj.get("id"):
            try:
                rm_project = fetch_project_identifier(url, key, proj["id"])
            except error.HTTPError as e:
                print(f"ERREUR : résolution projet (id={proj['id']}) : HTTP {e.code}", file=sys.stderr)
                sys.exit(1)
        if not rm_project:
            print("ERREUR : impossible de déterminer l'identifier du projet Redmine", file=sys.stderr)
            sys.exit(1)
        entity_dir, project_dir = cfg.find_project_by_redmine_id(rm_project)
        if project_dir is None:
            print(f"ERREUR : aucun projet MD ne référence redmine.project_id='{rm_project}'", file=sys.stderr)
            print("        Préciser --client <slug> --project <slug>", file=sys.stderr)
            sys.exit(1)
        entity_slug, project_slug = entity_dir.name, project_dir.name

    # Résoudre le login de l'auteur (l'API issues ne renvoie que name)
    author_info = issue.get("author") or {}
    author_login = fetch_user_login(url, key, author_info["id"]) if author_info.get("id") else None

    fm = build_frontmatter(issue, author_login)
    slug = args.slug or slugify(fm["title"])
    target = cfg.path("task_file", entity=entity_slug, project=project_slug, id=fm["redmine_id"], slug=slug)
    log_target = cfg.path("task_log_file", entity=entity_slug, project=project_slug, id=fm["redmine_id"], slug=slug)

    content = render_md(fm, issue.get("description") or "", url, fm["redmine_id"])

    print(f"Issue       : #{issue['id']} — {(issue.get('tracker') or {}).get('name', '?')}")
    print(f"Sujet       : {fm['title']}")
    print(f"Auteur      : {fm['creator']}")
    print(f"Client      : {entity_slug}")
    print(f"Projet      : {project_slug}")
    print(f"Destination : {target}")
    print()

    if args.dry_run:
        print("--- DRY RUN — contenu généré ---\n")
        print(content)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not args.overwrite:
        print(f"ERREUR : {target.name} existe déjà (utiliser --overwrite)", file=sys.stderr)
        sys.exit(1)

    target.write_text(content, encoding="utf-8")

    if not log_target.exists():
        log_target.write_text(
            f"# Journal RM{fm['redmine_id']}\n\n"
            f"## {now_iso(minutes=True)} — redmine-fetch-task\n"
            "Tokens : 0 | Durée : 0 min\n\n"
            f"Tâche créée depuis Redmine #{fm['redmine_id']} ({url.rstrip('/')}/issues/{fm['redmine_id']}).\n",
            encoding="utf-8",
        )

    print(f"✓ Fichier créé    : {target}")
    print(f"✓ Journal initial : {log_target}")
    print()
    print("→ Validation via validate-task.py :")
    validator = Path(__file__).resolve().parent / "validate-task.py"
    rc = subprocess.run(["python3", str(validator), str(target)]).returncode
    if rc != 0:
        print("\n⚠ Validation échouée — corriger le fichier avant invocation worker", file=sys.stderr)
        sys.exit(rc)


if __name__ == "__main__":
    main()
