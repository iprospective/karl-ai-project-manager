#!/usr/bin/env python3
"""pm-env-migrate — migre un workspace PRÉ-NORME vers le layout RM1993 (RM2028).

Adoption IN-PLACE (zéro re-clone) de l'existant. Patron pré-norme constaté
(uniforme sur calicote/*) :

    <ws>/.git        repo "<projet>-core" (branche main) qui tracke .mmi-pm/   → RESTE
    <ws>/dev/.git    CLONE SÉPARÉ du repo de CODE, branche dev, parfois dirty
    <ws>/test/.git   autre CLONE SÉPARÉ du même code (env test)

Cible :

    <ws>/repos/<code>.git        bare unique (issu du clone `dev`), gc.auto=0
    <ws>/envs/<code>-dev         worktree (ex-dev/) — branche d'origine
    <ws>/envs/<code>-test        worktree (ex-test/)
    <ws>/.mmi-pm/meta.yml › repos:   backfillé
    <ws>/.gitignore              réécrit au format nouveau norme

PRÉSERVATION TOTALE — l'adoption se fait par `git worktree add --no-checkout`
(établit la liaison git, n'écrit AUCUN fichier) puis **rsync des fichiers de
travail existants** : on conserve donc tracké-dirty + untracked + **fichiers
gitignorés/locaux** (vendor/, conf.php…) — ce qu'un `git stash` PERDRAIT.

SÉCURITÉ : snapshot ZFS avant mutation (rollback si VERIFY échoue) ; refus propre
si submodules (cas dolibarr « festival » → RM1837) ou collision de branche.

PÉRIMÈTRE v1 : 1+ repo(s) de code en clones séparés dev/test, SANS submodule.
Hors v1 (refus + renvoi) : submodules/N-2 → RM1837 ; implements → RM1837/RM1993.

Zéro privilège git/fs (KARL_USER). Le snapshot ZFS peut requérir un droit délégué
(sinon `--no-snapshot` + snapshot manuel en pré-requis).
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pm-env-migrate: PyYAML requis (apt install python3-yaml)")

EXCLUDE_DIRS = {"repos", "envs", "tmp", "sessions", "logs", "data", ".mmi-pm",
                ".mmi-pm-client", ".claude", "documents", "node_modules", "vendor"}
GITIGNORE = (
    "# Généré par pm-env-migrate (RM2028/RM1993). Seul .mmi-pm/ est tracké ;\n"
    "# code en worktrees, bares, runtime = local/régénérable.\n"
    "/*\n"
    "!/.gitignore\n"
    "!/.mmi-pm/\n"
)


class Ctx:
    def __init__(self, dry, verbose):
        self.dry = dry
        self.verbose = verbose
        self.changed = 0
        self.warnings = []

    def act(self, msg):
        print(f"  {'[dry] ' if self.dry else ''}{msg}")
        self.changed += 1

    def skip(self, msg):
        if self.verbose:
            print(f"  · {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        sys.stderr.write(f"  ⚠ {msg}\n")


def die(msg):
    sys.exit(f"pm-env-migrate: {msg}")


def git(args, cwd=None, check=True, quiet=False):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        if not quiet:
            sys.stderr.write(r.stderr)
        die(f"git {' '.join(args)} (cwd={cwd}) a échoué (rc={r.returncode})")
    return r.returncode, r.stdout.strip()


def run(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"{' '.join(args)} a échoué : {r.stderr.strip()}")
    return r.returncode, r.stdout.strip()


def best_effort_rmtree(ctx, path):
    """rmtree tolérant (RM2031) : sur échec — typiquement des fichiers possédés
    par un AUTRE user (cache Symfony `var/cache/…` du pool FPM, ex. `mathieu-www`)
    que `KARL_USER` ne peut pas `rmdir` — NE PLANTE PAS. Avertit avec la commande
    de nettoyage privilégié et laisse le résidu (repéré ensuite par VERIFY).
    Rend True si supprimé, False sinon."""
    try:
        shutil.rmtree(path)
        return True
    except OSError as e:
        ctx.warn(f"nettoyage {path.name} impossible ({e.strerror or e}) — résidu "
                 f"laissé (fichiers d'un autre propriétaire, ex. cache FPM). "
                 f"Nettoyage privilégié : sudo rm -rf {path}")
        return False


# ---------------------------------------------------------------- découverte

def find_workspace(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").exists():
            return d
    die(f"aucun `.mmi-pm` en remontant depuis {start} (workspace PM-tracké ?)")


def repo_info(d: Path) -> dict | None:
    """Décrit un repo git situé en `d` (None si pas un repo)."""
    if not (d / ".git").exists():
        return None
    _, origin = git(["-C", str(d), "remote", "get-url", "origin"], check=False, quiet=True)
    _, branch = git(["-C", str(d), "rev-parse", "--abbrev-ref", "HEAD"], check=False, quiet=True)
    _, head = git(["-C", str(d), "rev-parse", "HEAD"], check=False, quiet=True)
    _, dirty = git(["-C", str(d), "status", "--porcelain"], check=False, quiet=True)
    _, stashes = git(["-C", str(d), "stash", "list"], check=False, quiet=True)
    has_sub = (d / ".gitmodules").is_file()
    return {
        "dir": d, "origin": origin or None, "branch": branch or None, "head": head,
        "dirty": len([l for l in dirty.splitlines() if l]),
        "stashes": len([l for l in stashes.splitlines() if l]),
        "submodules": has_sub,
    }


def code_basename(origin: str) -> str:
    """`gitlab:calicote/doli-presta-sync.git` → `doli-presta-sync`."""
    name = origin.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return name[:-4] if name.endswith(".git") else name


def discover(ws: Path) -> tuple[dict, dict]:
    """Retourne (root, groups). root = repo racine (reste). groups = {code: [clones]}."""
    root = repo_info(ws)
    groups: dict[str, list] = {}
    for entry in sorted(ws.iterdir()):
        if not entry.is_dir() or entry.name in EXCLUDE_DIRS or entry.name.startswith("."):
            continue
        info = repo_info(entry)
        if not info or not info["origin"]:
            continue
        code = code_basename(info["origin"])
        info["usage"] = entry.name  # dev, test, …
        groups.setdefault(code, []).append(info)
    return root, groups


def print_plan(ws, root, groups):
    print(f"workspace : {ws}")
    if root:
        print(f"  racine    : {root['origin'] or '(sans origin)'} [{root['branch']}] "
              f"— RESTE (tracke .mmi-pm)")
    if not groups:
        print("  (aucun clone de code à migrer)")
    for code, clones in groups.items():
        print(f"  code `{code}` → repos/{code}.git :")
        for c in clones:
            flags = []
            if c["dirty"]:
                flags.append(f"{c['dirty']} dirty")
            if c["stashes"]:
                flags.append(f"{c['stashes']} stash")
            if c["submodules"]:
                flags.append("SUBMODULES")
            tag = f"  ({', '.join(flags)})" if flags else ""
            print(f"      {c['dir'].name}/ [{c['branch']}] → envs/{code}-{c['usage']}{tag}")


def guard(ws, groups, force):
    """Refus propres avant toute mutation."""
    if (ws / "repos").exists() or (ws / "envs").exists():
        if not force:
            die("repos/ ou envs/ existe déjà — workspace partiellement migré ? "
                "(--force pour passer outre, à tes risques)")
    for code, clones in groups.items():
        for c in clones:
            if c["submodules"]:
                die(f"{c['dir'].name}/ contient des submodules (.gitmodules) — cas "
                    f"« festival » NON géré en v1 → RM1837. Migration manuelle.")
        branches = [c["branch"] for c in clones]
        dup = {b for b in branches if branches.count(b) > 1}
        if dup:
            die(f"code `{code}` : collision de branche {dup} entre clones "
                f"(un bare ne peut checkout 2× la même branche) → résoudre à la main.")


# ------------------------------------------------------------------ snapshot

def zfs_dataset(path: Path) -> str | None:
    rc, out = run(["zfs", "list", "-H", "-o", "name,mountpoint"], check=False)
    if rc != 0:
        return None
    best, blen = None, -1
    sp = str(path)
    for line in out.splitlines():
        try:
            name, mp = line.split("\t")
        except ValueError:
            continue
        if mp in ("none", "legacy", "-"):
            continue
        if (sp == mp or sp.startswith(mp.rstrip("/") + "/")) and len(mp) > blen:
            best, blen = name, len(mp)
    return best


def snapshot(ctx, ws, no_snapshot) -> str | None:
    if no_snapshot:
        ctx.warn("snapshot ZFS désactivé (--no-snapshot) — réversibilité à ta charge.")
        return None
    ds = zfs_dataset(ws.resolve())
    if not ds:
        die(f"{ws} n'est pas sur un dataset ZFS — impossible de snapshot. "
            f"Utilise --no-snapshot (et sauvegarde toi-même) pour forcer.")
    snap = f"{ds}@pm-env-migrate-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ctx.act(f"zfs snapshot {snap}")
    if not ctx.dry:
        rc, _ = run(["zfs", "snapshot", snap], check=False)
        if rc != 0:
            die(f"`zfs snapshot {snap}` a échoué (droit délégué manquant ?). "
                f"Snapshot manuel + --no-snapshot, ou délègue le droit.")
    return snap


# ------------------------------------------------------------------- execute

def make_bare(ctx, ws, code, basis):
    """Transforme le .git du clone `basis` en bare repos/<code>.git."""
    bare = ws / "repos" / f"{code}.git"
    ctx.act(f"mv {basis['dir'].name}/.git → repos/{code}.git  (+ core.bare, gc.auto=0)")
    if not ctx.dry:
        (ws / "repos").mkdir(parents=True, exist_ok=True)
        shutil.move(str(basis["dir"] / ".git"), str(bare))
        git(["-C", str(bare), "config", "core.bare", "true"])
        git(["-C", str(bare), "config", "--unset", "core.worktree"], check=False)
        git(["-C", str(bare), "config", "gc.auto", "0"])
    return bare


def backup_clone_refs(ctx, bare, clone):
    """Récupère TOUTES les refs locales d'un clone secondaire dans le bare (filet)."""
    tag = clone["usage"]
    ctx.act(f"fetch refs locales de {clone['dir'].name}/ → refs/mig/{tag}/* (sauvegarde)")
    if ctx.dry:
        return
    src = str(clone["dir"])
    git(["-C", str(bare), "remote", "add", f"_mig_{tag}", src], check=False)
    git(["-C", str(bare), "fetch", "--quiet", f"_mig_{tag}",
         f"+refs/heads/*:refs/mig/{tag}/*"], check=False, quiet=True)
    git(["-C", str(bare), "remote", "remove", f"_mig_{tag}"], check=False)


def reconcile_branch(ctx, bare, branch, want_commit, tag):
    """Garantit heads/<branch> == want_commit (état réel du clone), sans perte."""
    if ctx.dry:
        return
    rc, cur = git(["-C", str(bare), "rev-parse", "--verify", "--quiet",
                   f"refs/heads/{branch}"], check=False, quiet=True)
    if rc != 0:
        git(["-C", str(bare), "branch", branch, want_commit])
    elif cur != want_commit:
        git(["-C", str(bare), "update-ref", f"refs/mig/_orig/{branch}", cur])
        git(["-C", str(bare), "branch", "-f", branch, want_commit])
        ctx.warn(f"branche `{branch}` divergeait : ancienne tête sauvée dans "
                 f"refs/mig/_orig/{branch}, worktree {tag} pointé sur l'état réel du clone.")


def adopt_worktree(ctx, ws, bare, code, clone):
    """Adopte le dossier de travail existant comme worktree, fichiers PRÉSERVÉS."""
    usage, branch = clone["usage"], clone["branch"]
    wt = ws / "envs" / f"{code}-{usage}"
    premig = ws / "envs" / f"{code}-{usage}.premig"
    ctx.act(f"adopte {clone['dir'].name}/ → envs/{code}-{usage} "
            f"(worktree --no-checkout + rsync ; dirty/untracked/ignorés préservés)")
    if ctx.dry:
        return wt
    (ws / "envs").mkdir(parents=True, exist_ok=True)
    # le clone secondaire garde son .git jusqu'ici (refs déjà sauvegardées) → on l'ôte
    if (clone["dir"] / ".git").exists():
        if (clone["dir"] / ".git").is_dir():
            shutil.rmtree(clone["dir"] / ".git")
        else:
            (clone["dir"] / ".git").unlink()
    shutil.move(str(clone["dir"]), str(premig))     # dossier de travail gitless, intact
    # liaison git SANS écrire de fichier (--no-checkout laisse l'index VIDE)
    git(["-C", str(bare), "worktree", "add", "--no-checkout", str(wt), branch])
    # fichiers de travail réels (tracké-dirty + untracked + IGNORÉS/local)
    run(["rsync", "-a", "--exclude=.git", f"{premig}/", f"{wt}/"])
    # peuple l'index depuis HEAD (mixed reset, working tree intact) : git reconnaît
    # alors les fichiers trackés → dirty = modifié, untracked = untracked, ignoré = ignoré.
    git(["-C", str(wt), "reset", "-q", "HEAD"])
    # Le worktree est complet à ce stade ; le `.premig` n'est plus que du scratch.
    # Son nettoyage est BEST-EFFORT (RM2031) : un échec (cache FPM d'un autre user)
    # ne doit pas interrompre migrate_group avant backfill_manifest/rewrite_gitignore.
    best_effort_rmtree(ctx, premig)
    return wt


def backfill_manifest(ctx, ws, code, basis, bare):
    """Ajoute/maj l'entrée repos: <code> dans .mmi-pm/meta.yml."""
    meta = ws / ".mmi-pm" / "meta.yml"
    ctx.act(f"backfill meta.yml › repos: += {code} (integration_branch={basis['branch']})")
    if ctx.dry:
        return
    data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {} if meta.is_file() else {}
    remotes = {}
    if not ctx.dry and bare.exists():
        _, names = git(["-C", str(bare), "remote"], check=False)
        for r in names.split():
            if r.startswith("_mig_"):
                continue
            _, url = git(["-C", str(bare), "remote", "get-url", r], check=False, quiet=True)
            if url:
                remotes[r] = url
    entry = {"name": code, "remotes": remotes or {"origin": basis["origin"]},
             "integration_branch": basis["branch"]}
    repos = data.get("repos") or []
    repos = [r for r in repos if r.get("name") != code] + [entry]
    data["repos"] = repos
    meta.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def rewrite_gitignore(ctx, ws):
    gi = ws / ".gitignore"
    if gi.is_file() and gi.read_text(encoding="utf-8") == GITIGNORE:
        ctx.skip(".gitignore déjà au format norme")
        return
    ctx.act("réécrit .gitignore (format nouveau norme)")
    if not ctx.dry:
        gi.write_text(GITIGNORE, encoding="utf-8")


def migrate_group(ctx, ws, code, clones):
    print(f"\n• code `{code}` ({len(clones)} clone(s))")
    # basis = clone sur la branche d'intégration (dev/develop) sinon le premier
    basis = next((c for c in clones if c["branch"] in ("dev", "develop")), clones[0])
    others = [c for c in clones if c is not basis]
    bare = make_bare(ctx, ws, code, basis)
    for c in others:
        backup_clone_refs(ctx, bare, c)
        reconcile_branch(ctx, bare, c["branch"], c["head"], c["usage"])
    # adoption des worktrees (basis d'abord)
    adopt_worktree(ctx, ws, bare, code, basis)
    for c in others:
        adopt_worktree(ctx, ws, bare, code, c)
    backfill_manifest(ctx, ws, code, basis, bare)


# -------------------------------------------------------------------- verify

def verify(ctx, ws, groups):
    print("\n— VERIFY —")
    ok = True
    for code in groups:
        bare = ws / "repos" / f"{code}.git"
        if not bare.exists():
            ctx.warn(f"repos/{code}.git absent après migration"); ok = False; continue
        rc, out = git(["-C", str(bare), "fsck", "--no-progress", "--no-dangling"],
                      check=False, quiet=True)
        print(f"  repos/{code}.git : fsck {'OK' if rc == 0 else 'ERREURS'}")
        if rc != 0:
            ctx.warn(f"fsck {code} a signalé des erreurs"); ok = False
        _, wl = git(["-C", str(bare), "worktree", "list"], check=False)
        for line in wl.splitlines():
            print(f"    {line}")
    leftover = list(ws.glob("envs/*.premig"))
    if leftover:
        ctx.warn(f"résidus .premig non nettoyés : {[p.name for p in leftover]}"); ok = False
    return ok


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        prog="pm-env-migrate",
        description="Migre un workspace pré-norme vers le layout RM1993 (RM2028).")
    ap.add_argument("workspace", nargs="?", default=None,
                    help="workspace (défaut : découverte depuis cwd via .mmi-pm)")
    ap.add_argument("--dry-run", action="store_true", help="plan + ops prévues, aucune mutation")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="saute le snapshot ZFS (réversibilité à ta charge)")
    ap.add_argument("--force", action="store_true",
                    help="passe outre repos/ ou envs/ déjà présents")
    ap.add_argument("-y", "--yes", action="store_true", help="non-interactif (pas de confirmation)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    start = Path(args.workspace).resolve() if args.workspace else Path.cwd()
    if args.workspace and not start.is_dir():
        die(f"{start} n'est pas un dossier")
    ws = find_workspace(start)
    root, groups = discover(ws)

    print("=== PLAN ===")
    print_plan(ws, root, groups)
    if not groups:
        die("rien à migrer.")
    guard(ws, groups, args.force)

    ctx = Ctx(args.dry_run, args.verbose)
    if args.dry_run:
        print("\n=== DRY-RUN (aucune mutation) ===")
        snapshot(ctx, ws, args.no_snapshot)
        for code, clones in groups.items():
            migrate_group(ctx, ws, code, clones)
        rewrite_gitignore(ctx, ws)
        print(f"\n[dry-run] {ctx.changed} action(s) prévues.")
        return

    if not args.yes:
        ans = input("\nConfirmer la migration (in-place, snapshot pris) ? [y/N] ")
        if ans.strip().lower() != "y":
            die("annulé.")

    snapshot(ctx, ws, args.no_snapshot)
    for code, clones in groups.items():
        migrate_group(ctx, ws, code, clones)
    rewrite_gitignore(ctx, ws)
    ok = verify(ctx, ws, groups)
    print(f"\n{'✓' if ok else '⚠'} migration : {ctx.changed} action(s), "
          f"{len(ctx.warnings)} avertissement(s).")
    if not ok:
        sys.stderr.write("pm-env-migrate: VERIFY a échoué — envisage un rollback du snapshot.\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
