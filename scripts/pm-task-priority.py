#!/usr/bin/env python3
"""pm-task-priority — change la priorité d'un ticket : Redmine + frontmatter + log (RM3275).

Jusqu'ici la priorité ne se posait qu'à la **création** (`pm-task-add --priority`).
La corriger ensuite n'avait pas d'outil : il fallait passer par l'UI Redmine, et
le frontmatter restait en arrière jusqu'à la prochaine `pm-task-sync` — ou bien
écrire les deux à la main, ce que le tripwire #1 interdit. Le trou s'est vu le
jour où un ticket de rotation de secret devait monter en `immediat` (RM3273).

Fait, dans le même mouvement :

1. **Redmine** — PUT `priority_id`, avec une note qui dit l'avant/après et le motif ;
2. **frontmatter** — `priority` + `updated` ;
3. **`.log.md`** — une entrée datée ;
4. **auto-commit** du dépôt PM.

⚠ Garde anti-silence : sans la permission « Edit issues », Redmine répond **204
et ignore l'attribut** (cf. `knowledge/redmine/api.md`) — un succès apparent qui
laisse Redmine et le MD divergents. L'outil **relit** donc l'issue après le PUT
et refuse d'écrire le miroir local si la priorité n'a pas bougé côté serveur.

Priorités : `low` · `normal` · `high` · `urgent` · `immediat`, source unique
`redmine.reference.yml :: priorities` (via `pm_priority`). `immediat` est le cran
qui **passe devant le travail en cours** — un secret compromis, une production à
l'arrêt — pas « urgent, mais vraiment ».

Usage :
    pm-task-priority.py <RM-id>                         # affiche la priorité courante
    pm-task-priority.py <RM-id> immediat                # change
    pm-task-priority.py <RM-id> urgent --reason "MEP bloquée"
    pm-task-priority.py <RM-id> high --no-commit --cross-project
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_git
import pm_priority
import pm_scope
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("priority", nargs="?", choices=pm_priority.labels(),
                    help="Nouvelle priorité (omise : affiche la courante)")
    ap.add_argument("--reason", help="Motif, repris dans la note Redmine et le journal")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")

    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    current = pm_priority.normalize(fm.get("priority"))

    if not args.priority:
        print(f"RM{args.rm_id} : priorité {current} (id Redmine {pm_priority.to_id(current)})")
        print("  crans, du plus faible au plus fort : " + " · ".join(pm_priority.labels()))
        return

    target = args.priority
    if target == current:
        print(f"RM{args.rm_id} est déjà en priorité {target} — rien à faire.")
        return

    pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-priority")

    target_id = pm_priority.to_id(target)
    sens = "montée" if pm_priority.rank(target) > pm_priority.rank(current) else "baisse"
    note = f"Priorité : {current} → {target} ({sens})."
    if args.reason:
        note += f"\n\nMotif : {args.reason}"

    ok, err = redmine_utils.update_issue_fields(args.rm_id, priority_id=target_id, notes=note)
    if not ok:
        sys.exit(f"ERREUR : Redmine a refusé le changement de priorité — {err}")

    # Le 204 ne prouve rien : on relit pour savoir si l'attribut a bien été pris.
    issue = redmine_utils.fetch_issue(args.rm_id) or {}
    seen = (issue.get("priority") or {}).get("id")
    if seen is not None and int(seen) != target_id:
        sys.exit(f"ERREUR : Redmine a répondu OK mais la priorité est restée à l'id {seen} "
                 f"(attendu {target_id}). Permission « Edit issues » manquante ? "
                 f"Le frontmatter n'a PAS été modifié — Redmine et le MD seraient divergents.")
    print(f"✓ Redmine RM{args.rm_id} priorité {current}→{target} (id {target_id})")

    fm["priority"] = target
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter priority : {md_path.relative_to(cfg.projects_root)}")

    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Priorité : {current} → {target} (pm-task-priority)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{note}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(priority): RM{args.rm_id} {current}→{target}")


if __name__ == "__main__":
    main()
