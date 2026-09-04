#!/usr/bin/env python3
"""pm-stats — Résumé synthétique du système PM (depuis les MD locaux).

Affiche, sans aucun appel Redmine (l'index MD local fait foi) :
  - nombre d'entités (les « clients » sous `paths.entities_dir`), avec
    répartition par `type` (client / product / self) ;
  - nombre de projets, dont combien « en cours » (au moins un ticket actif,
    c.-à-d. non `ferme`) ;
  - nombre de tickets : total, ouverts (non `ferme`) et `en_cours`.

Tous les chemins sont résolus via `pm_paths.py` (aucun hardcode). Les
compteurs « ouverts » / total sont cohérents avec `pm-task-list` (même
définition de ticket et même statut terminal `ferme`).

Sortie :
  défaut    texte lisible en CLI (table Rich si `rich` est dispo)
  --json    objet JSON (pour scripting)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
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


# Même définition de « fichier de tâche » que pm-task-list (hors .log.md).
TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")

# Seul statut terminal (cf. NORMS § Mapping NORMS → Redmine : `ferme`).
CLOSED_STATUSES = {"ferme"}
# Alias déprécié encore présent dans d'anciens MD (cf. NORMS).
IN_PROGRESS_STATUSES = {"en_cours"}


def entity_type(cfg: PMConfig, entity: str) -> str:
    """Lit `type` dans le manifeste client (meta.yml, sinon overview) — RM1994."""
    return cfg.client_meta(entity).get("type") or "client"


def scan_project_tasks(cfg: PMConfig, entity: str, project: str):
    """Yield le `status` de chaque ticket du projet."""
    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    if not tasks_dir.is_dir():
        return
    for f in sorted(tasks_dir.iterdir()):
        if not TASK_FILENAME.match(f.name):
            continue
        fm = parse_frontmatter(f)
        if fm is None:
            continue
        yield fm.get("status")


def collect_stats(cfg: PMConfig) -> dict:
    by_type: dict = {}
    entities_total = 0
    for slug, _ in cfg.iter_entities():
        entities_total += 1
        t = entity_type(cfg, slug)
        by_type[t] = by_type.get(t, 0) + 1

    projects_total = 0
    projects_active = 0
    tickets_total = 0
    tickets_open = 0
    tickets_in_progress = 0

    for ent, proj, _ in cfg.iter_projects():
        projects_total += 1
        has_active = False
        for status in scan_project_tasks(cfg, ent, proj):
            tickets_total += 1
            if status not in CLOSED_STATUSES:
                tickets_open += 1
                has_active = True
            if status in IN_PROGRESS_STATUSES:
                tickets_in_progress += 1
        if has_active:
            projects_active += 1

    return {
        "entities": {
            "total": entities_total,
            "by_type": dict(sorted(by_type.items())),
        },
        "projects": {"total": projects_total, "active": projects_active},
        "tickets": {
            "total": tickets_total,
            "open": tickets_open,
            "en_cours": tickets_in_progress,
        },
    }


def render_text(stats: dict):
    ent = stats["entities"]
    proj = stats["projects"]
    tic = stats["tickets"]
    by_type = ", ".join(f"{k}: {v}" for k, v in ent["by_type"].items()) or "—"

    if RICH:
        table = Table(title="Stats PM", box=box.SIMPLE_HEAVY, show_header=False)
        table.add_column("Indicateur", style="cyan")
        table.add_column("Valeur", justify="right", style="bold")
        table.add_column("Détail", style="dim")
        table.add_row("Entités (clients)", str(ent["total"]), by_type)
        table.add_row("Projets", str(proj["total"]),
                      f"en cours : {proj['active']} (≥1 ticket actif)")
        table.add_row("Tickets — total", str(tic["total"]), "")
        table.add_row("Tickets — ouverts", str(tic["open"]), "non fermés")
        table.add_row("Tickets — en cours", str(tic["en_cours"]), "status=en_cours")
        console.print(table)
    else:
        print("Stats PM")
        print(f"  Entités (clients)   : {ent['total']:>4}   ({by_type})")
        print(f"  Projets             : {proj['total']:>4}   "
              f"(en cours : {proj['active']} — ≥1 ticket actif)")
        print(f"  Tickets — total     : {tic['total']:>4}")
        print(f"  Tickets — ouverts   : {tic['open']:>4}   (non fermés)")
        print(f"  Tickets — en cours  : {tic['en_cours']:>4}   (status=en_cours)")


def main():
    ap = argparse.ArgumentParser(
        description="Résumé synthétique du système PM (depuis les MD locaux).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--json", action="store_true", help="Sortie JSON")
    args = ap.parse_args()

    cfg = PMConfig.load()
    stats = collect_stats(cfg)

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        render_text(stats)


if __name__ == "__main__":
    main()
