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
  3. **Structure docs/ (privsep, RM2043)** — frontière mathieu-pm/mathieu :
     `project/` ne contient QUE les canoniques (overview.md, environments.md) ;
     tout autre aspect libre doit vivre dans `docs/` (group-writable, wiki-syncé).
     Un `*.md` libre resté dans `project/` = aspect non migré → erreur.

Sortie : rapport par problème ; exit 0 si tout est cohérent, 1 sinon.
Usage : pm-doctor.py [--quiet]
"""
import argparse
import re
import subprocess
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
    """{(entité, projet): manifeste} de tous les projets.

    RM1994 : lit le manifeste via le lecteur central `cfg.project_meta` (meta.yml,
    sinon fallback frontmatter overview tant que la migration n'est pas finie).
    """
    return {
        (ent, proj): cfg.project_meta(ent, proj)
        for ent, proj, _ in cfg.iter_projects()
    }


def parse_ref(value):
    """'<entité>/<projet>' → (entité, projet) ou None si malformé."""
    if not isinstance(value, str) or value.count("/") != 1:
        return None
    ent, proj = value.split("/")
    return (ent.strip(), proj.strip()) if ent.strip() and proj.strip() else None


# Aspects qui RESTENT dans project/ (canoniques) — cf. pm-docs-migrate. Tout autre
# *.md dans project/ est un aspect libre non migré vers docs/ (privsep RM2043).
CANONICAL_PROJECT_DOCS = {"overview.md", "environments.md"}


def check_docs_structure(cfg, errors):
    """Invariant privsep (RM2043) : aucun aspect libre résiduel dans `project/`."""
    for ent, proj, _ in cfg.iter_projects():
        project_dir = cfg.path("project_dir", entity=ent, project=proj)
        if not project_dir.is_dir():
            continue
        for f in sorted(project_dir.glob("*.md")):
            if f.name not in CANONICAL_PROJECT_DOCS:
                errors.append(f"{ent}/{proj} : aspect libre '{f.name}' resté dans "
                              f"project/ — doit être migré vers docs/ "
                              f"(pm-docs-migrate --project {ent}/{proj})")


def check_partner_links(cfg, ovs, errors, warns):
    """Providers secondaires (RM2653) : conf saine + `link.policy: required` honoré.

    Deux contrôles, l'un structurel l'autre par ticket :
      * la déclaration `providers.task[]` du projet se résout (un primaire, instances
        connues du registre, pas de `link:`/`sync:` sur le primaire) → **erreur** ;
      * quand un secondaire est `required` (cas MatNat : « tout ce que je fais pour eux
        doit être rattaché chez eux »), tout ticket **ouvert** doit porter son lien
        `partner_issue` → **avertissement** (le rattachement reste un geste humain).
    """
    try:
        import pm_partner
        from pm_registry import Registry, RegistryError
    except ImportError:
        return
    try:
        reg = Registry.from_config(cfg.providers)
    except RegistryError as e:
        errors.append(f"registre providers (pm.config.yml) : {e}")
        return

    for (ent, proj), fm in sorted(ovs.items()):
        if not fm:
            continue
        me = f"{ent}/{proj}"
        try:
            required = pm_partner.required_secondaries(fm, reg)
        except RegistryError as e:
            errors.append(f"{me} : providers.task invalide — {e}")
            continue
        if not required:
            continue
        tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md"):
                continue
            m = FM_RE.match(f.read_text(encoding="utf-8"))
            if not m:
                continue
            try:
                tfm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                continue
            if tfm.get("status") == "ferme":
                continue        # un ticket clos ne se rattache plus utilement
            missing = pm_partner.missing_links(tfm, fm, reg)
            if missing:
                warns.append(f"{me} : RM{tfm.get('redmine_id')} sans lien partenaire "
                             f"{', '.join(missing)} (link.policy: required) — "
                             f"pm-task-partner link {tfm.get('redmine_id')} "
                             f"--instance {missing[0]} --issue <id>")


def check_claude_hooks(warns):
    """Hooks PM du profil Claude Code (RM2306) : sans eux, la conso interactive
    n'est pas tickée (tokens_total=0) → sous-comptage silencieux du ROI. Délègue
    à pm-claude-hooks-sync.py --check (source unique du bloc canonique)."""
    sync = Path(__file__).resolve().parent / "pm-claude-hooks-sync.py"
    try:
        r = subprocess.run([sys.executable, str(sync), "--check"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        warns.append(f"hooks Claude Code : contrôle impossible ({e})")
        return
    if r.returncode != 0:
        detail = ", ".join(l.strip("- ") for l in r.stdout.splitlines() if l.startswith("  -"))
        warns.append(f"hooks PM absents du profil Claude Code ({detail or 'voir --check'}) "
                     f"→ conso interactive non tickée ; lancer pm-claude-hooks-sync.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true", help="N'affiche que les problèmes")
    args = ap.parse_args()

    cfg = PMConfig.load()
    ovs = load_overviews(cfg)
    entities = {e for e, _ in ovs}
    errors, warns = [], []

    # 3. Invariant de structure docs/ (privsep RM2043)
    check_docs_structure(cfg, errors)

    # 4. Hooks PM du profil Claude Code de la machine (RM2306)
    check_claude_hooks(warns)

    # 5. Providers secondaires & rattachements partenaires obligatoires (RM2654)
    check_partner_links(cfg, ovs, errors, warns)

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
