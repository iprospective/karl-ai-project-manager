#!/usr/bin/env python3
"""PM Dashboard — vue d'ensemble du système de gestion de tâches.

Affiche : statuts globaux par projet, top ROI, en cours, à tester, activité récente.

Usage :
    ./scripts/pm-dashboard.py                    # utilise $PROJECTS_PATH
    ./scripts/pm-dashboard.py /path/to/projects  # chemin explicite
    ./scripts/pm-dashboard.py --client lemathou  # filtre client
    ./scripts/pm-dashboard.py --top 20           # top N ROI (défaut 10)
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None


PRIORITY_WEIGHTS = {"low": 0.5, "normal": 1.0, "high": 2.0, "urgent": 4.0}
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")
LOG_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.log\.md$")

STATUSES = [
    "a_etudier_chiffrer", "etude_chiffrage_en_cours", "a_faire",
    "en_cours", "a_tester_verifier", "a_corriger", "ferme",
]

STATUS_SHORT = {
    "a_etudier_chiffrer": "étud.",
    "etude_chiffrage_en_cours": "chif.",
    "a_faire": "faire",
    "en_cours": "cours",
    "a_tester_verifier": "test",
    "a_corriger": "corr.",
    "ferme": "fermé",
}


def parse_frontmatter(file_path):
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = FRONTMATTER_PATTERN.match(content)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None


def scan_clients(projects_root):
    clients_dir = projects_root / "clients"
    if not clients_dir.is_dir():
        return []
    return sorted([p for p in clients_dir.iterdir() if p.is_dir()])


def scan_projects(client_dir):
    proj_dir = client_dir / "projects"
    if not proj_dir.is_dir():
        return []
    return sorted([p for p in proj_dir.iterdir() if p.is_dir()])


def scan_tasks(project_dir):
    tasks_dir = project_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    tasks = []
    for f in sorted(tasks_dir.iterdir()):
        if not TASK_FILENAME.match(f.name):
            continue
        fm = parse_frontmatter(f)
        if fm:
            tasks.append((f, fm))
    return tasks


def task_score(fm):
    roi = fm.get("roi") or {}
    immediate = float(roi.get("immediate_benefit") or 0)
    monthly = float(roi.get("monthly_benefit") or 0)
    weight = PRIORITY_WEIGHTS.get(fm.get("priority", "normal"), 1.0)
    estimate = fm.get("estimate") or {}
    time_min = float(estimate.get("time_minutes") or 60)
    return (immediate + monthly * 12) * weight / max(time_min, 1)


def deps_satisfied(fm, tasks_by_id):
    for dep in fm.get("depends_on") or []:
        dep_fm = tasks_by_id.get(dep)
        if dep_fm is None or dep_fm.get("status") != "ferme":
            return False
    return True


def status_breakdown(tasks):
    counts = {s: 0 for s in STATUSES}
    for _, fm in tasks:
        s = fm.get("status")
        if s in counts:
            counts[s] += 1
    return counts


def recent_logs(projects_root, n=5):
    log_files = []
    for f in projects_root.rglob("*.log.md"):
        if LOG_FILENAME.match(f.name):
            try:
                mtime = f.stat().st_mtime
                log_files.append((mtime, f))
            except OSError:
                continue
    log_files.sort(reverse=True)
    return log_files[:n]


def fmt_dt(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def collect(projects_root, client_filter=None):
    """Retourne [(client_dir, project_dir, tasks), ...] et l'index par redmine_id."""
    data = []
    tasks_by_id = {}
    for c in scan_clients(projects_root):
        if client_filter and c.name != client_filter:
            continue
        for p in scan_projects(c):
            tasks = scan_tasks(p)
            data.append((c, p, tasks))
            for _, fm in tasks:
                rid = fm.get("redmine_id")
                if rid:
                    tasks_by_id[rid] = fm
    return data, tasks_by_id


def render_header(projects_root):
    if RICH:
        from rich.text import Text
        console.print(Text(f"PM Dashboard — {projects_root}", style="bold cyan"))
        console.print(Text(datetime.now().strftime("%Y-%m-%d %H:%M"), style="dim"))
        console.print()
    else:
        print(f"PM Dashboard — {projects_root}")
        print(datetime.now().strftime("%Y-%m-%d %H:%M"))
        print()


def render_overview(data):
    total_clients = len({c.name for c, _, _ in data})
    total_projects = len(data)
    total_tasks = sum(len(t) for _, _, t in data)
    msg = f"{total_clients} client(s) · {total_projects} projet(s) · {total_tasks} tâche(s)"
    if RICH:
        console.print(f"[bold]Vue d'ensemble[/bold]  {msg}")
        console.print()
    else:
        print(f"Vue d'ensemble : {msg}")
        print()


def render_status_table(data):
    if not data:
        return
    if RICH:
        table = Table(box=box.SIMPLE, show_lines=False)
        table.add_column("Client", style="cyan")
        table.add_column("Projet", style="magenta")
        for s in STATUSES:
            table.add_column(STATUS_SHORT[s], justify="right")
        table.add_column("Total", justify="right", style="bold")
        for c, p, tasks in data:
            counts = status_breakdown(tasks)
            row = [c.name, p.name] + [str(counts[s]) if counts[s] else "·" for s in STATUSES] + [str(len(tasks))]
            table.add_row(*row)
        console.print(Panel(table, title="Statuts par projet", border_style="dim"))
        console.print()
    else:
        print("Statuts par projet")
        for c, p, tasks in data:
            counts = status_breakdown(tasks)
            parts = " · ".join(f"{STATUS_SHORT[s]}={counts[s]}" for s in STATUSES if counts[s])
            print(f"  {c.name}/{p.name}: {parts or '(vide)'}")
        print()


def render_top_roi(data, tasks_by_id, top_n):
    eligible = []
    for c, p, tasks in data:
        for path, fm in tasks:
            if fm.get("status") != "a_faire":
                continue
            if not deps_satisfied(fm, tasks_by_id):
                continue
            eligible.append((task_score(fm), c.name, p.name, path, fm))
    eligible.sort(key=lambda x: x[0], reverse=True)

    if RICH:
        if eligible:
            table = Table(box=box.SIMPLE)
            table.add_column("Score", justify="right", style="yellow")
            table.add_column("RM", justify="right")
            table.add_column("Client/Projet", style="cyan")
            table.add_column("Type")
            table.add_column("Pri")
            table.add_column("Titre")
            for score, c, p, _, fm in eligible[:top_n]:
                table.add_row(
                    f"{score:.2f}",
                    f"RM{fm.get('redmine_id', '?')}",
                    f"{c}/{p}",
                    fm.get("type", "?"),
                    fm.get("priority", "?"),
                    (fm.get("title") or "?")[:50],
                )
            title = f"Top {min(len(eligible), top_n)} ROI"
            if len(eligible) > top_n:
                title += f" / {len(eligible)} éligibles"
            console.print(Panel(table, title=title, border_style="dim"))
        else:
            console.print(Panel("[dim]Aucune tâche éligible (a_faire avec dépendances satisfaites)[/dim]",
                                title="Top ROI", border_style="dim"))
        console.print()
    else:
        print("Top ROI")
        if eligible:
            for score, c, p, _, fm in eligible[:top_n]:
                print(f"  {score:6.2f}  RM{fm.get('redmine_id', '?'):>5}  {c}/{p}  "
                      f"{fm.get('type', '?'):<14}  {(fm.get('title') or '?')[:50]}")
        else:
            print("  (aucune tâche éligible)")
        print()


def render_status_list(data, status, title, border_style="green"):
    items = [(c.name, p.name, fm) for c, p, tasks in data for _, fm in tasks if fm.get("status") == status]
    if not items:
        return
    if RICH:
        table = Table(box=box.SIMPLE)
        table.add_column("RM", justify="right")
        table.add_column("Client/Projet", style="cyan")
        table.add_column("Titre")
        if status == "en_cours":
            table.add_column("Complétion", justify="right")
        for c, p, fm in items:
            row = [f"RM{fm.get('redmine_id', '?')}", f"{c}/{p}", (fm.get("title") or "?")[:50]]
            if status == "en_cours":
                row.append(f"{fm.get('completion_pct', 0)}%")
            table.add_row(*row)
        console.print(Panel(table, title=f"{title} ({len(items)})", border_style=border_style))
        console.print()
    else:
        print(f"{title} ({len(items)})")
        for c, p, fm in items:
            extra = f" ({fm.get('completion_pct', 0)}%)" if status == "en_cours" else ""
            print(f"  RM{fm.get('redmine_id', '?'):>5}  {c}/{p}  {(fm.get('title') or '?')[:50]}{extra}")
        print()


def render_activity(projects_root, n):
    recents = recent_logs(projects_root, n)
    if not recents:
        return
    if RICH:
        table = Table(box=box.SIMPLE)
        table.add_column("Modifié", style="dim")
        table.add_column("Fichier")
        for ts, f in recents:
            table.add_row(fmt_dt(ts), str(f.relative_to(projects_root)))
        console.print(Panel(table, title=f"Activité récente ({len(recents)} derniers logs)", border_style="dim"))
    else:
        print(f"Activité récente ({len(recents)} derniers logs)")
        for ts, f in recents:
            print(f"  {fmt_dt(ts)}  {f.relative_to(projects_root)}")


def main():
    ap = argparse.ArgumentParser(
        description="PM Dashboard — vue d'ensemble du système de gestion de tâches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", nargs="?", default=None,
                    help="Chemin vers projects/. Par défaut : $PROJECTS_PATH")
    ap.add_argument("--client", help="Filtrer sur un client (slug)")
    ap.add_argument("--top", type=int, default=10, help="Nombre de tâches dans Top ROI (défaut 10)")
    ap.add_argument("--activity", type=int, default=5, help="Nombre de logs récents (défaut 5)")
    args = ap.parse_args()

    path = args.path or os.environ.get("PROJECTS_PATH")
    if not path:
        print("ERREUR : passer le chemin en argument ou définir $PROJECTS_PATH", file=sys.stderr)
        sys.exit(1)

    root = Path(path).resolve()
    if not root.exists():
        print(f"ERREUR : {root} n'existe pas", file=sys.stderr)
        sys.exit(1)

    data, tasks_by_id = collect(root, client_filter=args.client)

    render_header(root)
    render_overview(data)
    render_status_table(data)
    render_top_roi(data, tasks_by_id, args.top)
    render_status_list(data, "en_cours", "En cours", border_style="green")
    render_status_list(data, "a_tester_verifier", "À tester / vérifier", border_style="yellow")
    render_status_list(data, "a_corriger", "À corriger", border_style="red")
    render_activity(root, args.activity)


if __name__ == "__main__":
    main()
