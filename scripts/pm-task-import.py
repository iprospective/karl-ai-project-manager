#!/usr/bin/env python3
"""pm-task-import — ADOPTE un ticket Redmine existant en fiche PM locale.

Miroir de `pm-task-add` : celui-là CRÉE un ticket, celui-ci en adopte un qui existe
déjà côté Redmine mais n'a jamais eu de fiche (`RM<id>_<slug>.md` + `.log.md`).
Aucune écriture côté Redmine — la seule modification est locale.

À quoi ça sert (RM2626 / [[Cdc-rm2626-tickets-partenaires]]) : rattacher un ticket
ANCIEN à un ticket de partenaire (`pm-task-partner link`) suppose une fiche, puisque
le lien vit dans son frontmatter. Sans adoption, tout le parc antérieur au système de
fichiers PM — la plupart des tickets Pisceen et MatNat — reste hors d'atteinte.

  pm-task-import.py 440 --project matnat/infra
  pm-task-import.py 440 --project matnat/infra --dry-run
  pm-task-import.py 440 --type infrastructure       # le tracker « Tâche » est ambigu

Après écriture, `pm-task-sync.py` est enchaîné : c'est LUI qui aligne statut,
priorité, échéance et journal sur Redmine (source unique du mapping des statuts —
ne pas le réimplémenter ici).
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pm_paths import PMConfig
from pm_output import out
from pm_task import get_task_provider
from pm_task_md import (TYPE_TO_TRACKER, build_frontmatter, priority_id_to_name,
                        render_log, render_md, slugify, tracker_to_type)
import pm_git


def project_redmine_id(cfg, entity, project):
    """`project_id` Redmine déclaré par le projet PM (identifiant textuel ou id).

    Lu depuis le manifeste (`meta.yml`, sinon frontmatter d'`overview.md`) via le
    même accès que pm-task-add — bloc `providers.task` primaire, ou legacy `redmine:`.
    """
    try:
        meta = cfg.project_meta(entity, project) or {}
    except Exception:                                            # noqa: BLE001
        return None
    for entry in ((meta.get("providers") or {}).get("task") or []):
        if isinstance(entry, dict) and entry.get("role", "primary") == "primary":
            return entry.get("project_id")
    return (meta.get("redmine") or {}).get("project_id")


def same_project(declared, issue_project):
    """Le ticket appartient-il bien au projet PM visé ?

    L'overview déclare tantôt l'identifiant textuel, tantôt l'id numérique : on
    compare aux deux formes rendues par l'API. Comparaison lâche (str) volontaire.
    """
    if declared is None:
        return None                                              # rien de déclaré → on ne tranche pas
    cands = {str(issue_project.get("id")), str(issue_project.get("identifier") or "")}
    return str(declared) in {c for c in cands if c}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int, help="Id du ticket Redmine à adopter")
    ap.add_argument("--project", help="entity/project (défaut : détecté depuis cwd)")
    ap.add_argument("--type", choices=list(TYPE_TO_TRACKER),
                    help="Type NORMS (défaut : déduit du tracker, `autre` si ambigu)")
    ap.add_argument("--tags", default="", help="Liste csv de tags")
    ap.add_argument("--force", action="store_true",
                    help="Adopter même si le ticket appartient à un AUTRE projet Redmine "
                         "que celui visé (à n'utiliser qu'en connaissance de cause)")
    ap.add_argument("--no-sync", action="store_true",
                    help="Ne pas enchaîner pm-task-sync (la fiche reste en `nouveau`, "
                         "sans le journal distant)")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()
    rm_id = args.rm_id

    existing, ent_e, proj_e = cfg.locate_task(rm_id)
    if existing:
        out.fail(f"RM{rm_id} a déjà une fiche PM ({ent_e}/{proj_e})",
                 remede=f"pm-task-show.py {rm_id} — l'adoption ne concerne que les "
                        f"tickets qui n'en ont pas")

    if args.project:
        entity, project = args.project.split("/", 1)
    else:
        det = cfg.detect_project_from_cwd()
        if not det:
            out.fail("projet non détecté depuis cwd",
                     remede="--project entity/project")
        entity, project = det

    issue = get_task_provider().fetch_issue(rm_id)
    if not issue:
        out.fail(f"ticket {rm_id} introuvable côté Redmine")

    declared = project_redmine_id(cfg, entity, project)
    ok = same_project(declared, issue.get("project") or {})
    if ok is False and not args.force:
        rp = (issue.get("project") or {})
        out.fail(f"RM{rm_id} appartient au projet Redmine "
                 f"« {rp.get('name')} » (id {rp.get('id')}), or {entity}/{project} "
                 f"déclare project_id={declared!r}",
                 remede="corriger --project, ou --force si l'écart est voulu")
    if ok is None:
        out.warn(f"{entity}/{project} ne déclare pas de redmine.project_id — "
                 f"appartenance non vérifiée")

    title = issue.get("subject") or f"RM{rm_id}"
    ttype = args.type or tracker_to_type((issue.get("tracker") or {}).get("id"))
    priority = priority_id_to_name((issue.get("priority") or {}).get("id"))
    created = (issue.get("created_on") or "")[:10] or None
    slug = slugify(title) or f"task-{rm_id}"
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if args.dry_run:
        out.op("import (dry-run)", rm=rm_id, extra=f"{entity}/{project} · {slug}")
        out.info(f"  titre    : {title}")
        out.info(f"  type     : {ttype} (tracker {(issue.get('tracker') or {}).get('name')})")
        out.info(f"  priorité : {priority} · créé le {created}")
        out.info(f"  statut Redmine : {(issue.get('status') or {}).get('name')} "
                 f"(appliqué par pm-task-sync)")
        return

    fm = build_frontmatter(rm_id, title, type=ttype, priority=priority,
                           tags=[t.strip() for t in args.tags.split(",") if t.strip()],
                           created=created, now=now, estimated_by="pm-task-import")
    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    md_path = tasks_dir / f"RM{rm_id}_{slug}.md"
    log_path = tasks_dir / f"RM{rm_id}_{slug}.log.md"
    md_path.write_text(render_md(fm, issue.get("description") or ""), encoding="utf-8")
    log_path.write_text(render_log(
        rm_id, now, title="Adoption (pm-task-import)",
        body=f"Fiche PM créée pour un ticket Redmine PRÉEXISTANT "
             f"(créé le {created}). Aucune écriture côté Redmine.\n"
             f"Statut, priorité et journal sont alignés par pm-task-sync."),
        encoding="utf-8")
    out.op("import", rm=rm_id, extra=f"{entity}/{project} · {slug}")

    if not args.no_sync:
        r = subprocess.run([sys.executable, str(HERE / "pm-task-sync.py"), str(rm_id)],
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            out.warn(f"pm-task-sync a échoué (exit {r.returncode}) — la fiche reste "
                     f"en `nouveau` : {(r.stdout + r.stderr).strip()[:300]}")
        else:
            out.info("  · statut/priorité/journal alignés sur Redmine (pm-task-sync)")

    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(import): RM{rm_id} adopté dans {entity}/{project}")


if __name__ == "__main__":
    main()
