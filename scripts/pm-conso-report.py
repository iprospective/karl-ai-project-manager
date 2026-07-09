#!/usr/bin/env python3
"""Compte-rendu de consommation tokens / coût / temps (RM1764).

Agrège les métriques de worklog du frontmatter des tâches PM (alimentées par le
hook Stop `pm-task-tick.py`, cf. NORMS § ROI assisté par IA) : `tokens_total`,
`cost_total_usd`, `tokens_breakdown.*`, `ai_time_total_minutes`,
`human_time_total_minutes`, `time_total_minutes`.

Dimensions d'agrégation (`--by`) : `project`, `client`, `type`, `status`,
`day`, `week`, `month` (temporel = champ `updated`). Toujours affiché : un
total global + le top-N des tickets les plus coûteux.

Périmètre = tous les projets PM (via `PMConfig.iter_projects`, qui suit les
symlinks de bascule et déduplique) ; filtrable par entité/projet.

Usage :
    ./pm-conso-report.py                       # tout, groupé par projet
    ./pm-conso-report.py --by type             # par typologie de ticket
    ./pm-conso-report.py --by month --top 15   # par mois + 15 tickets top
    ./pm-conso-report.py --status ferme        # seulement la conso livrée
    ./pm-conso-report.py --entity iprospective # une entité ; --project pm-ai-agents
    ./pm-conso-report.py --json                # sortie machine (JSON)
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TASK_FILENAME = re.compile(r"^RM\d+_[a-z0-9-]+\.md$")
DIMENSIONS = ("project", "client", "type", "status", "day", "week", "month")


def parse_frontmatter(path: Path) -> dict | None:
    try:
        m = FRONTMATTER_PATTERN.match(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not m:
        return None
    try:
        d = yaml.safe_load(m.group(1))
        return d if isinstance(d, dict) else None
    except yaml.YAMLError:
        return None


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _client_project(path: Path) -> tuple[str, str]:
    """clients/<C>/projects/<P>/tasks/RM….md → (C, P)."""
    parts = path.parts
    try:
        i = parts.index("clients")
        return parts[i + 1], parts[i + 3]
    except (ValueError, IndexError):
        return "?", "?"


def _iso_week(day: str) -> str:
    """'YYYY-MM-DD…' → 'YYYY-Www' (semaine ISO). '?' si non parsable."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(day))
    if not m:
        return "?"
    import datetime
    y, mo, d = map(int, m.groups())
    try:
        iso = datetime.date(y, mo, d).isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except ValueError:
        return "?"


def dimension_key(r: dict, by: str) -> str:
    fm = r["fm"]
    if by == "type":
        return fm.get("type") or "?"
    if by == "status":
        return fm.get("status") or "?"
    if by == "client":
        return r.get("client") or "?"
    if by == "project":
        return f"{r.get('client') or '?'}/{r.get('project') or '?'}"
    updated = str(fm.get("updated") or "")
    if by == "day":
        return updated[:10] or "?"
    if by == "month":
        return updated[:7] or "?"
    if by == "week":
        return _iso_week(updated)
    return "?"


def _row(f: Path, fm: dict, client: str | None, project: str | None) -> dict:
    bd = fm.get("tokens_breakdown") if isinstance(fm.get("tokens_breakdown"), dict) else {}
    if client is None:
        client, project = _client_project(f)
    return {
        "path": f, "fm": fm, "client": client, "project": project,
        "rm_id": fm.get("redmine_id"),
        "title": fm.get("title") or "",
        "tokens": _num(fm.get("tokens_total")),
        "cost": _num(fm.get("cost_total_usd")),
        "ai_min": _num(fm.get("ai_time_total_minutes")),
        "human_min": _num(fm.get("human_time_total_minutes")),
        "in": _num(bd.get("input")), "out": _num(bd.get("output")),
        "cache_read": _num(bd.get("cache_read")),
        "cache_creation": _num(bd.get("cache_creation")),
    }


def collect_via_config(cfg, entity=None, project=None) -> list[dict]:
    """Voie canonique : itère les projets via PMConfig (suit les symlinks de
    bascule RM1949, dédup par cible) puis lit les tâches de chaque tasks_dir."""
    rows = []
    for ent, proj, _ in cfg.iter_projects(entity=entity):
        if project and proj != project:
            continue
        try:
            tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        except KeyError:
            continue
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md") or not TASK_FILENAME.match(f.name):
                continue
            fm = parse_frontmatter(f)
            if fm:
                rows.append(_row(f, fm, ent, proj))
    return rows




def fmt_tokens(n: float) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f}G"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return f"{int(n)}"


def fmt_min(m: float) -> str:
    m = round(m)
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m}min"


def aggregate(rows: list[dict], by: str) -> dict:
    agg = {}
    for r in rows:
        k = dimension_key(r, by)
        a = agg.setdefault(k, {"n": 0, "tokens": 0.0, "cost": 0.0,
                               "ai_min": 0.0, "human_min": 0.0})
        a["n"] += 1
        for f in ("tokens", "cost", "ai_min", "human_min"):
            a[f] += r[f]
    return agg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entity", help="Restreindre à une entité (client/produit/self)")
    ap.add_argument("--project", dest="project", help="Restreindre à un projet (avec --entity)")
    ap.add_argument("--by", default="project", choices=DIMENSIONS,
                    help="Dimension d'agrégation (défaut : project)")
    ap.add_argument("--status", action="append",
                    help="Ne garder que ce(s) statut(s) (répétable)")
    ap.add_argument("--type", action="append",
                    help="Ne garder que ce(s) type(s) (répétable)")
    ap.add_argument("--top", type=int, default=10, help="Top-N tickets les plus coûteux (défaut : 10)")
    ap.add_argument("--json", action="store_true", help="Sortie JSON (machine)")
    args = ap.parse_args()

    from pm_paths import PMConfig
    rows = collect_via_config(PMConfig.load(), entity=args.entity, project=args.project)
    if args.status:
        rows = [r for r in rows if r["fm"].get("status") in set(args.status)]
    if args.type:
        rows = [r for r in rows if r["fm"].get("type") in set(args.type)]
    # Ne garder que les tâches qui ont réellement consommé.
    rows = [r for r in rows if r["tokens"] or r["cost"]]

    agg = aggregate(rows, args.by)
    total = {"n": len(rows),
             "tokens": sum(r["tokens"] for r in rows),
             "cost": sum(r["cost"] for r in rows),
             "ai_min": sum(r["ai_min"] for r in rows),
             "human_min": sum(r["human_min"] for r in rows)}
    top = sorted(rows, key=lambda r: r["cost"], reverse=True)[: args.top]

    if args.json:
        print(json.dumps({
            "by": args.by,
            "total": total,
            "groups": {k: v for k, v in sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True)},
            "top": [{"rm_id": r["rm_id"], "title": r["title"], "tokens": r["tokens"],
                     "cost": round(r["cost"], 4), "ai_min": r["ai_min"]} for r in top],
        }, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("Aucune tâche avec consommation enregistrée sur ce périmètre.")
        return

    print(f"Consommation — {total['n']} ticket(s) — par {args.by}")
    print(f"{'':<28}{'tickets':>8}{'tokens':>10}{'coût $':>10}{'IA':>9}{'humain':>9}")
    print("-" * 74)
    for k, a in sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True):
        print(f"{k[:27]:<28}{a['n']:>8}{fmt_tokens(a['tokens']):>10}"
              f"{a['cost']:>10.2f}{fmt_min(a['ai_min']):>9}{fmt_min(a['human_min']):>9}")
    print("-" * 74)
    print(f"{'TOTAL':<28}{total['n']:>8}{fmt_tokens(total['tokens']):>10}"
          f"{total['cost']:>10.2f}{fmt_min(total['ai_min']):>9}{fmt_min(total['human_min']):>9}")

    if top:
        print(f"\nTop {len(top)} tickets par coût :")
        for r in top:
            rm = f"RM{r['rm_id']}" if r["rm_id"] else "RM?"
            print(f"  {rm:>8}  ${r['cost']:>7.2f}  {fmt_tokens(r['tokens']):>7}  {r['title'][:52]}")


if __name__ == "__main__":
    main()
