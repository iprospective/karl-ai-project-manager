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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

from pm_paths import PMConfig
from pm_registry import AXES, Registry, RegistryError, resolve_instances

_spec = importlib.util.spec_from_file_location(
    "pm_secrets", str(Path(__file__).resolve().parent / "pm_secrets.py"))
pm_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_secrets)


def cmd_list(reg: Registry):
    print(f"Registre providers — axes actifs : {', '.join(reg.axes)}")
    print("Defaults :")
    for axis in reg.axes:
        name = reg.defaults.get(axis, "—")
        print(f"  {axis:6} → {name}")
    print("\nInstances déclarées :")
    for axis in reg.axes:
        insts = reg.by_axis(axis)
        print(f"  [{axis}]")
        for i in sorted(insts, key=lambda x: x.name):
            opt = f"  {i.options}" if i.options else ""
            print(f"    · {i.name:15} type={i.type:12} url={i.url or '—'}{opt}")
        # instances sans axis déclaré (tolérées) rattachées à aucun bloc
    stray = [i for i in reg.servers.values() if i.axis not in reg.axes]
    if stray:
        print("  [sans axe déclaré]")
        for i in stray:
            print(f"    · {i.name:15} type={i.type}")


def cmd_resolve(cfg: PMConfig, reg: Registry, axis, client, project):
    # `--client` explicite fait foi : ne pas le laisser écraser par le cwd (sinon
    # on répond pour le projet courant en croyant répondre pour le client demandé).
    if not client:
        det = cfg.detect_project_from_cwd()
        if not det:
            sys.exit("ERREUR : projet non détecté depuis le cwd — passer "
                     "--client C [--project P].")
        client, project = det
    # `--client` seul : ce que voit un projet de ce client qui ne surcharge rien.
    meta = cfg.project_meta(client, project) if project else {}
    client_meta = cfg.client_meta(client)
    axes = [axis] if axis else list(reg.axes)
    cible = f"{client}/{project}" if project else f"{client}/<projet sans surcharge>"
    print(f"Résolution pour {cible} :")
    for ax in axes:
        try:
            resolutions = resolve_instances(meta, ax, reg, client_meta=client_meta)
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
            if ax == "secret":
                # Identifiants : on ne montre QUE les noms de clés (tripwire 11).
                # Le repli `legacy` (BW_CLIENTID/BW_CLIENTSECRET) est GLOBAL : il
                # n'appartient qu'à l'instance par défaut de l'axe. L'accorder à
                # toutes ferait passer une instance sans identifiants pour
                # configurée, et le diagnostic contredirait le backend, qui refuse
                # alors en `unreachable` (RM2835). Même règle que karl-agent.
                keys = pm_secrets.creds_keys(
                    i.name, legacy=(i.name == reg.defaults.get(ax)))
                print(f"  {'':9} creds={', '.join(keys) if keys else '— aucun'}")


def cmd_instance(reg: Registry, name, field):
    """Fiche d'une instance déclarée — sert aussi de résolveur aux scripts shell."""
    inst = reg.get(name)
    if field:
        valeur = {"type": inst.type, "url": inst.url, "axis": inst.axis}.get(
            field, inst.options.get(field, ""))
        print(valeur)
        return
    opts = " ".join(f"{k}={v}" for k, v in sorted(inst.options.items()))
    print(f"{inst.name}\taxis={inst.axis}\ttype={inst.type}\turl={inst.url or '—'}"
          + (f"\t{opts}" if opts else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--list", action="store_true", help="affiche le registre et quitte")
    i = sub.add_parser("instance", help="fiche d'une instance déclarée")
    i.add_argument("name")
    i.add_argument("--field", help="n'afficher qu'un champ (type, url, axis, ou une option)")
    r = sub.add_parser("resolve", help="montre la résolution d'instance d'un projet")
    r.add_argument("axis", nargs="?",
                   help="axe à résoudre (défaut : tous les axes actifs)")
    r.add_argument("--client", help="entité/client (défaut : détecté du cwd)")
    r.add_argument("--project", help="slug projet (défaut : détecté du cwd)")
    args = ap.parse_args()

    # `PM_CORE_DIR` = racine du core PM (même sens que dans `mmi-pm.py`, qui y
    # cherche `scripts/`). Le daemon `vault-agentd` lit DÉJÀ son registre là
    # (RM2683) : sans cet alignement, `unlock-vault.sh` — qui demande ici le type
    # d'une instance — et le daemon qui la sert pourraient lire deux configs
    # différentes, donc être en désaccord sur le backend. Absent → config d'à côté.
    cfg = PMConfig.load(os.environ.get("PM_CORE_DIR") or None)
    try:
        reg = Registry.from_config(cfg.providers)
    except RegistryError as e:
        sys.exit(f"ERREUR de registre (pm.config.yml :: providers) : {e}")

    if args.list or args.cmd is None:
        cmd_list(reg)
        return
    if args.cmd == "resolve":
        cmd_resolve(cfg, reg, args.axis, args.client, args.project)
    elif args.cmd == "instance":
        try:
            cmd_instance(reg, args.name, args.field)
        except RegistryError as e:
            sys.exit(f"ERREUR : {e}")


if __name__ == "__main__":
    main()
