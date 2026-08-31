#!/usr/bin/env python3
"""Ordonnancement des tâches par ROI.

Scanne les fichiers de tâches d'un répertoire (récursif), filtre celles en
status=a_faire dont toutes les dépendances sont ferme, calcule un score ROI,
et affiche le classement décroissant.

Score en EUROS (RM1717) : privilégie les gains quantitatifs `roi.*_gain_eur`
quand ils sont renseignés, retombe sur l'échelle qualitative 1-5 sinon
(1 point ≙ BENEFIT_POINT_EUR €) :

    gain_eur = (immediate_gain_eur | immediate_benefit×BENEFIT_POINT_EUR)
             + (monthly_gain_eur | monthly_benefit×BENEFIT_POINT_EUR) × 12
    cout_eur = time_minutes / 60 × human_hourly_rate_eur (pm.pricing.yml)
    Score    = gain_eur × priority_weight / max(cout_eur, 1)

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_markdown import read_frontmatter as parse_frontmatter  # RM2764 : foyer unique


PRIORITY_WEIGHTS = {"low": 0.5, "normal": 1.0, "high": 2.0, "urgent": 4.0}
# Équivalence € d'un point de bénéfice qualitatif (échelle 1-5) — repli quand
# les gains € ne sont pas renseignés. Taux horaire humain lu dans pm.pricing.yml.
BENEFIT_POINT_EUR = 100.0
DEFAULT_HOURLY_RATE_EUR = 80.0


def hourly_rate_eur() -> float:
    """human_hourly_rate_eur depuis pm.pricing.yml (racine du repo PM)."""
    f = Path(__file__).resolve().parent.parent / "pm.pricing.yml"
    try:
        cfg = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        return float(cfg.get("human_hourly_rate_eur") or DEFAULT_HOURLY_RATE_EUR)
    except (OSError, yaml.YAMLError, TypeError, ValueError):
        return DEFAULT_HOURLY_RATE_EUR
TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")


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


def task_score(fm: dict, rate_eur: float = DEFAULT_HOURLY_RATE_EUR) -> float:
    """ROI en € : gains quantitatifs prioritaires, échelle 1-5 en repli (RM1717)."""
    roi = fm.get("roi") or {}

    def gain(eur_key, scale_key):
        eur = roi.get(eur_key)
        if eur is not None:
            return float(eur)
        return float(roi.get(scale_key) or 0) * BENEFIT_POINT_EUR

    gain_eur = gain("immediate_gain_eur", "immediate_benefit") \
             + gain("monthly_gain_eur", "monthly_benefit") * 12
    weight = PRIORITY_WEIGHTS.get(fm.get("priority", "normal"), 1.0)
    estimate = fm.get("estimate") or {}
    time_min = float(estimate.get("time_minutes") or 60)
    cout_eur = time_min / 60 * rate_eur
    return gain_eur * weight / max(cout_eur, 1)


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

    rate = hourly_rate_eur()
    all_tasks = collect_tasks(root)
    tasks_by_id = {fm.get("redmine_id"): fm for _, fm in all_tasks if fm.get("redmine_id")}

    eligible = []
    for path, fm in all_tasks:
        if not args.all_statuses and fm.get("status") != "a_faire":
            continue
        if not deps_satisfied(fm, tasks_by_id):
            continue
        eligible.append((task_score(fm, rate), path, fm))

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
