#!/usr/bin/env python3
"""pm-task-protocol — Protocole de test d'un ticket : CF Redmine + frontmatter (RM2229).

Le protocole de test se rédige AU FIL DE L'EAU pendant l'avancement du ticket
(décision Mathieu 2026-07-11) — pas seulement à la livraison. Champ canonique :
le CF Redmine « Protocole de test » (texte long), avec miroir local dans le
frontmatter `test_protocol` de la tâche (c'est le miroir que lit la fiche de
revue du cockpit — karl-agent ne lit que le local).

Usage :
    pm-task-protocol.py <RM-id>                    # affiche le protocole courant
    pm-task-protocol.py <RM-id> --set "Texte"      # remplace (ou '-' pour stdin)
    echo "1. ..." | pm-task-protocol.py <RM-id> --set -
    pm-task-protocol.py <RM-id> --append -         # ajoute un bloc à la suite

Config : id du CF dans `.env` → REDMINE_CF_TEST_PROTOCOL_ID (créé via l'UI admin
Redmine — l'API ne sait pas créer une définition de CF). Sans cette variable,
l'id est résolu par nom depuis `redmine.reference.yml` ; à défaut, seul le miroir
frontmatter est écrit (warning) : le cockpit fonctionne quand même, Redmine
n'affiche juste pas le champ.

Le miroir lui-même vit dans `pm_cf_mirror` — même contrat pour `implementation`
(CF 31) et `deploy_actions` (CF 8), cf. RM2563.
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


ENV_VAR = "REDMINE_CF_TEST_PROTOCOL_ID"
CF_NAME = "Protocole de test"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--set", dest="set_", metavar="TXT", help="Remplace le protocole ('-' = stdin)")
    g.add_argument("--append", metavar="TXT", help="Ajoute un bloc à la suite ('-' = stdin)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true", help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    if args.set_ is not None or args.append is not None:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-protocol")
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    current = str(fm.get("test_protocol") or "").strip()

    if args.set_ is None and args.append is None:
        print(current if current else f"(pas de protocole de test sur RM{args.rm_id} — "
                                      f"pm-task-protocol.py {args.rm_id} --set -)")
        return

    txt = args.set_ if args.set_ is not None else args.append
    txt = (sys.stdin.read() if txt == "-" else txt).strip()
    if not txt:
        sys.exit("ERREUR : protocole vide")
    new = (current + "\n\n" + txt).strip() if (args.append is not None and current) else txt

    # 1. Miroir frontmatter (bloc littéral multiligne via safe_dump)
    fm["test_protocol"] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter test_protocol : {md_path.relative_to(cfg.projects_root)}")

    # 2. CF Redmine (champ canonique visible web)
    if pm_cf_mirror.push_text_cf(args.rm_id, new, env_var=ENV_VAR, cf_name=CF_NAME):
        print(f"✓ CF Redmine « {CF_NAME} » poussé")

    # 3. Log + auto-commit
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    verb = "remplacé" if args.set_ is not None else "complété"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Protocole de test {verb} (pm-task-protocol)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{txt}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(protocol): RM{args.rm_id} protocole de test {verb}")


if __name__ == "__main__":
    main()
