#!/usr/bin/env python3
"""pm-doctor — Vérifie la cohérence des données PM (RM1923 #2, v1).

Valide les champs redondants par construction des `project/overview.md`
(NORMS module project-modeling) :

  1. **used_by_clients ↔ provided_by** (partage cross-client)
     - consommateur : `provided_by: <entité>/<projet>` → le fournisseur doit
       exister ET lister l'entité du consommateur dans `used_by_clients[]`.
     - fournisseur : chaque entité de `used_by_clients[]` doit exister ; si
       aucun de ses projets ne pointe `provided_by` vers le fournisseur →
       avertissement (déclaration unilatérale).
  2. **implements ↔ implemented_by** (relation implémentation, RM1837)
     - listes symétriques : A.implements ∋ B ⇔ B.implemented_by ∋ A.
     - chaque cible `<entité>/<projet>` doit exister.

Sortie : rapport par problème ; exit 0 si tout est cohérent, 1 sinon.
Usage : pm-doctor.py [--quiet]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def load_overviews(cfg):
    """{(entité, projet): frontmatter} de tous les project/overview.md lisibles."""
    out = {}
    for ent, proj, _ in cfg.iter_projects():
        p = cfg.path("project_dir", entity=ent, project=proj) / "overview.md"
        if not p.is_file():
            continue
        m = FM_RE.match(p.read_text(encoding="utf-8", errors="replace"))
        if not m:
            continue
        try:
            out[(ent, proj)] = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            out[(ent, proj)] = None  # frontmatter illisible = problème
    return out


def parse_ref(value):
    """'<entité>/<projet>' → (entité, projet) ou None si malformé."""
    if not isinstance(value, str) or value.count("/") != 1:
        return None
    ent, proj = value.split("/")
    return (ent.strip(), proj.strip()) if ent.strip() and proj.strip() else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true", help="N'affiche que les problèmes")
    args = ap.parse_args()

    cfg = PMConfig.load()
    ovs = load_overviews(cfg)
    entities = {e for e, _ in ovs}
    errors, warns = [], []

    for (ent, proj), fm in sorted(ovs.items()):
        me = f"{ent}/{proj}"
        if fm is None:
            errors.append(f"{me} : frontmatter overview.md illisible (YAML)")
            continue

        # 1a. consommateur → fournisseur
        pb = fm.get("provided_by")
        if pb:
            ref = parse_ref(pb)
            if not ref:
                errors.append(f"{me} : provided_by malformé ({pb!r}, attendu '<entité>/<projet>')")
            elif ref not in ovs:
                errors.append(f"{me} : provided_by → {pb} introuvable")
            else:
                ubc = (ovs[ref] or {}).get("used_by_clients") or []
                if ent not in ubc:
                    errors.append(f"{me} : provided_by → {pb}, mais {pb} ne liste pas "
                                  f"'{ent}' dans used_by_clients{ubc}")

        # 1b. fournisseur → consommateurs
        for client in (fm.get("used_by_clients") or []):
            if client not in entities:
                errors.append(f"{me} : used_by_clients contient '{client}' — entité inconnue")
            elif not any(e == client and ((o or {}).get("provided_by") == me)
                         for (e, _), o in ovs.items()):
                warns.append(f"{me} : used_by_clients ∋ '{client}' mais aucun projet de "
                             f"'{client}' ne déclare provided_by: {me} (unilatéral)")

        # 2. implements ↔ implemented_by (symétrie des deux côtés)
        for field, mirror in (("implements", "implemented_by"),
                              ("implemented_by", "implements")):
            for tgt in (fm.get(field) or []):
                ref = parse_ref(tgt)
                if not ref:
                    errors.append(f"{me} : {field} contient {tgt!r} (attendu '<entité>/<projet>')")
                elif ref not in ovs:
                    errors.append(f"{me} : {field} → {tgt} introuvable")
                elif me not in ((ovs[ref] or {}).get(mirror) or []):
                    errors.append(f"{me} : {field} → {tgt}, mais {tgt} ne liste pas "
                                  f"'{me}' dans {mirror}[] (paire non symétrique)")

    if not args.quiet:
        print(f"== pm-doctor — {len(ovs)} projet(s) scannés ==")
    for e in errors:
        print(f"  ✗ {e}")
    for w in warns:
        print(f"  ⚠ {w}")
    if not errors and not warns and not args.quiet:
        print("  ✓ paires used_by_clients↔provided_by et implements↔implemented_by cohérentes")
    print(f"== {'ÉCHEC' if errors else 'OK'} — {len(errors)} erreur(s), {len(warns)} avertissement(s) ==")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
