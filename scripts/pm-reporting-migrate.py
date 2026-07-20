#!/usr/bin/env python3
"""pm-reporting-migrate — externalise l'historique reporting vers le ledger annexe (RM2366).

Pour chaque tâche : déplace `reporting.time_entries[]`, `reporting.notes[]` et
le gros de `status_history[]` du frontmatter vers `<stem>.reporting.yml`
(pm_reporting.sweep — idempotent, dédup par clés). Le frontmatter garde les
cumuls, le marqueur `reporting.ledger` et la dernière entrée de statut
(contrat validate-task). Optimistic locking : `updated` relu avant écriture.

Usage :
    pm-reporting-migrate.py --rm-id 2316            # une tâche (dry-run)
    pm-reporting-migrate.py --all --apply           # tout le parc, commit par repo
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
import pm_git
import pm_reporting

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def migrate_one(md_path, apply):
    raw = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(raw)
    if not m:
        return ("no-fm", 0)
    fm = yaml.safe_load(m.group(2)) or {}
    rep = fm.get("reporting") or {}
    pending = len(rep.get("time_entries") or []) + len(rep.get("notes") or []) \
        + max(0, len(fm.get("status_history") or []) - 1)
    if not pending and rep.get("ledger"):
        return ("uptodate", 0)
    if not apply:
        return ("would-migrate", pending)
    updated_before = fm.get("updated")
    moved, _ = pm_reporting.sweep(fm, md_path)
    # optimistic locking : relire `updated` sur disque avant d'écrire le MD
    raw2 = md_path.read_text(encoding="utf-8")
    m2 = FM_RE.match(raw2)
    fm2 = yaml.safe_load(m2.group(2)) or {}
    if fm2.get("updated") != updated_before:
        return ("collision", 0)
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                              default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_yaml.rstrip()}{m.group(3)}{m.group(4)}",
                       encoding="utf-8")
    return ("migrated", moved)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rm-id", type=int)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Écrire (défaut : dry-run)")
    ap.add_argument("--no-commit", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    if args.rm_id:
        p = cfg.find_task(args.rm_id)
        if not p:
            out.fail(f"RM{args.rm_id} introuvable")
        targets = [p]
    else:
        targets = sorted(cfg.projects_root.glob("clients/*/projects/*/tasks/RM*_*.md"))
        targets = [p for p in targets if not p.name.endswith(".log.md")]

    stats, written = {}, []
    for p in targets:
        try:
            status, moved = migrate_one(p, args.apply)
        except Exception as e:
            status, moved = "error", 0
            out.warn(f"{p.name} : {e}")
        stats[status] = stats.get(status, 0) + 1
        if status == "migrated":
            written.append(p)
            out.info(f"✓ {p.name} : {moved} entrée(s) → {pm_reporting.ledger_path(p).name}")
        elif status == "would-migrate" and moved:
            out.info(f"→ {p.name} : {moved} entrée(s) à migrer")
        elif status == "collision":
            out.warn(f"{p.name} : collision updated (autre session) — relancer")

    if args.apply and written and not args.no_commit:
        by_root = {}
        for p in written:
            root = pm_git.repo_root(p)
            if root:
                by_root.setdefault(root, []).extend([p, pm_reporting.ledger_path(p)])
        for root, paths in by_root.items():
            pm_git.autocommit(paths, f"pm(reporting): migration ledger annexe "
                                     f"({len(paths)//2} ticket(s)) [RM2366]")
    out.op("migration", extra=" ".join(f"{k}={v}" for k, v in sorted(stats.items()))
           + ("" if args.apply else " (dry-run)"))


if __name__ == "__main__":
    main()
