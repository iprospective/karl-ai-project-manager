#!/usr/bin/env python3
"""pm-docs-migrate — sort les aspects-docs LIBRES de .mmi-pm/project/ vers .mmi-pm/docs/ (RM2043).

Étape 0 du volet privsep PM (CDC §5). Le discriminant n'est pas « prose vs structuré »
mais « a un mécanisme de réconciliation (wiki-sync 3-way) ou pas » :
  - RESTENT dans `.mmi-pm/project/` (canoniques, consommés par l'outillage) : overview.md,
    environments.md (+ whitelist) → couche mathieu-pm stricte, mutation via mmi-pm.
  - PARTENT vers `.mmi-pm/docs/` (libres, wiki-syncés, éditables par mathieu via le groupe) :
    tous les autres aspects (roadmap, data-model, orchestrator, migration-plan, …).

Cible `.mmi-pm/docs/` (décision : docs DANS .mmi-pm + symlink workspace ; pattern var/ —
le dossier reste mathieu-pm, group-write 2775 posé au verrou ; cf. CDC §5 révisé). Pour
les projets co-localisés, crée aussi le symlink de confort `<workspace>/docs → .mmi-pm/docs`.

Idempotent (2e run = no-op). `--dry-run` prévisualise. `--reverse` annule (docs/ → project/).
Ne touche PAS au git : il MOVE les fichiers ; committer le repo ai-projects est un geste séparé.

Usage : pm-docs-migrate [--project <entity>/<projet> | --all] [--dry-run] [--reverse]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

# Aspects qui RESTENT dans project/ (canoniques, consommés par l'outillage). Tout le reste
# des *.md de project/ part vers docs/.
CANONICAL = {"overview.md", "environments.md"}


def log(msg):
    print(msg)


def migrate_one(mmi: Path, projects_root: Path, dry: bool, reverse: bool):
    """Retourne (n_moves, n_symlink) effectués (ou prévus en dry-run) pour ce projet."""
    project_dir = mmi / "project"
    docs_dir = mmi / "docs"
    moves = 0
    symlinks = 0

    if reverse:
        if docs_dir.is_dir():
            for f in sorted(docs_dir.glob("*.md")):
                dest = project_dir / f.name
                log(f"  ← {f.relative_to(mmi)}  →  {dest.relative_to(mmi)}")
                if not dry:
                    project_dir.mkdir(parents=True, exist_ok=True)
                    os.rename(f, dest)
                moves += 1
        return moves, 0

    # Forward : aspects libres project/*.md (hors canoniques) → docs/
    if project_dir.is_dir():
        free = [f for f in sorted(project_dir.glob("*.md")) if f.name not in CANONICAL]
        for f in free:
            dest = docs_dir / f.name
            log(f"  → {f.relative_to(mmi)}  →  {dest.relative_to(mmi)}")
            if not dry:
                docs_dir.mkdir(parents=True, exist_ok=True)
                os.rename(f, dest)
            moves += 1

    # Symlink de confort <workspace>/docs → .mmi-pm/docs — UNIQUEMENT si le projet a
    # réellement un docs/ (aspects déplacés ce run, ou docs/ déjà présent). Sans ça, un
    # projet sans aspect libre récolterait un symlink PENDANT vers un .mmi-pm/docs absent
    # (pollution, notamment des repos tiers). Co-localisé seulement : cible résolue HORS
    # du projects_root (sinon on ne touche pas l'arbo interne). En dry-run, docs_dir n'est
    # pas créé → on se base sur moves>0 pour la prévisualisation.
    resolved = mmi.resolve()
    colocated = not _is_under(resolved, projects_root)
    has_docs = moves > 0 or docs_dir.is_dir()
    if colocated and has_docs:
        workspace = resolved.parent
        link = workspace / "docs"
        rel_target = f"{resolved.name}/docs"  # ex: .mmi-pm/docs
        if link.is_symlink():
            if os.readlink(link) != rel_target:
                log(f"  ~ symlink existant divergent : {link} -> {os.readlink(link)} (laissé tel quel)")
        elif link.exists():
            log(f"  ⚠ {link} existe et n'est PAS un symlink — symlink non créé")
        else:
            log(f"  ⊕ symlink {link}  →  {rel_target}")
            if not dry:
                os.symlink(rel_target, link)
            symlinks += 1

    return moves, symlinks


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main():
    cfg = PMConfig.load()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project", help="cible un seul projet : <entity>/<projet>")
    g.add_argument("--all", action="store_true", help="tous les projets")
    ap.add_argument("--dry-run", action="store_true", help="prévisualise sans rien déplacer")
    ap.add_argument("--reverse", action="store_true", help="annule la migration (docs/ → project/)")
    args = ap.parse_args()

    if args.project:
        if "/" not in args.project:
            sys.exit("ERREUR : --project attend <entity>/<projet>")
        ent, proj = args.project.split("/", 1)
        targets = [(e, p, path) for e, p, path in cfg.iter_projects(entity=ent) if p == proj]
        if not targets:
            sys.exit(f"ERREUR : projet '{args.project}' introuvable")
    else:
        targets = list(cfg.iter_projects())

    sens = "REVERSE (docs/ → project/)" if args.reverse else "migration (project/ → docs/)"
    log(f"pm-docs-migrate — {sens}{' [dry-run]' if args.dry_run else ''} — {len(targets)} projet(s)\n")
    tot_m = tot_s = 0
    touched = 0
    for ent, proj, path in targets:
        mmi = path  # iter_projects yield le .mmi-pm (réel ou symlink suivi par is_dir/resolve)
        m, s = migrate_one(mmi, cfg.projects_root, args.dry_run, args.reverse)
        if m or s:
            log(f"• {ent}/{proj} : {m} aspect(s)" + (f", {s} symlink" if s else ""))
            touched += 1
        tot_m += m; tot_s += s
    log(f"\nTotal : {tot_m} aspect(s) déplacé(s), {tot_s} symlink(s), {touched} projet(s) touché(s)"
        f"{' [dry-run, rien écrit]' if args.dry_run else ''}.")
    if not args.dry_run and (tot_m or tot_s):
        log("→ committer le repo ai-projects (projects/) pour figer le déplacement.")


if __name__ == "__main__":
    main()
