#!/usr/bin/env python3
"""pm-task-deploy — actions à effectuer au déploiement : CF Redmine + frontmatter (RM2563).

`deploy_actions` existait dans le schéma de tâche depuis l'origine, et le CF
Redmine **8 « Actions au déploiement »** existait de son côté — mais **rien ne
les reliait** : le champ n'était qu'initialisé à `[]` (redmine-fetch-task,
pm_task_md, pm-project-bootstrap), jamais lu ni poussé. Ce script ferme le
circuit.

Ce qu'on y met : ce que la MEP exige **en plus** d'un `git pull` — migration SQL
à jouer, cache à vider, constante à créer, cron à (ré)installer, service à
recharger, ordre imposé entre deux dépôts. Une action par ligne, à l'impératif,
rédigée **au fil de l'eau** pendant le dev : c'est au moment où on écrit la
migration qu'on sait qu'il faudra la jouer, pas trois semaines plus tard devant
la prod.

Champ canonique : le CF Redmine 8 (texte long, visible sur la fiche) ; miroir
local dans le frontmatter `deploy_actions` (liste — c'est le miroir que lit le
cockpit). Sérialisation : une action par ligne, préfixée `- `.

Usage :
    pm-task-deploy.py <RM-id>                      # liste les actions courantes
    pm-task-deploy.py <RM-id> --add "Jouer la migration 2026-08-25-catalogpro.sql"
    pm-task-deploy.py <RM-id> --add "A" --add "B"  # plusieurs d'un coup
    pm-task-deploy.py <RM-id> --set -              # remplace (stdin, 1 par ligne)
    pm-task-deploy.py <RM-id> --clear              # vide la liste
    pm-task-deploy.py <RM-id> --pull               # REDMINE → PM (saisie faite dans l'UI web)

Config : id du CF dans `.env` → REDMINE_CF_DEPLOY_ACTIONS_ID ; à défaut résolu
par nom depuis `redmine.reference.yml`. Absent ⇒ miroir frontmatter seul
(warning, jamais fatal).
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_cf_mirror
import pm_git
import pm_scope

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
ENV_VAR = "REDMINE_CF_DEPLOY_ACTIONS_ID"
CF_NAME = "Actions au déploiement"


# Sérialisation liste ↔ texte : mutualisée avec pm-task-sync (RM2563), qui rapatrie
# le même CF dans l'autre sens.
to_text = pm_cf_mirror.list_to_text
from_text = pm_cf_mirror.text_to_list


def read_fm(md_path):
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    return m, (yaml.safe_load(m.group(2)) or {})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--add", action="append", metavar="TXT",
                   help="Ajoute une action (répétable)")
    g.add_argument("--set", dest="set_", metavar="TXT",
                   help="Remplace la liste ('-' = stdin, une action par ligne)")
    g.add_argument("--clear", action="store_true", help="Vide la liste")
    g.add_argument("--pull", action="store_true",
                   help="Rapatrie la valeur du CF Redmine vers le frontmatter")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    writing = bool(args.add or args.set_ is not None or args.clear or args.pull)
    if writing:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-deploy")

    m, fm = read_fm(md_path)
    current = list(fm.get("deploy_actions") or [])

    if not writing:
        if current:
            for a in current:
                print(f"- {a}")
        else:
            print(f"(aucune action de déploiement sur RM{args.rm_id} — "
                  f"pm-task-deploy.py {args.rm_id} --add \"…\")")
        return

    if args.pull:
        remote = pm_cf_mirror.pull_text_cf(args.rm_id, env_var=ENV_VAR, cf_name=CF_NAME)
        if remote is None:
            print(f"(CF « {CF_NAME} » vide ou non résolu sur RM{args.rm_id} — "
                  f"frontmatter inchangé)")
            return
        new = from_text(remote)
        verb = "rapatriées depuis Redmine"
    elif args.clear:
        new, verb = [], "vidées"
    elif args.set_ is not None:
        raw = sys.stdin.read() if args.set_ == "-" else args.set_
        new = from_text(raw)
        if not new:
            sys.exit("ERREUR : liste vide (utiliser --clear pour vider volontairement)")
        verb = "remplacées"
    else:
        new = current + [a.strip() for a in args.add if a.strip()]
        verb = "complétées"

    if new == current:
        print(f"(deploy_actions inchangées sur RM{args.rm_id})")
        return

    # 1. Miroir frontmatter
    fm["deploy_actions"] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter deploy_actions ({len(new)}) : {md_path.relative_to(cfg.projects_root)}")

    # 2. CF Redmine — sauf sur --pull, où Redmine est déjà la source.
    if not args.pull and pm_cf_mirror.push_text_cf(args.rm_id, to_text(new),
                                                   env_var=ENV_VAR, cf_name=CF_NAME):
        print(f"✓ CF Redmine « {CF_NAME} » poussé")

    # 3. Log + auto-commit
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Actions au déploiement {verb} (pm-task-deploy)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{to_text(new) or '(aucune)'}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(deploy): RM{args.rm_id} actions au déploiement {verb}")


if __name__ == "__main__":
    main()
