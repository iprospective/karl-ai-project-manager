#!/usr/bin/env python3
"""redmine-tag-ia — Opt-in / opt-out d'un ticket Redmine pour la sync PM.

Set ou retire le custom field 'IA' (mutex de synchronisation cf. NORMS).
Optionnellement, déclenche immédiatement la création du MD local via
`redmine-fetch-task.py`.

Usage :
    redmine-tag-ia.py <RM-id>                  # tag IA + crée le MD local
    redmine-tag-ia.py <RM-id> --no-fetch       # tag uniquement
    redmine-tag-ia.py <RM-id> --untag          # retire le tag (laisse le MD)
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import get_ia_cf_id, set_issue_ia_tag, issue_is_ia_tagged
from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--untag", action="store_true", help="Retirer le tag (au lieu de l'ajouter)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="Ne pas créer le MD local après tagging (par défaut: si tag → fetch)")
    args = ap.parse_args()

    cfg = PMConfig.load()  # charge .env

    if get_ia_cf_id() is None:
        sys.exit("ERREUR : REDMINE_CF_IA_ID non configuré dans .env. "
                 "Créer le custom field 'IA' en UI Redmine puis renseigner l'id.")

    # État courant
    issue = get_task_provider().fetch_issue(args.rm_id)
    was_tagged = issue_is_ia_tagged(issue)
    subject = (issue.get("subject") or "").strip()

    if args.untag:
        if not was_tagged:
            print(f"ℹ RM{args.rm_id} déjà sans tag IA — rien à faire.")
            return
        set_issue_ia_tag(args.rm_id, value="")
        print(f"✓ RM{args.rm_id} — tag IA retiré.")
        # Signaler si un MD local existe (drift)
        md = cfg.find_task(args.rm_id)
        if md:
            print(f"⚠ MD local toujours présent : {md.relative_to(cfg.projects_root)}")
            print(f"  → Envisager d'archiver (déplacer dans tasks/_archived/) ou de re-tagger.")
        return

    # Tag (opt-in)
    if was_tagged:
        print(f"ℹ RM{args.rm_id} déjà tagué IA.")
    else:
        set_issue_ia_tag(args.rm_id, value="IA")
        print(f"✓ RM{args.rm_id} ({subject!r}) — tag IA ajouté.")

    if args.no_fetch:
        return

    # Si le MD existe déjà, on ne refetch pas (on évite l'overwrite)
    if cfg.find_task(args.rm_id):
        print(f"ℹ MD local existant : {cfg.find_task(args.rm_id).relative_to(cfg.projects_root)} — fetch skip.")
        return

    print(f"→ Déclenche redmine-fetch-task.py --issue {args.rm_id}")
    fetch = Path(__file__).parent / "redmine-fetch-task.py"
    r = subprocess.run([sys.executable, str(fetch), "--issue", str(args.rm_id)], check=False)
    if r.returncode != 0:
        sys.exit(f"ERREUR : redmine-fetch-task a échoué (exit {r.returncode})")


if __name__ == "__main__":
    main()
