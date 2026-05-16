#!/usr/bin/env python3
"""pm-task-add — Crée une nouvelle tâche (POST Redmine + MD + log + valide).

Usage :
    pm-task-add.py --title "Setup CI GitLab" --type infrastructure --priority high
    pm-task-add.py --title "..." --description "Détails..." --tags "ci,gitlab"
    pm-task-add.py --project iprospective/pm-ai-agents --title "..." --type feature

Détection projet :
  1. --project entity/project explicite
  2. cwd via mmi-pm / .mmi-pm symlink (comme pm-task-list)
  3. cwd dans projects_root/clients/<E>/projects/<P>/

Mapping NORMS → Redmine tracker (par défaut) :
    bugfix       → 1 (Anomalie)
    feature      → 2 (Évolution)
    assistance   → 3 (Assistance)
    autre        → 4 (Tâche)
"""
import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import get_ia_cf_id

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


TYPE_TO_TRACKER = {"bugfix": 1, "feature": 2, "assistance": 3, "infrastructure": 4, "maintenance": 4, "autre": 4}
PRIORITY_TO_ID = {"low": 1, "normal": 2, "high": 3, "urgent": 4}


def slugify(s: str, maxlen: int = 50) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s).strip("-").lower()
    return s[:maxlen].rstrip("-")


def detect_project_from_cwd(cfg):
    """Réplique la détection de pm-task-list.py (simplifiée)."""
    cwd = Path.cwd().resolve()
    for d in [cwd] + list(cwd.parents):
        for name in ("mmi-pm", ".mmi-pm"):
            link = d / name
            if link.is_symlink():
                target = link.resolve()
                try:
                    parts = target.relative_to(cfg.projects_root).parts
                    if len(parts) >= 4 and parts[0] == "clients" and parts[2] == "projects":
                        return parts[1], parts[3]
                except ValueError:
                    pass
    try:
        parts = cwd.relative_to(cfg.projects_root).parts
        if len(parts) >= 4 and parts[0] == "clients" and parts[2] == "projects":
            return parts[1], parts[3]
    except ValueError:
        pass
    return None


def load_project_overview(cfg, entity, project):
    """Retourne le frontmatter overview.md du projet."""
    p = cfg.path("project_dir", entity=entity, project=project) / "overview.md"
    if not p.is_file():
        sys.exit(f"ERREUR : overview.md introuvable pour {entity}/{project}")
    content = p.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {p}")
    return yaml.safe_load(m.group(1)) or {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", required=True)
    ap.add_argument("--type", default="feature", choices=list(TYPE_TO_TRACKER))
    ap.add_argument("--priority", default="normal", choices=list(PRIORITY_TO_ID))
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="", help="Liste csv de tags")
    ap.add_argument("--target-env", default=None)
    ap.add_argument("--project", help="Override auto-detect (format: entity/project)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()

    if args.project:
        if "/" not in args.project:
            sys.exit("ERREUR : --project doit être entity/project")
        entity, project = args.project.split("/", 1)
    else:
        det = detect_project_from_cwd(cfg)
        if not det:
            sys.exit("ERREUR : projet non détecté depuis cwd, utilise --project entity/project")
        entity, project = det

    fm_proj = load_project_overview(cfg, entity, project)
    rm_proj_id = (fm_proj.get("redmine") or {}).get("project_id")
    if not rm_proj_id:
        sys.exit(f"ERREUR : project_id Redmine manquant dans overview.md de {entity}/{project}")

    tracker_id = TYPE_TO_TRACKER[args.type]
    priority_id = PRIORITY_TO_ID[args.priority]

    if args.dry_run:
        print(f"--dry-run : POST Redmine project={rm_proj_id} tracker={tracker_id} prio={priority_id}")
        print(f"--dry-run : title={args.title!r}")
        return

    # POST Redmine
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : REDMINE_URL et REDMINE_USER_PJ1_API_KEY requis (.env)")

    payload = {"issue": {
        "project_id": rm_proj_id,
        "tracker_id": tracker_id,
        "priority_id": priority_id,
        "subject": args.title,
        "description": args.description,
    }}
    # Toujours setter le CF IA — les tickets créés depuis pm-task-add sont par
    # définition IA-trackés (cf. NORMS « Filtrage IA »).
    cf_ia_id = get_ia_cf_id()
    if cf_ia_id is not None:
        payload["issue"]["custom_fields"] = [{"id": cf_ia_id, "value": "IA"}]
    req = urllib.request.Request(
        f"{url}/issues.json",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Redmine-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ERREUR Redmine HTTP {e.code} : {e.read().decode(errors='replace')[:500]}")

    rm_id = d["issue"]["id"]
    slug = slugify(args.title) or f"task-{rm_id}"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # Build MD
    fm = {
        "schema_version": "1.9.0",
        "redmine_id": rm_id,
        "redmine_last_journal_id": None,
        "redmine_last_checked_at": None,
        "title": args.title,
        "type": args.type,
        "bootstrap_template": None,
        "parent_task": None,
        "sub_tasks": [],
        "creator": "iprospective",
        "team": [{"username": "iprospective", "email": "mathieu@iprospective.fr", "role": "owner"}],
        "status": "a_faire",
        "close_reason": None,
        "completion_pct": 0,
        "priority": args.priority,
        "roi": {"immediate_benefit": 3, "monthly_benefit": 3},
        "estimate": {"difficulty": "medium", "time_minutes": 60, "tokens": None,
                     "confidence": 0.5, "estimated_by": "pm-task-add", "estimated_at": now},
        "depends_on": [], "blocks": [], "relates": [], "refs": [],
        "target_env": args.target_env,
        "test_url": None,
        "git": {"repo": None, "branch": None, "mr_url": None},
        "deploy_actions": [],
        "tokens_total": 0, "time_total_minutes": 0,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "due": None, "updated": now,
        "status_history": [{"status": "a_faire", "at": now, "by": "iprospective",
                            "model": None, "tokens": None, "duration_minutes": None}],
        "pistes": [],
        "tags": tags,
    }
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    desc = args.description or "_(pas de description fournie au moment de la création)_"
    md = f"---\n{fm_yaml}\n---\n\n## Contexte\n\n{desc}\n\n## Critères d'acceptation\n\n- [ ] (à compléter)\n"

    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    md_path = tasks_dir / f"RM{rm_id}_{slug}.md"
    log_path = tasks_dir / f"RM{rm_id}_{slug}.log.md"
    md_path.write_text(md, encoding="utf-8")
    log_path.write_text(f"# Journal RM{rm_id}\n\n## {now} — Création (pm-task-add)\nTokens : 0 | Durée : 0 min\n\nTâche créée via pm-task-add.py.\n", encoding="utf-8")

    print(f"✓ RM{rm_id} créé sur Redmine + MD/log écrits :")
    print(f"  {md_path.relative_to(cfg.projects_root)}")

    # Validate
    try:
        import subprocess
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "validate-task.py"), str(md_path)],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"⚠ validate-task.py warnings :\n{r.stdout}{r.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"⚠ validate-task.py non exécuté : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
