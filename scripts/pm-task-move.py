#!/usr/bin/env python3
"""pm-task-move — DÉPLACE une tâche d'un projet PM vers un autre (fichiers + Redmine).

Un ticket ouvert dans le mauvais projet — ou déplacé côté Redmine par un humain —
laissait jusqu'ici sa fiche PM orpheline dans le projet d'origine, sans outil pour
la remettre en place (NORMS tripwire #1 : « pas d'outil = trou à combler, pas une
exception manuelle »). Incident fondateur : RM2865, créé dans `pm-ai-agents` puis
déplacé dans l'UI Redmine vers `calicote/dolibarr`.

    pm-task-move.py 2865 --to calicote/dolibarr
    pm-task-move.py 2865 --to calicote/dolibarr --dry-run
    pm-task-move.py 2865 --to calicote-dolibarr --no-redmine   # fichiers seuls

Ce qui bouge :
  - `RM<id>_<slug>.md`, son `.log.md` et son `.reporting.yml` (si présent) ;
  - le `project_id` Redmine, **vérifié par relecture** (sans « Move issues »,
    Redmine répond 204 et drop l'attribut — l'échec serait muet) ;
  - un commit path-scopé **de chaque côté** : les dossiers `tasks/` source et cible
    n'appartiennent pas forcément au même dépôt de données PM.

Ce qui NE bouge pas : une branche de code (`git.branch`) ne se déplace pas de dépôt
— la présence de ce champ bloque, sauf `--force`.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pm_markdown import read_frontmatter
from pm_output import out
from pm_paths import PMConfig
from pm_task import get_task_provider
import pm_git
import redmine_utils

TOOL = "pm-task-move"


def project_redmine_id(cfg, entity, project):
    """`project_id` Redmine du projet PM (bloc `providers.task` primaire, sinon
    legacy `redmine:`). Même lecture que pm-task-add / pm-task-import."""
    try:
        meta = cfg.project_meta(entity, project) or {}
    except Exception:                                            # noqa: BLE001
        return None
    for entry in ((meta.get("providers") or {}).get("task") or []):
        if isinstance(entry, dict) and entry.get("role", "primary") == "primary":
            return entry.get("project_id")
    return (meta.get("redmine") or {}).get("project_id")


def task_files(md_path):
    """(md, log, reporting) — le reporting n'existe que si la tâche a été tickée."""
    stem = md_path.name[:-3]
    return (md_path,
            md_path.parent / f"{stem}.log.md",
            md_path.parent / f"{stem}.reporting.yml")


def append_log(log_path, message):
    """Journal append-only (NORMS) — format d'entrée imposé."""
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    entry = (f"\n## {ts} — Déplacement ({TOOL})\nTokens : 0 | Durée : 0 min\n\n"
             f"{message}\n")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


def commit_move(src_files, dst_files, rm_id, src_ref, dst_ref):
    """Commits path-scopés, groupés par dépôt.

    Source et cible peuvent vivre dans DEUX dépôts de données distincts (un
    workspace par projet) : dans ce cas deux commits, la suppression d'un côté et
    l'ajout de l'autre. Même dépôt ⇒ un seul commit, que git lit comme un rename.
    """
    src_root = pm_git.repo_root(src_files[0].parent)
    dst_root = pm_git.repo_root(dst_files[0].parent)
    shas = []
    if src_root and dst_root and src_root == dst_root:
        shas.append(pm_git.autocommit(
            list(src_files) + list(dst_files),
            f"pm(move): RM{rm_id} {src_ref} → {dst_ref}", allow_missing=True))
    else:
        shas.append(pm_git.autocommit(
            list(dst_files), f"pm(move): RM{rm_id} arrivée depuis {src_ref}"))
        shas.append(pm_git.autocommit(
            list(src_files), f"pm(move): RM{rm_id} sortie vers {dst_ref}",
            allow_missing=True))
    return [s for s in shas if s]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int, help="Id du ticket à déplacer")
    ap.add_argument("--to", required=True, metavar="REF",
                    help="Projet cible : `client/slug` ou un `redmine.project_id` "
                         "(un slug nu ambigu est refusé — NORMS tripwire #14)")
    ap.add_argument("--no-redmine", action="store_true",
                    help="Ne touche pas au projet Redmine (fichiers seuls)")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Déplace même si la tâche porte une branche de code")
    ap.add_argument("--dry-run", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    rm_id = args.rm_id

    md_path, src_ent, src_proj = cfg.locate_task(rm_id)
    if not md_path:
        out.fail(f"RM{rm_id} n'a pas de fiche PM",
                 remede=f"pm-task-import.py {rm_id} --project <client>/<projet> "
                        f"— le déplacement suppose une fiche existante")
    src_ref = f"{src_ent}/{src_proj}"

    try:
        dst_ent, dst_proj, _ = cfg.resolve_project_ref(args.to, require_redmine=True)
    except ValueError as e:
        out.fail(str(e))
    dst_ref = f"{dst_ent}/{dst_proj}"

    if (src_ent, src_proj) == (dst_ent, dst_proj):
        out.fail(f"RM{rm_id} est déjà dans {dst_ref} — rien à déplacer")

    fm = read_frontmatter(md_path) or {}
    branch = (fm.get("git") or {}).get("branch")
    if branch and not args.force:
        out.fail(f"RM{rm_id} porte une branche de code ({branch}) — une branche ne "
                 f"se déplace pas de dépôt",
                 remede="livrer ou abandonner la branche d'abord, ou --force si la "
                        "tâche change de projet PM sans changer de dépôt de code")

    src_files = task_files(md_path)
    dst_dir = cfg.path("tasks_dir", entity=dst_ent, project=dst_proj)
    dst_files = tuple(dst_dir / f.name for f in src_files)

    clash = [f.name for f in dst_files if f.exists()]
    if clash:
        out.fail(f"{dst_ref} contient déjà : {', '.join(clash)}",
                 remede="conflit à trancher à la main — l'outil ne remplace jamais "
                        "une fiche existante")

    # ── Redmine : que faut-il faire, et est-ce déjà fait ? ────────────────
    declared = project_redmine_id(cfg, dst_ent, dst_proj)
    rm_action, provider, target, needs_move = "ignoré (--no-redmine)", None, None, False
    if not args.no_redmine:
        provider = get_task_provider(cfg.project_meta(dst_ent, dst_proj))
        if not provider.capabilities.move_project:
            out.fail(f"le backend « {provider.name} » ne sait pas déplacer un ticket "
                     f"de projet", remede="--no-redmine pour ne bouger que les fichiers")
        target = redmine_utils.fetch_project(declared,
                                             creds=getattr(provider, "creds", None))
        if not target:
            out.fail(f"projet Redmine '{declared}' (déclaré par {dst_ref}) introuvable")
        current = (provider.fetch_issue(rm_id).get("project") or {})
        needs_move = str(current.get("id")) != str(target["id"])
        rm_action = (f"{current.get('name')} (#{current.get('id')}) → "
                     f"{target.get('name')} (#{target['id']})") if needs_move else \
                    f"déjà dans « {target.get('name')} » — aucune écriture"

    if args.dry_run:
        out.op("move (dry-run)", rm=rm_id, extra=f"{src_ref} → {dst_ref}")
        out.info(f"  fichiers : {', '.join(f.name for f in src_files if f.exists())}")
        out.info(f"  redmine  : {rm_action}")
        return

    # ── Redmine d'abord : si le déplacement échoue, les fichiers n'ont pas bougé
    if needs_move:
        ok, err = provider.move_project(
            rm_id, target["id"],
            notes=f"Déplacement de projet : {src_ref} → {dst_ref} (via {TOOL}).")
        if not ok:
            out.fail(f"déplacement Redmine refusé : {err}",
                     remede="corriger les droits, ou --no-redmine pour ne déplacer "
                            "que les fichiers (la divergence resterait à résorber)")

    # ── Fichiers ─────────────────────────────────────────────────────────
    dst_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for src, dst in zip(src_files, dst_files):
        if src.exists():
            src.replace(dst)
            moved.append(dst)

    append_log(dst_files[1], f"Fiche déplacée de `{src_ref}` vers `{dst_ref}` "
                             f"({TOOL}). Côté Redmine : {rm_action}.")

    shas = [] if args.no_commit else commit_move(src_files, dst_files, rm_id,
                                                 src_ref, dst_ref)
    out.op("move", rm=rm_id, extra=f"{src_ref} → {dst_ref}",
           commit=(shas[0] if shas else None))
    out.info(f"  fichiers : {', '.join(f.name for f in moved)}")
    out.info(f"  redmine  : {rm_action}")


if __name__ == "__main__":
    main()
