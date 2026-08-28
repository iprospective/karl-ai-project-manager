#!/usr/bin/env python3
"""pm-task-list — Liste les tâches d'un projet PM (depuis MD).

Détection du projet :
1. `--project <entity>/<project>` explicite
2. cwd contient (ou est sous) un symlink `.mmi-pm` → suit → projet PM
3. cwd est directement sous `projects_root/clients/<E>/projects/<P>/` → déduit
4. fallback : toutes les tâches de tous les projets

Filtres :
  --status STATUS         filtre statut (peut être répété)
  --not-status STATUS     exclut un statut (peut être répété ; défaut: exclut "ferme")
  --type TYPE             filtre type (peut être répété)
  --priority PRIO         filtre priorité (peut être répété)
  --tag TAG               filtre tag (peut être répété)
  --include-closed        désactive l'exclusion par défaut de "ferme"
  --all                   ignore l'auto-détection cwd et liste TOUS les projets

Sortie :
  --json                  sortie JSON (pour scripting)
  --limit N               tronque aux N tâches les plus récemment mises à jour
                          (table uniquement ; 0 = tout)
  défaut                  table Rich (ou plain text si rich absent)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
from pm_markdown import read_frontmatter as parse_frontmatter  # RM2764 : foyer unique

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None


TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")

PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3, None: 9}
STATUS_ORDER = {
    "en_cours": 0,
    "a_corriger": 1,
    "a_tester_verifier": 2,
    "a_faire": 3,
    "etude_chiffrage_en_cours": 4,
    "a_etudier_chiffrer": 5,
    "ferme": 9,
    None: 99,
}


def detect_project_from_cwd(cfg: PMConfig):
    """Retourne (entity_slug, project_slug) ou None.

    Délègue à la détection centralisée `PMConfig.detect_project_from_cwd`
    (overview-based, gère `.mmi-pm` symlink OU dossier — RM1942).
    """
    return cfg.detect_project_from_cwd()


def scan_project_tasks(cfg: PMConfig, entity: str, project: str):
    """Yield (path, fm) pour chaque tâche du projet."""
    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    if not tasks_dir.is_dir():
        return
    for f in sorted(tasks_dir.iterdir()):
        if not TASK_FILENAME.match(f.name):
            continue
        fm = parse_frontmatter(f)
        if fm:
            yield f, fm


def collect_tasks(cfg: PMConfig, entity=None, project=None):
    """Retourne [(ent, proj, path, fm)] selon le scope."""
    out = []
    if entity and project:
        for path, fm in scan_project_tasks(cfg, entity, project):
            out.append((entity, project, path, fm))
    else:
        for ent, proj, _ in cfg.iter_projects(entity=entity):
            for path, fm in scan_project_tasks(cfg, ent, proj):
                out.append((ent, proj, path, fm))
    return out


def apply_filters(rows, args):
    out = []
    not_status = set(args.not_status or [])
    if not args.include_closed and not args.status:
        not_status.add("ferme")
    status_set = set(args.status or [])
    type_set = set(args.type or [])
    prio_set = set(args.priority or [])
    tag_set = set(args.tag or [])

    for ent, proj, path, fm in rows:
        s = fm.get("status")
        if status_set and s not in status_set:
            continue
        if not_status and s in not_status:
            continue
        if type_set and fm.get("type") not in type_set:
            continue
        if prio_set and fm.get("priority") not in prio_set:
            continue
        if tag_set:
            tags = set(fm.get("tags") or [])
            if not (tag_set & tags):
                continue
        out.append((ent, proj, path, fm))
    return out


def apply_limit(rows, limit):
    """Tronque aux `limit` tâches les plus récemment mises à jour (frontmatter
    `updated`). Retourne (rows_tronquées, nb_masquées). limit None/0 → tout."""
    if not limit or limit < 0 or len(rows) <= limit:
        return rows, 0
    recent = sorted(rows, key=lambda r: str(r[3].get("updated") or ""), reverse=True)
    keep = {id(r) for r in recent[:limit]}
    return [r for r in rows if id(r) in keep], len(rows) - limit


def sort_rows(rows):
    return sorted(
        rows,
        key=lambda r: (
            STATUS_ORDER.get(r[3].get("status"), 99),
            PRIORITY_ORDER.get(r[3].get("priority"), 9),
            r[3].get("redmine_id") or 0,
        ),
    )


def render_table(rows, scope_label, single_project):
    if RICH:
        title = f"Tâches — {scope_label}" if scope_label else "Tâches"
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        table.add_column("RM", justify="right", style="cyan")
        if not single_project:
            table.add_column("Projet", style="magenta")
        table.add_column("Statut", style="yellow")
        table.add_column("Pri", style="bold")
        table.add_column("Type")
        table.add_column("Titre")
        for ent, proj, _, fm in rows:
            row = [f"RM{fm.get('redmine_id', '?')}"]
            if not single_project:
                row.append(f"{ent}/{proj}")
            row += [
                fm.get("status", "?") or "?",
                fm.get("priority", "?") or "?",
                fm.get("type", "?") or "?",
                (fm.get("title") or "?")[:60],
            ]
            table.add_row(*row)
        console.print(table)
        console.print(f"[dim]{len(rows)} tâche(s)[/dim]")
    else:
        if scope_label:
            print(f"Tâches — {scope_label}")
        for ent, proj, _, fm in rows:
            cols = [f"RM{fm.get('redmine_id','?'):>5}"]
            if not single_project:
                cols.append(f"{ent}/{proj}")
            cols += [
                f"{fm.get('status','?'):<22}",
                f"{fm.get('priority','?'):<7}",
                f"{fm.get('type','?'):<14}",
                (fm.get("title") or "?")[:60],
            ]
            print("  " + "  ".join(cols))
        print(f"  ({len(rows)} tâche(s))")


def render_json(rows):
    data = []
    for ent, proj, path, fm in rows:
        data.append({
            "entity": ent,
            "project": proj,
            "path": str(path),
            "redmine_id": fm.get("redmine_id"),
            "title": fm.get("title"),
            "status": fm.get("status"),
            "priority": fm.get("priority"),
            "type": fm.get("type"),
            "tags": fm.get("tags") or [],
            "completion_pct": fm.get("completion_pct"),
            "target_env": fm.get("target_env"),
        })
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(
        description="Liste les tâches d'un projet PM (depuis MD).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--project", help="Cible explicite : entity/project (sinon: auto-détection cwd)")
    ap.add_argument("--status", action="append", help="Filtre statut (répétable)")
    ap.add_argument("--not-status", action="append", help="Exclut statut (défaut: ferme)")
    ap.add_argument("--type", action="append", help="Filtre type (répétable)")
    ap.add_argument("--priority", action="append", help="Filtre priorité (répétable)")
    ap.add_argument("--tag", action="append", help="Filtre tag (répétable)")
    ap.add_argument("--include-closed", action="store_true",
                    help="Inclure les tâches fermées (sinon `ferme` exclu par défaut)")
    ap.add_argument("--all", action="store_true",
                    help="Ignore l'auto-détection cwd et liste TOUS les projets")
    ap.add_argument("--json", action="store_true", help="Sortie JSON")
    ap.add_argument("--limit", type=int, default=None, metavar="N",
                    help="Tronque aux N tâches les plus récemment mises à jour "
                         "(0 = tout ; défaut : tout)")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()

    entity = project = None
    scope_label = "tous projets"
    single_project = False

    if args.project:
        if "/" not in args.project:
            sys.exit("ERREUR : --project doit être au format entity/project")
        entity, project = args.project.split("/", 1)
        scope_label = f"{entity}/{project}"
        single_project = True
    elif not args.all:
        detected = detect_project_from_cwd(cfg)
        if detected:
            entity, project = detected
            scope_label = f"{entity}/{project}"
            single_project = True

    rows = collect_tasks(cfg, entity, project)
    rows = apply_filters(rows, args)
    rows = sort_rows(rows)

    if args.json:
        render_json(rows)
    else:
        rows, hidden = apply_limit(rows, args.limit)
        render_table(rows, scope_label, single_project)
        if hidden:
            print(f"… (+{hidden} autres — --limit 0 pour tout)")


if __name__ == "__main__":
    main()
