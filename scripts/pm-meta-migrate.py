#!/usr/bin/env python3
"""pm-meta-migrate — sépare la donnée machine (meta.yml) de la prose (overview.md). RM1994.

Le frontmatter d'`overview.md` devient `meta.yml` ; `overview.md` redevient de la prose pure.

Par défaut : **DRY-RUN** (n'écrit rien).
  --apply   écrit réellement les fichiers.
  --strip   PHASE 2 : retire le frontmatter d'`overview.md` (prose pure). À NE FAIRE
            qu'APRÈS migration des lecteurs vers `pm_paths.project_meta/client_meta`
            (le shim lit encore le frontmatter tant qu'il est là).

Phasage sûr : (1) `--apply` seul → meta.yml créés, frontmatter conservé, lecteurs OK via
le shim ; (2) migrer les lecteurs ; (3) `--apply --strip` → prose pure.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_fm(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def gen_one(overview_path: Path, meta_path: Path, dry: bool, strip: bool):
    if not overview_path.is_file():
        return "pas d'overview.md (skip)"
    text = overview_path.read_text(encoding="utf-8")
    fm_raw, body = split_fm(text)
    if fm_raw is None:
        return "overview sans frontmatter (déjà migré ?)"
    fm = yaml.safe_load(fm_raw) or {}
    actions = []
    if meta_path.exists():
        actions.append("meta.yml existe (conservé)")
    else:
        actions.append("crée meta.yml")
        if not dry:
            meta_path.write_text(
                yaml.safe_dump(fm, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
    if strip:
        actions.append("retire frontmatter overview")
        if not dry:
            overview_path.write_text(body.lstrip("\n"), encoding="utf-8")
    return " ; ".join(actions)


def main():
    ap = argparse.ArgumentParser(description="Génère meta.yml depuis le frontmatter d'overview (RM1994).")
    ap.add_argument("--apply", action="store_true", help="écrit réellement (défaut: dry-run)")
    ap.add_argument("--strip", action="store_true", help="phase 2 : retire le frontmatter d'overview")
    args = ap.parse_args()
    dry = not args.apply

    cfg = PMConfig.load()
    mode = "DRY-RUN" if dry else "APPLY"
    if args.strip:
        mode += " +STRIP"
    print(f"== pm-meta-migrate ({mode}) ==")

    np = nc = 0
    for ent, proj, _ in cfg.iter_projects():
        base = cfg.path("project", entity=ent, project=proj)
        res = gen_one(base / "project" / "overview.md", base / "meta.yml", dry, args.strip)
        print(f"  projet {ent}/{proj}: {res}")
        np += 1
    for ent, _ in cfg.iter_entities():
        cdir = cfg.path("entity_client_dir", entity=ent)
        try:
            mmi_client = cdir.resolve().parent
        except OSError:
            mmi_client = cdir.parent
        # Garde-fou : ne générer que pour un vrai dossier .mmi-pm-client co-localisé
        # (les produits non co-localisés — redmine/roundcube/prestashop — résolvent vers
        # l'index ai-projects, pas vers un .mmi-pm-client : on les saute).
        if mmi_client.name != ".mmi-pm-client":
            print(f"  client {ent}: non co-localisé (pas de .mmi-pm-client) — skip")
            continue
        res = gen_one(cdir / "overview.md", mmi_client / "meta.yml", dry, args.strip)
        print(f"  client {ent}: {res}")
        nc += 1
    print(f"== {np} projet(s), {nc} client(s) — {mode} ==")
    if dry:
        print("   (dry-run : rien écrit. Relancer avec --apply pour générer les meta.yml.)")


if __name__ == "__main__":
    main()
