#!/usr/bin/env python3
"""Ordonnancement des tâches par ROI.

Scanne les fichiers de tâches d'un répertoire (récursif), filtre celles en
status=a_faire dont toutes les dépendances sont ferme, calcule un score ROI,
et affiche le classement décroissant.

Score = (immediate_benefit + monthly_benefit * 12) * priority_weight / max(time_minutes, 1)

Usage :
    ./scripts/priority.py <chemin>                # scan récursif d'un répertoire
    ./scripts/priority.py "$PROJECTS_PATH"        # scan global
    ./scripts/priority.py "$PROJECTS_PATH" --top 10
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


PRIORITY_WEIGHTS = {"low": 0.5, "normal": 1.0, "high": 2.0, "urgent": 4.0}
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")


def parse_frontmatter(file_path: Path) -> dict | None:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None
    m = FRONTMATTER_PATTERN.match(content)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None


def collect_tasks(root: Path) -> list[tuple[Path, dict]]:
    tasks = []
    for f in root.rglob("*.md"):
        if f.name.endswith(".log.md"):
            continue
        if not TASK_FILENAME.match(f.name):
            continue
        fm = parse_frontmatter(f)
        if fm and isinstance(fm, dict):
            tasks.append((f, fm))
    return tasks


def task_score(fm: dict) -> float:
    roi = fm.get("roi") or {}
    immediate = float(roi.get("immediate_benefit") or 0)
    monthly = float(roi.get("monthly_benefit") or 0)
    weight = PRIORITY_WEIGHTS.get(fm.get("priority", "normal"), 1.0)
    estimate = fm.get("estimate") or {}
    time_min = float(estimate.get("time_minutes") or 60)
    return (immediate + monthly * 12) * weight / max(time_min, 1)


def deps_satisfied(fm: dict, tasks_by_id: dict) -> bool:
    for dep_id in fm.get("depends_on") or []:
        dep_fm = tasks_by_id.get(dep_id)
        if dep_fm is None:
            return False
        if dep_fm.get("status") != "ferme":
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="Répertoire à scanner (récursif)")
    ap.add_argument("--top", type=int, default=20, help="Nombre de tâches à afficher (défaut : 20)")
    ap.add_argument("--all-statuses", action="store_true", help="Inclure tous les statuts, pas seulement a_faire")
    args = ap.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"ERREUR : {root} n'existe pas", file=sys.stderr)
        sys.exit(1)

    all_tasks = collect_tasks(root)
    tasks_by_id = {fm.get("redmine_id"): fm for _, fm in all_tasks if fm.get("redmine_id")}

    eligible = []
    for path, fm in all_tasks:
        if not args.all_statuses and fm.get("status") != "a_faire":
            continue
        if not deps_satisfied(fm, tasks_by_id):
            continue
        eligible.append((task_score(fm), path, fm))

    eligible.sort(key=lambda x: x[0], reverse=True)

    if not eligible:
        print("Aucune tâche éligible.")
        return

    print(f"{'Score':>8}  {'RM':>6}  {'Type':<14}  {'Pri':<7}  Titre")
    print("-" * 80)
    for score, path, fm in eligible[: args.top]:
        rm_id = fm.get("redmine_id", "?")
        ttype = fm.get("type", "?")[:14]
        prio = fm.get("priority", "?")[:7]
        title = fm.get("title", "?")[:40]
        print(f"{score:>8.2f}  {rm_id:>6}  {ttype:<14}  {prio:<7}  {title}")

    if len(eligible) > args.top:
        print(f"\n... {len(eligible) - args.top} tâche(s) supplémentaire(s)")


if __name__ == "__main__":
    main()
