#!/usr/bin/env python3
"""pm-session-relocate — Déplace les sessions Claude quand un workspace change de chemin (CDC §3.7).

Quand un dossier de workspace est déplacé/renommé (ex. /zfs/workspaces/infra →
/zfs/workspaces/iprospective/infrastructure/infra), l'historique des sessions
Claude (`~/.claude/projects/<cwd-encodé>/`, dont l'auto-mémoire) doit suivre,
sinon `claude --resume` et les mémoires projet sont perdus.

Ce script :
  1. encode l'ancien et le nouveau chemin (règle Claude Code : `/`→`-`) ;
  2. renomme `~/.claude/projects/<old-encodé>` → `<new-encodé>` (refuse si la cible
     existe déjà — pas de fusion destructive) ;
  3. (--fix-paths) remplace l'ancien chemin absolu par le nouveau dans les fichiers
     de mémoire du dossier (`memory/*.md`, `MEMORY.md`) — contenu activement chargé.

Les transcripts `.jsonl` ne sont PAS réécrits (le champ `cwd` y est historique ;
Claude associe les sessions par le NOM du dossier encodé, pas par ce champ).

Usage :
    pm-session-relocate.py <ancien-chemin-abs> <nouveau-chemin-abs> [--fix-paths] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"


def encode(path: str) -> str:
    """Chemin absolu → nom de dossier de sessions Claude (`/`→`-`)."""
    return "-" + path.strip("/").replace("/", "-")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old_path", help="Ancien chemin absolu du workspace")
    ap.add_argument("new_path", help="Nouveau chemin absolu du workspace")
    ap.add_argument("--fix-paths", action="store_true",
                    help="Réécrit l'ancien chemin → nouveau dans les mémoires du dossier")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    old_enc, new_enc = encode(args.old_path), encode(args.new_path)
    src, dst = PROJECTS / old_enc, PROJECTS / new_enc
    print(f"== {args.old_path}  →  {args.new_path} ==")
    print(f"   {old_enc}  →  {new_enc}")

    if not src.is_dir():
        print(f"  · aucun dossier de sessions pour l'ancien chemin ({old_enc}) — rien à déplacer")
        return
    n = len(list(src.glob("*.jsonl")))
    if dst.exists():
        sys.exit(f"  ✗ la cible existe déjà ({new_enc}) — fusion manuelle requise, abandon")

    if args.dry_run:
        print(f"  [dry] renommerait le dossier ({n} sessions)")
    else:
        src.rename(dst)
        print(f"  ✓ {n} session(s) déplacées : {old_enc} → {new_enc}")

    # Correction des chemins absolus dans les mémoires
    target = dst if not args.dry_run else src
    mem_files = list((target / "memory").glob("*.md")) if (target / "memory").is_dir() else []
    mem_files += [target / "memory" / "MEMORY.md"] if (target / "memory" / "MEMORY.md").is_file() else []
    touched = 0
    for f in set(mem_files):
        try:
            txt = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if args.old_path in txt:
            touched += 1
            if args.fix_paths and not args.dry_run:
                f.write_text(txt.replace(args.old_path, args.new_path), encoding="utf-8")
    if touched:
        if args.fix_paths and not args.dry_run:
            print(f"  ✓ chemins corrigés dans {touched} fichier(s) mémoire")
        else:
            print(f"  ⚠ {touched} fichier(s) mémoire référencent l'ancien chemin "
                  f"({'--fix-paths pour corriger' if not args.fix_paths else 'dry-run'})")

    print("== terminé ==" + (" (DRY-RUN)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
