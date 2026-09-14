#!/usr/bin/env python3
"""pm-module — les modules de PM : lister, décrire, contrôler, mesurer l'écart (RM3145, lot 0).

PM porte déjà sept mécanismes d'extension, chacun réinventé dans son coin. Ce verbe donne la
première chose qui manquait : **une vue unique**, qui montre autant ce qui est décrit que ce qui
ne l'est pas. Un inventaire qui tairait le second serait flatteur et faux.

  mmi-pm module list                 les modules décrits, leur état, ce qu'ils fournissent
  mmi-pm module show <nom>           un module : description, dépendances, apports, erreurs
  mmi-pm module check                contrôle : manifestes, dépendances, cycles (code 1 si un module casse)
  mmi-pm module inventory            les 7 registres, item par item, décrits ou non
  --json                             pour le cockpit et les scripts

Ce verbe ne charge aucun code de module et n'active rien : au lot 0 il DÉCRIT. Déplacer d'abord et
constater ensuite, c'est se priver de la seule mesure qui rend le chantier discutable.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_modules as M                                   # noqa: E402

ETAT = {True: "✓", False: "✗"}


def _resolution(mods):
    return M.resout(mods)


def cmd_list(a) -> int:
    mods = M.decouvre()
    r = _resolution(mods)
    if a.json:
        print(json.dumps({"modules": [m.as_dict() for m in mods], **r}, ensure_ascii=False, indent=1))
        return 0
    if not mods:
        print(f"aucun module décrit dans {M.racine()}")
        return 0
    for m in sorted(mods, key=lambda x: x.name):
        etat = "désactivé" if not m.enabled else ("bloqué" if m.name in r["bloques"] else "actif")
        print(f"  {ETAT[m.ok]} {m.name:24} {m.version:8} {etat:10} {m.label}")
        for k, n in m.fournit():
            print(f"  {'':26} · {k} {n}")
        for r in [x for x in M.routes(modules=mods) if x.module == m.name and x.ok]:
            print(f"  {'':26} → {r.method} {r.url}")
        for motif in m.errors + r["bloques"].get(m.name, []):
            print(f"  {'':26} ⚠ {motif}")
    print(f"\n  {len(mods)} module(s) · ordre de chargement : " + (" → ".join(r["ordre"]) or "—"))
    return 0


def cmd_show(a) -> int:
    mods = M.decouvre()
    m = next((x for x in mods if x.name == a.name), None)
    if not m:
        sys.exit(f"ERREUR : aucun module « {a.name} » dans {M.racine()}")
    r = _resolution(mods)
    if a.json:
        print(json.dumps({**m.as_dict(), "bloque": r["bloques"].get(m.name, [])},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"{m.label} ({m.name} {m.version})")
    print(f"  {m.description}")
    print(f"  dossier    {m.path.parent}")
    print(f"  état       " + ("désactivé" if not m.enabled else ("bloqué" if m.name in r["bloques"] else "actif")))
    print(f"  requiert   " + (", ".join(m.requires) or "rien"))
    # Ce qui casserait si on le désactivait : la question qu'on se pose au moment de cliquer.
    dependants = sorted(x.name for x in mods if any(d == m.name for d, _, _ in x.deps()))
    print(f"  requis par " + (", ".join(dependants) or "personne"))
    print(f"  fournit    " + (", ".join(f"{k} {n}" for k, n in m.fournit()) or "rien"))
    # `r` porte déjà la résolution : une boucle qui le réutiliserait écraserait les motifs de blocage.
    for rt in [x for x in M.routes(modules=mods) if x.module == m.name]:
        print(f"  {'sert' if rt.ok else '⚠   ':<10} {rt.method} {rt.url}  → {rt.handler}"
              + ("" if rt.ok else "  " + " ; ".join(rt.errors)))
    trs = [t for t in M.triggers(modules=mods) if t.module == m.name]
    for t in trs:
        print(f"  {'réagit' if t.ok else '⚠     ':<10} {t.on or '?'} → {' '.join(t.run) or '?'}"
              + ("" if t.ok else "  " + " ; ".join(t.errors)))
    for motif in m.errors + r["bloques"].get(m.name, []):
        print(f"  ⚠ {motif}")
    return 0


def cmd_check(a) -> int:
    mods = M.decouvre()
    r = _resolution(mods)
    casses = [m for m in mods if not m.ok]
    if a.json:
        print(json.dumps({"ok": not casses and not r["bloques"] and not r["cycles"],
                          "invalides": [m.name for m in casses], **r}, ensure_ascii=False, indent=1))
        return 1 if (casses or r["bloques"] or r["cycles"]) else 0
    for m in casses:
        print(f"  ✗ {m.name} : " + " ; ".join(m.errors))
    for nom, motifs in sorted(r["bloques"].items()):
        print(f"  ⚠ {nom} bloqué : " + " ; ".join(motifs))
    for c in r["cycles"]:
        print("  ⚠ cycle : " + " → ".join(c))
    if not casses and not r["bloques"] and not r["cycles"]:
        print(f"  ✓ {len(mods)} manifeste(s) valide(s), dépendances résolues, aucun cycle")
        return 0
    return 1


def cmd_inventory(a) -> int:
    mods = M.decouvre()
    inv = M.inventaire(modules=mods)
    if a.json:
        print(json.dumps(inv, ensure_ascii=False, indent=1))
        return 0
    for cle, lignes in sorted(inv["registres"].items()):
        manquants = [x["item"] for x in lignes if not x["decrit"]]
        print(f"  {cle:20} {len(lignes) - len(manquants):>2}/{len(lignes):<3} décrit(s)")
        if manquants and a.verbose:
            for it in manquants:
                print(f"  {'':22} · {it}")
    print(f"\n  {inv['decrits']}/{inv['total']} point(s) d'extension décrit(s) — "
          f"{inv['non_decrits']} encore porté(s) par un registre sans manifeste")
    if not a.verbose and inv["non_decrits"]:
        print("  (--verbose pour les nommer)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="les modules décrits")
    s = sub.add_parser("show", help="un module en détail"); s.add_argument("name")
    sub.add_parser("check", help="contrôle des manifestes et des dépendances")
    sub.add_parser("inventory", help="les registres, décrits ou non")
    a = ap.parse_args()
    return {"show": cmd_show, "check": cmd_check, "inventory": cmd_inventory}.get(a.cmd or "list", cmd_list)(a)


if __name__ == "__main__":
    sys.exit(main())
