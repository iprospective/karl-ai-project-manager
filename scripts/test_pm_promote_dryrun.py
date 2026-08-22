#!/usr/bin/env python3
"""Tests RM2790 — `pm-promote --dry-run` ne doit RIEN écrire.

Le flush des commits locaux (étape 1) s'exécutait avant que `--dry-run` ne soit
testé : un dry-run lancé pour *voir* le lot poussait le travail local sur la
branche d'intégration, court-circuitant la revue par MR (tripwire NORMS #3).

Sans réseau : la forge est remplacée par un double, et `--dry-run` sort de
`main()` avant tout appel d'API. L'assertion utile porte sur l'effet réel —
l'état de la ref distante après exécution.

Lancer : python3 scripts/test_pm_promote_dryrun.py
"""
import contextlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_forge

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def load_promote():
    spec = importlib.util.spec_from_file_location("pm_promote", HERE / "pm-promote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Caps:
    pull_request_api = True


class _Project:
    path = "test/repo"
    id = 1


class _Forge:
    capabilities = _Caps()

    def token(self, _role):
        return "fake-token"

    def resolve_project(self, _token):
        return _Project()


def seed(tmp):
    """Bare + clone : main et dev alignés, puis un commit local non poussé."""
    bare = tmp / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True)
    git("config", "user.email", "t@t", cwd=work)
    git("config", "user.name", "t", cwd=work)
    (work / "a.txt").write_text("1\n")
    git("add", "a.txt", cwd=work)
    git("commit", "-qm", "init", cwd=work)
    git("push", "-q", "origin", "main:main", cwd=work)
    git("push", "-q", "origin", "main:dev", cwd=work)
    # commit local NON poussé, comme une branche de ticket en cours
    (work / "b.txt").write_text("2\n")
    git("add", "b.txt", cwd=work)
    git("commit", "-qm", "travail local", cwd=work)
    git("fetch", "-q", "origin", cwd=work)
    return work


def run_promote(work, *argv):
    mod = load_promote()
    real = pm_forge.get_forge
    pm_forge.get_forge = lambda _repo: _Forge()
    old_argv = sys.argv
    sys.argv = ["pm-promote.py", "--repo", str(work), *argv]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                mod.main()
            except SystemExit:
                pass
    finally:
        sys.argv = old_argv
        pm_forge.get_forge = real
    return buf.getvalue()


def main():
    with tempfile.TemporaryDirectory() as td:
        work = seed(pathlib.Path(td))
        before = git("rev-parse", "origin/dev", cwd=work)
        local = git("rev-parse", "HEAD", cwd=work)

        out = run_promote(work, "--source", "dev", "--target", "main", "--dry-run")

        git("fetch", "-q", "origin", cwd=work)
        after = git("rev-parse", "origin/dev", cwd=work)

        check("--dry-run n'écrit pas sur la branche d'intégration",
              before == after, f"origin/dev {before[:8]} → {after[:8]}")
        check("le commit local n'a pas fui sur le remote",
              after != local, "HEAD local retrouvé sur origin/dev")
        check("la simulation du flush est annoncée",
              "dry-run" in out and "seraient poussés" in out, out.strip())
        check("le lot annoncé inclut le commit qui serait flushé",
              "1 commit(s) à promouvoir" in out, out.strip())

    print()
    if fails:
        print(f"{len(fails)} test(s) en échec : {', '.join(fails)}")
        return 1
    print("tous les tests passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
