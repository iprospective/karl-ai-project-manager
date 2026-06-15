#!/usr/bin/env python3
"""pm-resolver-flip.py — bascule du résolveur PM vers les workspaces co-localisés.

Bascule, **client par client**, les projets PM d'un client : le dossier réel
`ai-projects/clients/<C>/projects/<P>` est remplacé par un **symlink** vers le
`.mmi-pm` co-localisé dans le workspace de code, qui devient ainsi la donnée
**canonique**. Le résolveur (`pm_paths.iter_projects`, patché RM1949) suit le
symlink ⇒ les outils lisent/écrivent désormais dans le `.mmi-pm` co-localisé.

Pour CHAQUE projet du client :
  1. **re-sync** ai-projects → `.mmi-pm` co-localisé (ai-projects est canonique
     jusqu'à la bascule ; le `.mmi-pm` a pu diverger). Exclut `workspace`
     (symlink, recréé après) et `.wiki-sync` (régénérable).
  2. **archive** le dossier réel ai-projects (mv, réversible).
  3. **symlink** ai-projects/<P> → `.mmi-pm` co-localisé.
  4. **recrée** `<.mmi-pm>/workspace → ..` (le `.mmi-pm` est dans le workspace
     de code ⇒ `..` EST le workspace ; garde `workspace_link` résolvable).

Mapping ai-projects ↔ co-localisé **par slug lu dans l'overview** (jamais via le
symlink `workspace` d'ai-projects, qui peut être périmé).

DRY-RUN par défaut. `--execute` pour agir. Idempotent (re-jouable : un projet
déjà basculé = symlink ⇒ ignoré).

Usage :
  pm-resolver-flip.py <client> [--execute] [--workspaces-root DIR]
                       [--archive-dir DIR] [--no-resync]
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_paths", str(_HERE / "pm_paths.py"))
pm_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_paths)
PMConfig = pm_paths.PMConfig

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
import yaml  # noqa: E402

EXCLUDES = ["workspace", ".wiki-sync"]  # exclus du re-sync (recréés / régénérés)


def _read_client_slug(overview: Path):
    """Lit `client` + `slug` dans le frontmatter d'un project/overview.md."""
    try:
        m = _FM_RE.match(overview.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None, None
    if not m:
        return None, None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, None
    return fm.get("client"), fm.get("slug")


def build_colocated_map(workspaces_root: Path, maxdepth: int = 6):
    """Scanne `workspaces_root` pour les `.mmi-pm/project/overview.md` et retourne
    `{(client, slug): mmipm_path}`. Indépendant du nommage des dossiers (lit le
    client+slug dans l'overview ⇒ robuste aux divergences dossier↔slug)."""
    out = {}
    # find rapide, borné en profondeur, en évitant les gros arbres de code.
    try:
        res = subprocess.run(
            ["find", str(workspaces_root), "-maxdepth", str(maxdepth),
             "-type", "d", "-name", ".git", "-prune", "-o",
             "-path", "*/.mmi-pm/project", "-name", "project",
             "-type", "d", "-print"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERREUR find : {e.stderr}")
    for line in res.stdout.splitlines():
        proj_dir = Path(line)
        mmipm = proj_dir.parent  # .../.mmi-pm
        if mmipm.name != ".mmi-pm":
            continue
        client, slug = _read_client_slug(proj_dir / "overview.md")
        if client and slug:
            out[(str(client), str(slug))] = mmipm.resolve()
    return out


def build_client_colocated_map(workspaces_root: Path, maxdepth: int = 4):
    """Scanne `workspaces_root` pour les `.mmi-pm-client/client/overview.md` et
    retourne `{client_slug: mmipm_client_path}`. Mapping par slug lu dans
    l'overview (robuste au nommage de dossier, ex. perso↔lemathou,
    lydie-mariller↔lydiemariller)."""
    out = {}
    try:
        res = subprocess.run(
            ["find", str(workspaces_root), "-maxdepth", str(maxdepth),
             "-type", "d", "-name", ".git", "-prune", "-o",
             "-type", "d", "-name", ".mmi-pm-client", "-print"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERREUR find (client) : {e.stderr}")
    for line in res.stdout.splitlines():
        mmipmc = Path(line)
        # Un overview de CLIENT porte son identité dans `slug:` (pas `client:`).
        client, slug = _read_client_slug(mmipmc / "client" / "overview.md")
        key = slug or client
        if key:
            out[str(key)] = mmipmc.resolve()
    return out


# Sous-dossiers du niveau client à basculer (projects/ reste réel : il contient
# les symlinks de projets ; pas de workspace symlink à recréer ici).
CLIENT_SUBDIRS = ["client", "memory", "projects_used"]


def run(cmd, dry):
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    if not dry:
        subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description="Bascule du résolveur PM (RM1949).")
    ap.add_argument("client", help="slug du client à basculer (ex: calicote)")
    ap.add_argument("--execute", action="store_true",
                    help="exécuter réellement (défaut : dry-run)")
    ap.add_argument("--workspaces-root", default="/zfs/workspaces",
                    help="racine des workspaces de code (défaut: /zfs/workspaces)")
    ap.add_argument("--archive-dir", default=None,
                    help="dossier d'archive (défaut: <projects_root>/_archive-resolver-flip)")
    ap.add_argument("--no-resync", action="store_true",
                    help="ne pas re-syncer ai-projects → .mmi-pm (flip seul)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="slug de projet à ne PAS basculer (répétable)")
    ap.add_argument("--no-client-level", action="store_true",
                    help="ne pas basculer le niveau client (client/, memory/, projects_used/)")
    args = ap.parse_args()

    dry = not args.execute
    cfg = PMConfig.load()
    wsroot = Path(args.workspaces_root).resolve()
    archive_dir = Path(args.archive_dir) if args.archive_dir else (
        cfg.projects_root / "_archive-resolver-flip"
    )

    mode = "DRY-RUN (rien n'est modifié)" if dry else "EXECUTE"
    print(f"== pm-resolver-flip : client={args.client} — {mode} ==")
    print(f"   workspaces_root = {wsroot}")
    print(f"   archive_dir     = {archive_dir}")

    colo = build_colocated_map(wsroot)
    print(f"   {len(colo)} .mmi-pm co-localisés découverts (tous clients)")

    projects = list(cfg.iter_projects(entity=args.client))
    if not projects:
        sys.exit(f"ERREUR : aucun projet ai-projects pour le client '{args.client}'")

    proot = cfg.projects_root.resolve()
    n_flip = n_skip = n_nocolo = n_err = 0
    for ent, slug, ppath in projects:
        print(f"\n── {ent}/{slug}")
        if slug in args.exclude:
            print("   ⏭  exclu explicitement (--exclude) — ignoré")
            n_skip += 1
            continue
        if ppath.is_symlink():
            print(f"   ⏭  déjà basculé (symlink → {os.readlink(ppath)}) — ignoré")
            n_skip += 1
            continue
        target = colo.get((ent, slug))
        if target is None:
            print(f"   ⏭  pas de .mmi-pm co-localisé pour ({ent},{slug}) — non "
                  f"co-localisé (ex: l'outil PM lui-même) — ignoré")
            n_nocolo += 1
            continue
        # Garde dur : la cible doit vivre HORS d'ai-projects (sinon flip
        # circulaire — ex. un .mmi-pm encore symlinké vers ai-projects).
        if str(target).startswith(str(proot)):
            print(f"   ✗  REFUS : cible {target} est DANS ai-projects "
                  f"(non co-localisée pour de vrai) — flip circulaire évité")
            n_err += 1
            continue
        print(f"   source ai-projects : {ppath}")
        print(f"   cible co-localisée : {target}")

        # 1. re-sync ai-projects → co-localisé
        if not args.no_resync:
            print("   1) re-sync ai-projects → .mmi-pm (rsync -a --delete, exclut "
                  f"{EXCLUDES})")
            rsync = ["rsync", "-a", "--delete"]
            for ex in EXCLUDES:
                rsync += ["--exclude", ex]
            rsync += [f"{ppath}/", f"{target}/"]
            run(rsync, dry)

        # 2. archive du dossier réel
        dest = archive_dir / ent / slug
        print(f"   2) archive : mv {ppath} → {dest}")
        if not dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                sys.exit(f"ERREUR : archive déjà existante : {dest} (nettoyer avant)")
        run(["mv", str(ppath), str(dest)], dry)

        # 3. symlink ai-projects → co-localisé
        print(f"   3) symlink : {ppath} → {target}")
        run(["ln", "-s", str(target), str(ppath)], dry)

        # 4. recrée <.mmi-pm>/workspace → .. (relatif)
        ws_link = target / "workspace"
        print(f"   4) workspace symlink : {ws_link} → ..")
        if not dry:
            if ws_link.is_symlink() or ws_link.exists():
                ws_link.unlink()
            ws_link.symlink_to("..")
        else:
            print("    $ ln -s .. " + str(ws_link))
        n_flip += 1

    # ── Niveau client : client/, memory/, projects_used/ → symlinks ─────────
    n_cflip = n_cskip = 0
    if not args.no_client_level:
        client_colo = build_client_colocated_map(wsroot)
        ctarget = client_colo.get(args.client)
        print(f"\n══ niveau client : {args.client}")
        if ctarget is None:
            print("   ⏭  pas de .mmi-pm-client co-localisé (produit/différé) — ignoré")
        elif str(ctarget).startswith(str(proot)):
            print(f"   ✗  REFUS : .mmi-pm-client {ctarget} est DANS ai-projects")
            n_err += 1
        else:
            print(f"   cible .mmi-pm-client : {ctarget}")
            for sub in CLIENT_SUBDIRS:
                src = cfg.path("entity", entity=args.client) / sub
                dst = ctarget / sub
                print(f"   ── {sub}")
                if not src.exists():
                    print("      ⏭  absent côté ai-projects — ignoré")
                    continue
                if src.is_symlink():
                    print(f"      ⏭  déjà basculé (symlink → {os.readlink(src)})")
                    n_cskip += 1
                    continue
                if not dst.exists():
                    print(f"      ✗  cible {dst} absente — ignoré")
                    n_err += 1
                    continue
                if not args.no_resync:
                    print("      1) re-sync (rsync -a --delete)")
                    run(["rsync", "-a", "--delete", f"{src}/", f"{dst}/"], dry)
                cdest = archive_dir / args.client / "__client__" / sub
                print(f"      2) archive : mv {src} → {cdest}")
                if not dry:
                    cdest.parent.mkdir(parents=True, exist_ok=True)
                    if cdest.exists():
                        sys.exit(f"ERREUR : archive déjà existante : {cdest}")
                run(["mv", str(src), str(cdest)], dry)
                print(f"      3) symlink : {src} → {dst}")
                run(["ln", "-s", str(dst), str(src)], dry)
                n_cflip += 1

    print(f"\n== Bilan : {n_flip} projet(s) basculé(s), {n_skip} ignoré(s), "
          f"{n_nocolo} non co-localisé(s) | client-level {n_cflip} basculé(s), "
          f"{n_cskip} ignoré(s) | {n_err} erreur(s) ==")
    if dry:
        print("   (DRY-RUN — relancer avec --execute pour appliquer)")
    if n_err:
        sys.exit(2)


if __name__ == "__main__":
    main()
