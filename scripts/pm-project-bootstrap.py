#!/usr/bin/env python3
"""Bootstrap a PM project by instantiating bootstrap-tasks templates.

For each retained template, this script :
  1. Creates a Redmine ticket in the project's `redmine.project_id`
  2. Writes a task MD file `tasks/RM<id>_<slug>.md` with full frontmatter
  3. Writes a corresponding `.log.md` with the initial entry
  4. Updates `project/overview.md` :: `bootstrap.done[]`

Usage :
    pm-project-bootstrap.py <project-pm-dir> [options]

Options :
    --yes                       Non-interactive — take all default_checked applicable templates
    --dry-run                   Show what would be done, don't touch anything
    --include <id>              Force-include a template (can be repeated)
    --exclude <id>              Force-exclude a template (can be repeated)
"""
import argparse
import mimetypes
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import create_redmine_issue

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install PyYAML")


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates" / "bootstrap-tasks"

NORMS_TYPE_TO_TRACKER = {
    "bugfix": 1,        # Anomalie
    "feature": 2,       # Evolution
    "assistance": 3,    # Assistance
    # tout le reste → 4 (Tâche)
}
NORMS_PRIORITY_TO_REDMINE = {"low": 1, "normal": 2, "high": 3, "urgent": 4}

FRENCH_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "à", "au",
    "aux", "en", "dans", "par", "pour", "sur", "et", "ou", "que", "qui", "se",
    "ce", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "the", "a", "an",
    "of", "in", "on", "for", "to", "and", "or",
}
MAX_SLUG_LEN = 40


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9 -]+", " ", s).lower().strip()
    words = [w for w in s.split() if w and w not in FRENCH_STOPWORDS]
    slug = "-".join(words)
    if len(slug) <= MAX_SLUG_LEN:
        return slug
    truncated = slug[:MAX_SLUG_LEN].rsplit("-", 1)[0]
    return truncated or slug[:MAX_SLUG_LEN]


def parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        sys.exit(f"No frontmatter found in {path}")
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return fm, body


def write_frontmatter(path: Path, fm: dict, body: str):
    serialized = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    path.write_text(f"---\n{serialized}\n---\n{body}", encoding="utf-8")


def load_templates():
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        fm, body = parse_frontmatter(path)
        templates.append({
            "id": fm["bootstrap_template"],
            "default_checked": bool(fm.get("default_checked", False)),
            "title": fm["title"],
            "type": fm.get("type", "maintenance"),
            "priority": fm.get("priority", "normal"),
            "tags": fm.get("tags", []),
            "roi": fm.get("roi", {"immediate_benefit": 2, "monthly_benefit": 2}),
            "estimate": fm.get("estimate", {"difficulty": "low", "time_minutes": 30}),
            "applicable_when": fm.get("applicable_when", ""),
            "body": body,
            "path": path,
        })
    return templates


def is_applicable(tpl, project_dir, overview):
    """Heuristic applicability per template id. Defaults to True if unknown."""
    pid = tpl["id"]
    proj_dir = project_dir / "project"

    if pid == "001-secrets-vaultwarden":
        env_path = proj_dir / "environments.md"
        if not env_path.is_file():
            return True
        env_fm, _ = parse_frontmatter(env_path)
        envs = env_fm.get("environments") or []
        return any(not e.get("secrets_source") for e in envs) if envs else True

    if pid == "002-git-repos":
        gl = overview.get("gitlab") or {}
        return not (gl.get("repo") or "").strip()

    if pid == "003-environnements":
        env_path = proj_dir / "environments.md"
        if not env_path.is_file():
            return True
        env_fm, _ = parse_frontmatter(env_path)
        return not (env_fm.get("environments") or [])

    if pid == "004-stack":
        return not (proj_dir / "stack.md").is_file()
    if pid == "005-deployment":
        return not (proj_dir / "deployment.md").is_file()
    if pid == "006-testing":
        return not (proj_dir / "testing.md").is_file()
    if pid == "007-monitoring":
        return not (proj_dir / "monitoring.md").is_file()

    return True


def interactive_picker(selectable):
    """Show a list with checkboxes, let user toggle, return retained templates."""
    print("\nBootstrap templates :")
    print("  ([x] coché par défaut, [ ] non coché, ! non applicable au projet)")
    print()
    states = []
    for i, (tpl, applicable, default) in enumerate(selectable, start=1):
        mark = "[x]" if default else "[ ]"
        appl = "" if applicable else " ! "
        states.append(default)
        print(f"  {i:2d}. {mark}{appl}{tpl['id']:<28s} — {tpl['title']}")
    print()
    print("Numéro(s) à toggle (séparés par espace), ou Entrée pour valider en l'état,")
    print("ou 'q' pour annuler :")
    raw = input("> ").strip()
    if raw.lower() in ("q", "quit", "abort"):
        sys.exit("Aborted.")
    if raw:
        for tok in raw.split():
            try:
                idx = int(tok) - 1
                if 0 <= idx < len(states):
                    states[idx] = not states[idx]
            except ValueError:
                pass
    retained = [tpl for (tpl, _, _), st in zip(selectable, states) if st]
    if retained:
        print("\nÀ instancier :")
        for tpl in retained:
            print(f"  - {tpl['id']} : {tpl['title']}")
        confirm = input("\nConfirmer ? [y/N] ").strip().lower()
        if confirm not in ("y", "yes", "o", "oui"):
            sys.exit("Aborted.")
    return retained


def create_redmine_ticket(project_id, tpl):
    """Crée le ticket Redmine pour un template bootstrap.

    Délègue à `redmine_utils.create_redmine_issue()` (source unique) qui
    set automatiquement le CF IA (cf. NORMS « Filtrage IA »). Le bootstrap
    est exécuté par karl (agent) → POST author=karl OK, pas de PUT
    author_id nécessaire.
    """
    tracker_id = NORMS_TYPE_TO_TRACKER.get(tpl["type"], 4)
    priority_id = NORMS_PRIORITY_TO_REDMINE.get(tpl["priority"], 2)
    return create_redmine_issue(
        project_id=project_id,
        tracker_id=tracker_id,
        priority_id=priority_id,
        subject=tpl["title"],
        description=tpl["body"].strip(),
    )


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def write_task(project_dir, tpl, issue_id, overview):
    slug = slugify(tpl["title"])
    task_filename = f"RM{issue_id}_{slug}.md"
    log_filename = f"RM{issue_id}_{slug}.log.md"
    tasks_dir = project_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    task_path = tasks_dir / task_filename
    log_path = tasks_dir / log_filename

    creator = "iprospective"
    creator_email = "mathieu@iprospective.fr"
    if overview.get("defaults", {}).get("team"):
        first = overview["defaults"]["team"][0]
        creator = first.get("username") or creator
        creator_email = first.get("email") or creator_email

    today = datetime.now().date().isoformat()
    iso = now_iso()

    fm = {
        "schema_version": "1.7.1",
        "redmine_id": issue_id,
        "redmine_last_journal_id": None,
        "redmine_last_checked_at": None,
        "title": tpl["title"],
        "type": tpl["type"],
        "bootstrap_template": tpl["id"],
        "parent_task": None,
        "sub_tasks": [],
        "creator": creator,
        "team": [{"username": creator, "email": creator_email, "role": "owner"}],
        "status": "a_faire",
        "close_reason": None,
        "completion_pct": 0,
        "priority": tpl["priority"],
        "roi": tpl["roi"],
        "estimate": {
            "difficulty": tpl["estimate"].get("difficulty", "low"),
            "time_minutes": tpl["estimate"].get("time_minutes", 30),
            "tokens": None,
            "confidence": 0.7,
            "estimated_by": "bootstrap-template",
            "estimated_at": iso,
        },
        "depends_on": [],
        "blocks": [],
        "refs": [],
        "target_env": None,
        "test_url": None,
        "git": {"repo": None, "branch": None, "mr_url": None},
        "deploy_actions": [],
        "tokens_total": 0,
        "time_total_minutes": 0,
        "created": today,
        "due": None,
        "updated": iso,
        "status_history": [
            {"status": "a_faire", "at": iso, "by": creator, "model": None, "tokens": None, "duration_minutes": None}
        ],
        "pistes": [],
        "tags": tpl["tags"],
    }

    write_frontmatter(task_path, fm, tpl["body"].lstrip("\n"))
    log_path.write_text(
        f"# Journal RM{issue_id}\n\n## {iso} — pm-project-bootstrap\nTokens : 0 | Durée : 0 min\n\nTâche créée depuis le template `{tpl['id']}`.\n",
        encoding="utf-8",
    )
    return task_path


def update_overview_done(overview_path, done):
    # RM1994 : bootstrap.done s'écrit dans meta.yml (sinon frontmatter overview en transition).
    meta_path = overview_path.parent.parent / "meta.yml"
    if meta_path.is_file():
        fm = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        fm.setdefault("bootstrap", {"skip": [], "done": []})
        fm["bootstrap"]["done"] = sorted(set(fm["bootstrap"].get("done", []) or []) | set(done))
        meta_path.write_text(
            yaml.safe_dump(fm, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    else:
        fm, body = parse_frontmatter(overview_path)
        fm.setdefault("bootstrap", {"skip": [], "done": []})
        fm["bootstrap"]["done"] = sorted(set(fm["bootstrap"].get("done", []) or []) | set(done))
        write_frontmatter(overview_path, fm, body)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", help="Chemin vers le dossier projet PM (qui contient project/, tasks/, …)")
    ap.add_argument("--yes", action="store_true", help="Non-interactif (prend les default_checked applicables)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include", action="append", default=[], help="Force-include template id (peut être répété)")
    ap.add_argument("--exclude", action="append", default=[], help="Force-exclude template id (peut être répété)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    project_dir = Path(args.project_dir).resolve()
    overview_path = project_dir / "project" / "overview.md"
    if not overview_path.is_file():
        sys.exit(f"{overview_path} introuvable")

    # RM1994 : manifeste = meta.yml (sinon fallback frontmatter overview)
    meta_path = project_dir / "meta.yml"
    if meta_path.is_file():
        overview = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    else:
        overview, _ = parse_frontmatter(overview_path)
    redmine_project = (overview.get("redmine") or {}).get("project_id")
    if not redmine_project and not args.dry_run:
        sys.exit("project/overview.md :: redmine.project_id manquant")

    skip = set((overview.get("bootstrap") or {}).get("skip") or [])
    done = set((overview.get("bootstrap") or {}).get("done") or [])

    templates = load_templates()
    selectable = []
    for tpl in templates:
        if tpl["id"] in skip or tpl["id"] in done:
            continue
        if tpl["id"] in args.exclude:
            continue
        applicable = is_applicable(tpl, project_dir, overview)
        default = (tpl["default_checked"] and applicable) or (tpl["id"] in args.include)
        selectable.append((tpl, applicable, default))

    if not selectable:
        print("Aucun template à instancier (tous déjà done/skip/exclus).")
        return

    if args.yes or not sys.stdin.isatty():
        retained = [tpl for tpl, _, default in selectable if default]
        if retained:
            print("Auto-pick (default_checked + applicable) :")
            for tpl in retained:
                print(f"  - {tpl['id']} : {tpl['title']}")
    else:
        retained = interactive_picker(selectable)

    if args.dry_run:
        print("\n--dry-run : rien n'est créé.")
        return

    new_done = []
    for tpl in retained:
        print(f"\n[{tpl['id']}] création ticket Redmine …")
        issue_id = create_redmine_ticket(redmine_project, tpl)
        print(f"  → ticket #{issue_id} créé")
        path = write_task(project_dir, tpl, issue_id, overview)
        try:
            print(f"  → {path.relative_to(cfg.projects_root)}")
        except ValueError:
            print(f"  → {path}")
        new_done.append(tpl["id"])

    if new_done:
        update_overview_done(overview_path, new_done)
        print(f"\n✓ overview.md :: bootstrap.done mis à jour ({len(new_done)} ajouté(s))")


if __name__ == "__main__":
    main()
