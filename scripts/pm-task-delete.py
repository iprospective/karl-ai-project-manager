#!/usr/bin/env python3
"""pm-task-delete — SUPPRIME réellement un ticket créé par erreur (Redmine + fichiers PM).

Fermer un ticket (`pm-task-status-update … ferme --close-reason invalide`) le garde
à vie dans les listes et les recherches. Pour le bruit pur — un ticket ouvert
automatiquement sur un faux positif, un doublon sans contenu — Mathieu demande la
suppression (RM3468, à propos de RM3433/3434/3436). Aucun outil ne le faisait, et le
geste manuel dans Redmine est exclu (NORMS tripwire #1).

    pm-task-delete.py 3433 --reason "faux positif pm-secret-watch (RM3465)"           # plan
    pm-task-delete.py 3433 --reason "faux positif pm-secret-watch (RM3465)" --apply   # exécute

Dry-run par défaut : sans `--apply`, l'outil montre ce qu'il supprimerait et s'arrête.

Ordre d'exécution, choisi pour qu'un échec laisse un état cohérent :
  1. trace dans le journal PM (`pm_log`, catégorie `pm`) — AVANT de détruire, et
     hors du ticket puisque celui-ci disparaît : id, titre, projet, motif ;
  2. retrait des liens (relates/depends_on/blocks) par `pm-task-link rm`, qui nettoie
     aussi le miroir dans la fiche de l'AUTRE ticket ;
  3. suppression Redmine, vérifiée par relecture (404) ;
  4. suppression des fichiers du ticket (fiche, journal, reporting, think, script de
     MEP) et commit path-scopé ;
  5. retrait du ticket des worklogs de session (`pm-session-status rm`) : sinon le
     cockpit le garde dans « reste à faire » avec son dernier statut connu.

Refus, sauf `--force` : un ticket qui porte du travail ne se supprime pas, il se ferme.
Sont du travail : du temps saisi, des sous-tâches, des commits liés (changesets), une
branche ou une MR de code dans la fiche.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pm_markdown import read_frontmatter
from pm_output import out
from pm_paths import PMConfig
from pm_task import get_task_provider
import pm_git
import pm_log
import pm_stores

TOOL = "pm-task-delete"
LINK_FIELDS = ("relates", "depends_on", "blocks")


def task_files(md_path):
    """Fiche et frères — même liste que `pm-task-move` (fiche, journal, reporting,
    réflexion RM3053, script de MEP RM3225), réduite à ceux qui existent."""
    stem = md_path.name[:-3]
    candidates = (md_path,
                  md_path.parent / f"{stem}.log.md",
                  md_path.parent / f"{stem}.reporting.yml",
                  md_path.parent / f"{stem}.think.md",
                  md_path.parent / f"{stem}.script-mep.sh")
    return [f for f in candidates if f.exists()]


def linked_ids(fm, issue):
    """Tickets liés, d'après la fiche ET Redmine (l'un peut manquer à l'autre)."""
    ids = set()
    for field in LINK_FIELDS:
        for v in (fm.get(field) or []):
            try:
                ids.add(int(v))
            except (TypeError, ValueError):
                pass
    me = int(fm.get("redmine_id") or 0)
    for rel in (issue or {}).get("relations") or []:
        for k in ("issue_id", "issue_to_id"):
            v = rel.get(k)
            if v and int(v) != me:
                ids.add(int(v))
    return sorted(ids)


def blockers(fm, issue):
    """Ce qui fait d'un ticket autre chose que du bruit : du travail rattaché."""
    found = []
    git = fm.get("git") or {}
    if git.get("branch"):
        found.append(f"branche de code {git['branch']}")
    if git.get("mr_url"):
        found.append(f"MR {git['mr_url']}")
    if issue:
        if float(issue.get("spent_hours") or 0) > 0:
            found.append(f"{issue['spent_hours']} h de temps saisi")
        if issue.get("children"):
            found.append(f"{len(issue['children'])} sous-tâche(s)")
        if issue.get("changesets"):
            found.append(f"{len(issue['changesets'])} commit(s) lié(s)")
    return found


def unlink(rm_id, other, no_commit):
    cmd = [sys.executable, str(HERE / "pm-task-link.py"), "rm", str(rm_id), str(other)]
    if no_commit:
        cmd.append("--no-commit")
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def sessions_listing(ref):
    """Sessions dont le worklog porte encore `ref` (ex. « RM3433 »)."""
    found = []
    for path in sorted(Path(pm_stores.worklog_dir()).glob("*.json")):
        try:
            items = json.loads(path.read_text(encoding="utf-8")).get("items") or []
        except (OSError, ValueError):
            continue
        if any(str(i.get("ref", "")).lower() == ref.lower() for i in items):
            found.append(path.stem)
    return found


def drop_from_worklogs(ref):
    """Retire `ref` des worklogs de session. Rend la liste des sessions en échec."""
    failed = []
    for sid in sessions_listing(ref):
        r = subprocess.run([sys.executable, str(HERE / "pm-session-status.py"),
                            "--session", sid, "rm", ref], capture_output=True, text=True)
        if r.returncode != 0:
            failed.append(sid)
    return failed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int, help="Id du ticket à supprimer")
    ap.add_argument("--reason", required=True,
                    help="Motif, tracé dans le journal PM (le ticket, lui, disparaît)")
    ap.add_argument("--apply", action="store_true",
                    help="Exécute la suppression (sinon : plan seulement)")
    ap.add_argument("--force", action="store_true",
                    help="Supprime même un ticket qui porte du travail (temps, sous-tâches, code)")
    ap.add_argument("--no-redmine", action="store_true",
                    help="Fichiers PM seuls (ticket déjà supprimé côté Redmine)")
    ap.add_argument("--no-commit", action="store_true")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    if not args.reason.strip():
        out.fail("--reason vide : le motif est la seule trace qui restera")

    cfg = PMConfig.load()
    rm_id = args.rm_id
    md_path, ent, proj = cfg.locate_task(rm_id)
    if not md_path:
        out.fail(f"RM{rm_id} n'a pas de fiche PM",
                 remede="l'outil supprime un ticket suivi par le PM ; vérifier l'id")
    ref = f"{ent}/{proj}"
    fm = read_frontmatter(md_path) or {}
    title = fm.get("title") or md_path.stem

    issue, provider = None, None
    if not args.no_redmine:
        provider = get_task_provider(cfg.project_meta(ent, proj))
        if not provider.capabilities.delete_issue:
            out.fail(f"le backend « {provider.name} » ne sait pas supprimer un ticket",
                     remede="--no-redmine pour ne supprimer que les fichiers PM")
        issue = provider.fetch_issue(rm_id, include="children,relations,changesets")

    files = task_files(md_path)
    links = linked_ids(fm, issue)
    work = blockers(fm, issue)

    out.info(f"  ticket   : RM{rm_id} « {title} » ({ref})")
    out.info(f"  fichiers : {', '.join(f.name for f in files)}")
    out.info(f"  liens    : {', '.join(f'RM{i}' for i in links) or 'aucun'}")
    out.info(f"  redmine  : {'ignoré (--no-redmine)' if args.no_redmine else 'suppression'}")
    if work:
        out.info(f"  travail  : {', '.join(work)}")

    if work and not args.force:
        out.fail(f"RM{rm_id} porte du travail ({', '.join(work)}) — il se ferme, il ne "
                 f"se supprime pas",
                 remede=f"pm-task-status-update.py {rm_id} ferme --close-reason <motif>, "
                        f"ou --force en connaissance de cause")
    if links and args.no_redmine and not args.force:
        out.fail(f"RM{rm_id} est lié à {', '.join(f'RM{i}' for i in links)} — hors Redmine, "
                 f"les liens ne peuvent pas être retirés proprement",
                 remede="relancer sans --no-redmine, ou --force (les miroirs resteront à nettoyer)")

    if not args.apply:
        out.op("delete (plan)", rm=rm_id, extra=f"« {title} » ({ref}) — relancer avec --apply")
        return

    # 1. Trace — avant toute destruction, et ailleurs que dans le ticket.
    pm_log.log("pm", "warn", f"RM{rm_id} supprimé : {args.reason}", echo=False,
               rm_id=rm_id, title=title, project=ref, reason=args.reason, tool=TOOL,
               user=os.environ.get("USER", ""), forced=bool(args.force and work))

    # 2. Liens — les miroirs vivent dans la fiche des autres tickets.
    if not args.no_redmine:
        for other in links:
            ok, err = unlink(rm_id, other, args.no_commit)
            if not ok:
                out.fail(f"retrait du lien RM{rm_id} ↔ RM{other} refusé : {err[:300]}",
                         remede="rien n'est encore supprimé ; corriger puis relancer")

    # 3. Redmine — si ça échoue, les fichiers sont intacts.
    if not args.no_redmine:
        ok, err = provider.delete_issue(rm_id)
        if not ok:
            out.fail(f"suppression Redmine refusée : {err}",
                     remede="permission « Delete issues » de la clé API ? Les fichiers "
                            "PM sont intacts")

    # 4. Fichiers
    for f in files:
        f.unlink()
    sha = None if args.no_commit else pm_git.autocommit(
        files, f"pm(delete): RM{rm_id} supprimé — {args.reason}", allow_missing=True)
    # 5. Worklogs de session — la liste « reste à faire » du cockpit.
    failed = drop_from_worklogs(f"RM{rm_id}")
    if failed:
        out.warn(f"RM{rm_id} encore listé dans le worklog de : {', '.join(failed)} "
                 f"(pm-session-status.py --session <id> rm RM{rm_id})")
    out.op("delete", rm=rm_id, extra=f"« {title} » ({ref})", commit=sha)


if __name__ == "__main__":
    main()
