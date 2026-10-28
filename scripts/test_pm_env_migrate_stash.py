#!/usr/bin/env python3
"""Tests RM3566 — `pm-env-migrate` ne doit plus détruire les stashes.

Incident du 2026-10-27 (workspace `/zfs/workspaces/dolibarr`) : le plan affichait
les stashes de chaque clone, mais `backup_clone_refs()` ne sauvegardait que
`refs/heads/*`, puis `adopt_worktree()` supprimait le `.git` du clone. 160 stashes
ont été perdus sur 8 clones.

Ce qui est protégé ici :
  1. les stashes de TOUS les clones (y compris le clone `basis`, dont le `.git`
     devient le bare) sont importés sous `refs/mig/<usage>/stash/<n>` ;
  2. le contenu du stash reste lisible (commit + arbre) dans le bare ;
  3. la migration est rejouable : `make_bare()` réutilise un bare existant au lieu
     de re-mover un `.git` dedans.

Lancement : python3 scripts/test_pm_env_migrate_stash.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "pm-env-migrate.py"

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} : {got!r} != {want!r}")
        FAILURES.append(label)


def sh(args, cwd=None, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, args))} -> {r.returncode}\n{r.stderr}")
    return r


def make_workspace(root: Path) -> Path:
    origin = root / "origin.git"
    sh(["git", "init", "-q", "--bare", str(origin)])
    src = root / "src"
    sh(["git", "init", "-q", str(src)])
    sh(["git", "-C", str(src), "config", "user.email", "t@t"])
    sh(["git", "-C", str(src), "config", "user.name", "t"])
    for i in (1, 2, 3):
        (src / f"f{i}").write_text(f"{i}\n")
        sh(["git", "-C", str(src), "add", f"f{i}"])
        sh(["git", "-C", str(src), "commit", "-qm", f"c{i}"])
    sh(["git", "-C", str(src), "remote", "add", "origin", str(origin)])
    sh(["git", "-C", str(src), "push", "-q", "origin", "master"])

    ws = root / "ws"
    (ws / ".mmi-pm").mkdir(parents=True)
    (ws / ".mmi-pm" / "meta.yml").write_text(
        "schema_version: 1.7.1\nslug: test\nname: Test\nclient: test\n"
        "status: active\naspects: []\n", encoding="utf-8")
    for name in ("dev", "test"):
        clone = ws / name
        sh(["git", "clone", "-q", str(origin), str(clone)])
        sh(["git", "-C", str(clone), "config", "user.email", "t@t"])
        sh(["git", "-C", str(clone), "config", "user.name", "t"])
        sh(["git", "-C", str(clone), "checkout", "-q", "-b", name])
        for i in (1, 2):
            (clone / "f1").write_text(f"{name}-{i}\n")
            sh(["git", "-C", str(clone), "stash", "-q"])
    return ws


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="envmig-stash-") as tmp:
        ws = make_workspace(Path(tmp))
        r = sh([sys.executable, str(SCRIPT), str(ws),
                "--no-snapshot", "--force", "-y"], check=False)
        check("migration rc", r.returncode, 0)

        bare = ws / "repos" / "origin.git"
        for usage in ("dev", "test"):
            refs = sh(["git", "-C", str(bare), "for-each-ref",
                       "--format=%(objectname)",
                       f"refs/mig/{usage}/stash"]).stdout.split()
            check(f"{usage} : 2 stashes sauvegardés", len(refs), 2)
            for sha in refs:
                cat = sh(["git", "-C", str(bare), "cat-file", "-t", sha], check=False)
                check(f"{usage} : {sha[:8]} lisible", cat.returncode, 0)

        # le contenu d'un stash est intact (arbre présent, pas juste le commit)
        sha = sh(["git", "-C", str(bare), "rev-parse",
                  "refs/mig/dev/stash/0"]).stdout.strip()
        files = sh(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", sha]).stdout
        check("arbre du stash présent (f1)", "f1" in files, True)

        # rejouable : bare existant réutilisé, pas de re-move destructeur
        sh(["git", "clone", "-q", str(Path(tmp) / "origin.git"), str(ws / "test2")])
        sh(["git", "-C", str(ws / "test2"), "checkout", "-q", "-b", "test2"])
        r2 = sh([sys.executable, str(SCRIPT), str(ws),
                 "--no-snapshot", "--force", "-y"], check=False)
        check("reprise rc", r2.returncode, 0)
        heads = sh(["git", "-C", str(bare), "rev-parse", "--verify",
                    "refs/mig/dev/stash/0"]).stdout.strip()
        check("stash dev toujours présent après reprise", heads, sha)

    print()
    if FAILURES:
        print(f"ÉCHECS : {FAILURES}")
        return 1
    print("tous les contrôles sont passés")
    return 0


if __name__ == "__main__":
    sys.exit(main())
