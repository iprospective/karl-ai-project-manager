#!/usr/bin/env python3
"""pm-providers — inspecte le registre de serveurs et la résolution d'instance (RM2542/P0).

Outil de **diagnostic** (lecture seule) de la fondation providers (CDC RM2530).
Ne câble rien : il montre ce que `pm_registry.resolve_instances` retiendrait.

Depuis RM2653 (chantier RM2626), `resolve` liste **tous** les providers d'un axe : le
**primaire** (source de vérité PM) puis les **secondaires** (gestionnaires partenaires)
avec leurs règles `link:` / `sync:`.

Usage :
    pm-providers.py --list                       # registre (servers + defaults)
    pm-providers.py resolve [<axe>]              # résolution pour le projet du cwd
    pm-providers.py resolve <axe> --client C --project P
        <axe> ∈ {task, forge, doc} ; omis → les trois.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_registry import AXES, Registry, RegistryError, resolve_instances


def cmd_list(reg: Registry):
    print("Registre providers — defaults :")
    for axis in AXES:
        name = reg.defaults.get(axis, "—")
        print(f"  {axis:6} → {name}")
    print("\nInstances déclarées :")
    for axis in AXES:
        insts = reg.by_axis(axis)
        print(f"  [{axis}]")
        for i in sorted(insts, key=lambda x: x.name):
            opt = f"  {i.options}" if i.options else ""
            print(f"    · {i.name:15} type={i.type:12} url={i.url or '—'}{opt}")
        # instances sans axis déclaré (tolérées) rattachées à aucun bloc
    stray = [i for i in reg.servers.values() if i.axis not in AXES]
    if stray:
        print("  [sans axe déclaré]")
        for i in stray:
            print(f"    · {i.name:15} type={i.type}")


def cmd_resolve(cfg: PMConfig, reg: Registry, axis, client, project):
    if not (client and project):
        det = cfg.detect_project_from_cwd()
        if not det:
            sys.exit("ERREUR : projet non détecté depuis le cwd — passer "
                     "--client C --project P.")
        client, project = det
    meta = cfg.project_meta(client, project)
    axes = [axis] if axis else list(AXES)
    print(f"Résolution pour {client}/{project} :")
    for ax in axes:
        try:
            resolutions = resolve_instances(meta, ax, reg)
        except RegistryError as e:
            print(f"  {ax:6} → ✗ {e}")
            continue
        for n, res in enumerate(resolutions):
            i = res.instance
            head = f"  {ax:6} → " if n == 0 else f"  {'':6}   "
            tag = "primaire " if res.is_primary else "secondaire"
            print(f"{head}{i.name:15} [{tag}] (type={i.type}, url={i.url or '—'}, "
                  f"source={res.source})")
            if res.params:
                print(f"  {'':9} params={res.params}")
            if res.link:
                print(f"  {'':9} link={res.link}")
            if res.sync:
                print(f"  {'':9} sync={res.sync}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--list", action="store_true", help="affiche le registre et quitte")
    r = sub.add_parser("resolve", help="montre la résolution d'instance d'un projet")
    r.add_argument("axis", nargs="?", choices=list(AXES),
                   help="axe à résoudre (défaut : les trois)")
    r.add_argument("--client", help="entité/client (défaut : détecté du cwd)")
    r.add_argument("--project", help="slug projet (défaut : détecté du cwd)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    try:
        reg = Registry.from_config(cfg.providers)
    except RegistryError as e:
        sys.exit(f"ERREUR de registre (pm.config.yml :: providers) : {e}")

    if args.list or args.cmd is None:
        cmd_list(reg)
        return
    if args.cmd == "resolve":
        cmd_resolve(cfg, reg, args.axis, args.client, args.project)


if __name__ == "__main__":
    main()
