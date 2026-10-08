#!/usr/bin/env python3
"""pm-privsep — le modèle de propriété de l'instance : le montrer, ou l'exporter pour le shell (RM3379).

    mmi-pm privsep                  le modèle effectif, cible par cible (lecture seule)
    mmi-pm privsep --sh             exports consommés par `core-lock` (source unique du modèle)

Applique-le : `pm-perms --apply --var <workspace>` (sans privilège pour les droits de groupe) ou
`core-lock lock` (root, au déploiement). Configuration : section `privsep:` de `pm.config.yml`.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_privsep  # noqa: E402


def _core_and_state(core_opt):
    if core_opt:
        core = Path(core_opt).expanduser().resolve()
        return core, core / "var"
    try:
        from pm_paths import PMConfig
        cfg = PMConfig.load()
        return cfg.pm_dir, cfg.state_dir
    except Exception:
        core = Path(os.environ.get("PM_CORE_DIR") or Path(__file__).resolve().parent.parent)
        return core, core / "var"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mmi-pm privsep", description=__doc__.split("\n")[0])
    ap.add_argument("--core", help="racine de l'instance (défaut : celle résolue par la conf)")
    ap.add_argument("--sh", action="store_true", help="exports shell (pour core-lock)")
    ap.add_argument("--names", action="store_true",
                    help="noms CONFIGURÉS des groupes, sans repli — pour les créer (install-mmi-pm)")
    args = ap.parse_args(argv)
    core, state = _core_and_state(args.core)
    env = dict(os.environ)
    for key in ("KARL_USER", "KARL_SUDO_USER"):      # le .env de l'instance, s'il est lisible
        if key not in env:
            try:
                for line in (core / ".env").read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith(f"{key}="):
                        env[key] = line.split("=", 1)[1].strip().strip("'\"")
            except OSError:
                pass
    if args.names:
        cfg = pm_privsep.read_config(core)
        print(f"PRIVSEP_CONFIGURED_GROUP={cfg.get('group') or pm_privsep.DEFAULT_GROUP}")
        print(f"PRIVSEP_CONFIGURED_ADMIN_GROUP={cfg.get('admin_group') or pm_privsep.DEFAULT_ADMIN_GROUP}")
        return 0
    model = pm_privsep.load(core, environ=env)
    if args.sh:
        sys.stdout.write(pm_privsep.sh_exports(core, state, model))
        return 0
    print(f"instance : {core}")
    print(f"modèle   : {model.describe()}")
    for w in model.fallbacks:
        print(f"  ⚠ {w}")
    print()
    for t in pm_privsep.core_targets(core, state, model):
        etat = "présent" if t.path.exists() else "absent"
        print(f"  {str(t.path):<60} {(t.owner or '(inchangé)')}:{t.group} {t.mode:04o}"
              f"{' -R' if t.recurse else '  '}  {etat:<8} {t.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
