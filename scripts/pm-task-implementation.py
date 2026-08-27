#!/usr/bin/env python3
"""pm-task-implementation — esquisse d'implémentation d'un ticket : CF Redmine + frontmatter (RM2563).

La **proposition d'implémentation** est le livrable *technique* de la phase
d'étude : ce que l'audit a compris de l'endroit où le code va se greffer. Elle
répond au **comment**, là où le CDC répond au *quoi* et le chiffrage au *combien*.

Champ canonique : le CF Redmine **31 « Proposition d'implémentation »** (texte
long) ; miroir local dans le frontmatter `implementation` (c'est le miroir que lit
la fiche de revue du cockpit — karl-agent ne lit que le local).

Contenu attendu, niveau de détail et dispenses : NORMS
`modules/status-workflow-pratique.md` § *La section « Implémentation » du CDC*.
En deux lignes : modèle de données, composants, **points d'insertion
`fichier:fonction`**, vues, flux & déclencheurs, migration, pièges — 15 à 40
lignes, ça **oriente sans prescrire**.

Usage :
    pm-task-implementation.py <RM-id>                 # affiche l'esquisse courante
    pm-task-implementation.py <RM-id> --set "Texte"   # remplace ('-' = stdin)
    cat esquisse.md | pm-task-implementation.py <RM-id> --set -
    pm-task-implementation.py <RM-id> --append -      # ajoute un bloc à la suite
    pm-task-implementation.py <RM-id> --from-description   # migre la section
                                                      # `## Implémentation` du corps

Config : id du CF dans `.env` → REDMINE_CF_IMPLEMENTATION_ID (créé via l'UI admin
Redmine — l'API ne sait pas créer une définition de CF). Sans cette variable, l'id
est résolu par nom depuis `redmine.reference.yml` ; à défaut, seul le miroir
frontmatter est écrit (warning, jamais fatal).
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
# Section `## Implémentation` du corps : tolérante aux accents, au pluriel et aux
# niveaux # 1 à 4 — même expression que la garde de pm-task-status-update.
SECTION_RE = re.compile(r"(?mi)^(?P<h>#{1,4})\s*Impl[ée]mentations?\b[^\n]*\n(?P<body>.*?)"
                        r"(?=^\#{1,4}\s|\Z)", re.DOTALL)
ENV_VAR = "REDMINE_CF_IMPLEMENTATION_ID"
CF_NAME = "Proposition d'implémentation"


def extract_from_description(body: str):
    """Corps de la section `## Implémentation` du MD, ou None."""
    m = SECTION_RE.search(body)
    if not m:
        return None
    txt = m.group("body").strip()
    return txt or None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--set", dest="set_", metavar="TXT",
                   help="Remplace l'esquisse ('-' = stdin)")
    g.add_argument("--append", metavar="TXT", help="Ajoute un bloc à la suite ('-' = stdin)")
    g.add_argument("--from-description", action="store_true",
                   help="Reprend la section `## Implémentation` du corps du MD "
                        "(migration d'un CDC rédigé avant RM2563)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    writing = args.set_ is not None or args.append is not None or args.from_description
    if writing:
        pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project,
                                   "pm-task-implementation")
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    current = str(fm.get("implementation") or "").strip()

    if not writing:
        if current:
            print(current)
            return
        # Rien dans le frontmatter : la section vit peut-être encore dans le corps.
        legacy = extract_from_description(m.group(4))
        if legacy:
            print(f"(pas de champ `implementation` sur RM{args.rm_id}, mais une section "
                  f"`## Implémentation` existe dans le corps — la migrer :\n"
                  f"   pm-task-implementation.py {args.rm_id} --from-description)",
                  file=sys.stderr)
            print(legacy)
        else:
            print(f"(pas d'esquisse d'implémentation sur RM{args.rm_id} — "
                  f"pm-task-implementation.py {args.rm_id} --set -)")
        return

    if args.from_description:
        txt = extract_from_description(m.group(4))
        if not txt:
            sys.exit(f"ERREUR : aucune section `## Implémentation` dans le corps de "
                     f"{md_path.name} — rien à migrer.")
        verb = "repris de la description"
    else:
        txt = args.set_ if args.set_ is not None else args.append
        txt = (sys.stdin.read() if txt == "-" else txt).strip()
        verb = "remplacée" if args.set_ is not None else "complétée"
    if not txt:
        sys.exit("ERREUR : esquisse vide")
    new = (current + "\n\n" + txt).strip() if (args.append is not None and current) else txt

    # 1. Miroir frontmatter (bloc littéral multiligne via safe_dump)
    fm["implementation"] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    print(f"✓ frontmatter implementation : {md_path.relative_to(cfg.projects_root)}")

    # 2. CF Redmine (champ canonique visible web)
    if pm_cf_mirror.push_text_cf(args.rm_id, new, env_var=ENV_VAR, cf_name=CF_NAME):
        print(f"✓ CF Redmine « {CF_NAME} » poussé")

    # 3. Log + auto-commit
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Esquisse d'implémentation {verb} (pm-task-implementation)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{txt}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(impl): RM{args.rm_id} esquisse d'implémentation {verb}")


if __name__ == "__main__":
    main()
