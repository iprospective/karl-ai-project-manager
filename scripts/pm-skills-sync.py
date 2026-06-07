#!/usr/bin/env python3
"""pm-skills-sync — expose les skills PM (skills/) à Claude Code via des symlinks.

Claude Code n'auto-découvre les skills que depuis ~/.claude/skills/ (ou le
.claude/skills/ d'un projet, ou les plugins). Les skills versionnés dans ce repo
PM (dossier `skills/`) ne sont donc invocables qu'une fois symlinkés dans le
dossier skills de l'utilisateur. Ce script crée/rafraîchit ces symlinks.

Même pattern que les symlinks `~/.claude/skills/X → ~/.agents/skills/X` déjà
utilisés pour les skills agents : un lien par skill, pointant vers ce repo.

Usage :
  pm-skills-sync.py                 # crée/rafraîchit les symlinks manquants
  pm-skills-sync.py --dry-run       # montre les actions sans rien modifier
  pm-skills-sync.py --prune         # retire en plus les symlinks PM devenus orphelins
  pm-skills-sync.py --target DIR    # dossier skills cible (défaut: ~/.claude/skills)

Garde-fous :
  - ne supprime JAMAIS un vrai dossier/fichier (collision de nom → averti, ignoré) ;
  - ne touche qu'aux symlinks qui pointent dans le dossier skills/ de ce repo ;
  - idempotent : relançable sans effet de bord.
"""
import argparse
import os
import sys
from pathlib import Path

PM_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PM_ROOT / "skills"


def discover_skills(skills_dir: Path):
    """Sous-dossiers de skills/ contenant un SKILL.md."""
    if not skills_dir.is_dir():
        return []
    return sorted(
        p for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )


def points_into(link: Path, root: Path) -> bool:
    """Vrai si `link` est un symlink dont la cible résolue est sous `root`."""
    if not link.is_symlink():
        return False
    try:
        return root in link.resolve().parents or link.resolve() == root
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Symlink les skills PM dans le dossier skills utilisateur.")
    ap.add_argument("--target", type=Path, default=Path.home() / ".claude" / "skills",
                    help="Dossier skills cible (défaut: ~/.claude/skills)")
    ap.add_argument("--dry-run", action="store_true", help="Affiche sans modifier.")
    ap.add_argument("--prune", action="store_true",
                    help="Retire les symlinks pointant vers skills/ dont la source a disparu.")
    args = ap.parse_args()

    target = args.target.expanduser()
    skills = discover_skills(SKILLS_DIR)
    if not skills:
        print(f"Aucun skill dans {SKILLS_DIR}")
        return 0

    if not target.exists():
        if args.dry_run:
            print(f"[dry-run] mkdir -p {target}")
        else:
            target.mkdir(parents=True, exist_ok=True)

    created = linked_ok = skipped = repaired = 0
    for skill in skills:
        link = target / skill.name
        if link.is_symlink():
            if link.resolve() == skill.resolve():
                linked_ok += 1
                continue
            # symlink existant mais mauvaise cible → réparer
            print(f"~ {skill.name} : symlink repointé ({os.readlink(link)} → {skill})")
            if not args.dry_run:
                link.unlink()
                link.symlink_to(skill)
            repaired += 1
        elif link.exists():
            # vrai dossier/fichier : collision, on n'y touche pas
            print(f"! {skill.name} : un vrai dossier/fichier existe déjà dans {target} — ignoré "
                  f"(déplace-le ou supprime-le pour utiliser la version PM)")
            skipped += 1
        else:
            print(f"+ {skill.name} → {skill}")
            if not args.dry_run:
                link.symlink_to(skill)
            created += 1

    pruned = 0
    if args.prune and target.is_dir():
        for entry in sorted(target.iterdir()):
            if points_into(entry, SKILLS_DIR) and not entry.exists():
                print(f"- {entry.name} : symlink orphelin retiré")
                if not args.dry_run:
                    entry.unlink()
                pruned += 1

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"\n{prefix}{created} créé(s), {repaired} réparé(s), {linked_ok} déjà OK, "
          f"{skipped} ignoré(s){', ' + str(pruned) + ' éla­gué(s)' if args.prune else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
