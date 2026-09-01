#!/usr/bin/env python3
"""pm-lock-gc — GC des fichiers .lock (T7/RM2551) : filet post-crash + observabilité.

Les verrous `pm_lock` sont des `flock(2)` noyau : à la mort d'un process, le lock est
libéré AUTOMATIQUEMENT (aucun verrou fantôme). Le fichier `.lock` peut subsister mais
est INERTE. Ce GC nettoie les `.lock` inertes ET vieux, et SIGNALE (sans jamais casser)
un `.lock` tenu anormalement longtemps (= détenteur potentiellement pendu).

  pm-lock-gc.py                    # DRY-RUN sur state_dir/locks : montre, ne supprime rien
  pm-lock-gc.py --apply            # supprime les inertes inactifs > --min-idle
  pm-lock-gc.py --min-idle 600     # seuil d'inactivité/anomalie (défaut 3600 s)
  pm-lock-gc.py --root <dir>       # autre répertoire de .lock

Exit code 1 si une anomalie (lock tenu trop longtemps) est détectée — utile en cron/alerte.
À lancer en cron (nettoyage périodique) et invocable à la main.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
from pm_lock import gc_locks  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Supprime réellement les inertes vieux (défaut : dry-run).")
    ap.add_argument("--min-idle", type=float, default=3600.0,
                    help="Âge (s) d'inactivité avant suppression / seuil d'anomalie (défaut 3600).")
    ap.add_argument("--root", type=Path, default=None,
                    help="Répertoire de .lock (défaut : <state_dir>/locks).")
    args = ap.parse_args()

    root = args.root or (PMConfig.load().state_dir / "locks")
    rep = gc_locks(root, min_idle=args.min_idle, apply=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== pm-lock-gc [{mode}] {root} ===")
    print(f"  inertes vieux {'supprimés' if args.apply else 'à supprimer'} : {len(rep['removed'])}")
    print(f"  inertes récents gardés          : {len(rep['kept_inert'])}")
    print(f"  tenus (verrou vivant)           : {len(rep['held'])}")
    for name, age in rep["stale_held"]:
        print(f"  ⚠ ANOMALIE : {name} tenu depuis {age}s (> {args.min_idle:g}) "
              f"— détenteur pendu ? (investiguer ; kill sous contrôle admin)")
    return 1 if rep["stale_held"] else 0


if __name__ == "__main__":
    sys.exit(main())
