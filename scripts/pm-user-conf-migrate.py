#!/usr/bin/env python3
"""pm-user-conf-migrate — Sort la conf PM d'un utilisateur de son home (RM3318).

La conf PM ne va JAMAIS dans `~`. Ce script déplace, UNE fois, le contenu de l'ancien
`~/.config/mmi-pm/` (RM2497) vers `<core>/var/users/<user>/` (hors git, 700 / fichiers 600) :

  - fichier absent à la destination  → déplacé ;
  - `.env` déjà présent à la destination → FUSION : les clés absentes sont ajoutées, celles déjà
    posées côté `var/` sont gardées (c'est la nouvelle source de vérité) ; un conflit de valeur
    est signalé, jamais tranché en silence — l'ancien fichier est alors conservé ;
  - autre fichier déjà présent → laissé en place et signalé (à arbitrer à la main).

L'ancien dossier est supprimé s'il se retrouve vide. Aucune valeur n'est affichée.

Usage :
    pm-user-conf-migrate.py --dry-run     # ce qui serait fait
    pm-user-conf-migrate.py               # le faire (utilisateur courant)

Pré-requis : lancé depuis le runtime (ou avec PM_CORE_DIR), sinon la destination serait le `var/`
d'un worktree de session, détruit à la livraison — le script refuse.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_paths  # noqa: E402


def lire_env(path: Path) -> dict:
    """{clé: valeur brute} d'un .env (commentaires et lignes vides ignorés)."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if k.startswith("export "):
            k = k[len("export "):].strip()
        out[k] = v.strip()
    return out


def fusionner_env(src: Path, dst: Path, dry: bool) -> bool:
    """Ajoute à `dst` les clés de `src` qui lui manquent. Rend True si `src` peut être supprimé
    (aucun conflit de valeur)."""
    anciens, nouveaux = lire_env(src), lire_env(dst)
    a_ajouter = [k for k in anciens if k not in nouveaux]
    conflits = [k for k in anciens if k in nouveaux and anciens[k] != nouveaux[k]]
    for k in a_ajouter:
        print(f"    + {k}")
    for k in conflits:
        print(f"    ⚠ {k} : valeurs différentes — gardée côté var/, ancienne conservée dans {src}")
    if a_ajouter and not dry:
        bloc = [f"\n# Repris de {src} (pm-user-conf-migrate, RM3318)"]
        src_lignes = {}
        for line in src.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k = s.partition("=")[0].strip()
                k = k[len("export "):].strip() if k.startswith("export ") else k
                src_lignes.setdefault(k, s)
        bloc += [src_lignes[k] for k in a_ajouter]
        with dst.open("a", encoding="utf-8") as f:
            f.write("\n".join(bloc) + "\n")
        os.chmod(dst, 0o600)
    return not conflits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="Affiche le plan sans rien toucher")
    ap.add_argument("--force", action="store_true",
                    help="Accepte une destination dans un worktree de session (tests uniquement)")
    args = ap.parse_args()

    src_dir = pm_paths.legacy_user_conf_dir()
    dst_dir = pm_paths.user_conf_dir()
    if f"{os.sep}envs{os.sep}" in str(dst_dir) and not args.force:
        sys.exit(f"ERREUR : destination {dst_dir} dans un worktree de session (détruit à la livraison).\n"
                 "  Lance depuis le runtime, ou pose PM_CORE_DIR=<chemin .mmi-pm-core>.")
    if not src_dir.is_dir():
        print(f"Rien à migrer : {src_dir} n'existe pas.")
        return 0

    print(f"{'[dry-run] ' if args.dry_run else ''}{src_dir} → {dst_dir}")
    if not args.dry_run:
        dst_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(dst_dir, 0o700)

    restes = 0
    for src in sorted(src_dir.iterdir()):
        dst = dst_dir / src.name
        if not src.is_file():
            print(f"  ? {src.name} : pas un fichier, laissé en place")
            restes += 1
            continue
        if not dst.exists():
            print(f"  → {src.name} : déplacé")
            if not args.dry_run:
                shutil.copy2(src, dst)
                os.chmod(dst, 0o600)
                src.unlink()
        elif src.name == ".env":
            print(f"  ⇄ {src.name} : fusion (clés manquantes ajoutées)")
            if fusionner_env(src, dst, args.dry_run):
                if not args.dry_run:
                    src.unlink()
            else:
                restes += 1
        else:
            print(f"  ⚠ {src.name} : existe déjà dans {dst_dir} — laissé en place, à arbitrer")
            restes += 1

    if not args.dry_run and not any(src_dir.iterdir()):
        src_dir.rmdir()
        print(f"  ✓ {src_dir} supprimé (vide)")
    elif restes:
        print(f"  {restes} élément(s) restant(s) dans {src_dir}")
    return 0 if not restes else 1


if __name__ == "__main__":
    sys.exit(main())
