#!/usr/bin/env python3
"""Tests du rattrapage non-fast-forward sur un dépôt core (RM2440).

Monte de vrais dépôts git (bare + deux clones) pour reproduire le scénario réel :
une autre machine a poussé pendant qu'on travaillait, notre push est rejeté en
non-fast-forward, et pm_git doit rattraper au lieu de différer.

Cas couverts :
  1. core + non_ff sans conflit          → rebase + push, rien n'est perdu ;
  2. core + non_ff AVEC conflit          → rebase abandonné, arbre propre,
                                           commit local conservé, warning ;
  3. dépôt de CODE + non_ff              → pas de rebase (invariant conservé) ;
  4. succès nominal                      → aucune sortie (verbosité RM2440).

Lancement : python3 scripts/test_pm_git_core_rebase.py
"""
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git  # noqa: E402

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} : attendu {want!r}, obtenu {got!r}")
        FAILURES.append(label)


def git(repo, *a, check_rc=True):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    if check_rc and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)} : {r.stderr}")
    return r


def build(tmp, core=True):
    """(bare, ours, theirs) — deux clones d'un même dépôt, marqué core ou non."""
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)

    seed = tmp / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True)
    git(seed, "config", "user.email", "t@t"); git(seed, "config", "user.name", "t")
    if core:
        (seed / ".mmi-pm").mkdir()
        (seed / ".mmi-pm" / ".keep").write_text("")
    (seed / "shared.md").write_text("ligne commune\n")
    git(seed, "add", "-A"); git(seed, "commit", "-qm", "seed")
    git(seed, "push", "-q", "origin", "HEAD:refs/heads/main")

    ours, theirs = tmp / "ours", tmp / "theirs"
    for c in (ours, theirs):
        subprocess.run(["git", "clone", "-q", "-b", "main", str(bare), str(c)], check=True)
        git(c, "config", "user.email", "t@t"); git(c, "config", "user.name", "t")
    return bare, ours, theirs


def advance_remote(theirs, content="modif distante\n", fname="shared.md"):
    (theirs / fname).write_text(content)
    git(theirs, "add", "-A"); git(theirs, "commit", "-qm", "commit distant")
    git(theirs, "push", "-q", "origin", "main")


def run_autocommit(paths, msg):
    """Capture stdout+stderr : la verbosité fait partie du contrat testé."""
    buf_out, buf_err = StringIO(), StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        sha = pm_git.autocommit(paths, msg)
    return sha, buf_out.getvalue() + buf_err.getvalue()


def test_core_non_ff_sans_conflit():
    print("Core + non-fast-forward, sans conflit :")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _, ours, theirs = build(tmp, core=True)
        advance_remote(theirs)                      # le remote avance
        (ours / "mon-ticket.md").write_text("RM9999\n")   # notre écriture, autre fichier

        sha, output = run_autocommit([ours / "mon-ticket.md"], "pm(test): RM9999")
        check("commit créé", bool(sha), True)
        check("rien à rattraper au tour suivant (ahead=0)",
              git(ours, "rev-list", "--count", "origin/main..HEAD").stdout.strip(), "0")
        check("le commit distant est bien présent localement",
              (ours / "shared.md").read_text(), "modif distante\n")
        check("notre fichier a survécu au rebase",
              (ours / "mon-ticket.md").read_text(), "RM9999\n")
        check("aucun warning", "⚠" in output, False)


def test_core_non_ff_avec_conflit():
    print("Core + non-fast-forward, AVEC conflit :")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _, ours, theirs = build(tmp, core=True)
        advance_remote(theirs, "version distante\n")
        (ours / "shared.md").write_text("version locale\n")   # même fichier → conflit

        sha, output = run_autocommit([ours / "shared.md"], "pm(test): conflit")
        check("commit local conservé", bool(sha), True)
        check("arbre PROPRE (pas de rebase en cours)",
              (Path(ours) / ".git" / "rebase-merge").exists()
              or (Path(ours) / ".git" / "rebase-apply").exists(), False)
        check("notre version locale est intacte",
              (ours / "shared.md").read_text(), "version locale\n")
        check("un warning est émis", "⚠" in output, True)


def test_code_repo_pas_de_rebase():
    print("Dépôt de CODE + non-fast-forward (invariant conservé) :")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _, ours, theirs = build(tmp, core=False)
        advance_remote(theirs)
        (ours / "note.md").write_text("x\n")

        sha, output = run_autocommit([ours / "note.md"], "pm(test): code")
        check("commit local conservé", bool(sha), True)
        # pm_git n'a pas fetché (c'est le point : pas de rebase sur un dépôt de
        # code) — la ref locale origin/main est donc périmée. Il faut fetcher
        # nous-mêmes avant de mesurer, sinon on mesure une ref obsolète.
        git(ours, "fetch", "-q", "origin", "main")
        behind = git(ours, "rev-list", "--count", "HEAD..FETCH_HEAD").stdout.strip()
        ahead = git(ours, "rev-list", "--count", "FETCH_HEAD..HEAD").stdout.strip()
        check("PAS de rebase : la divergence est conservée",
              (behind != "0", ahead != "0"), (True, True))
        check("warning « push différé »", "différé" in output, True)


def test_succes_silencieux():
    print("Succès nominal (verbosité RM2440) :")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _, ours, _ = build(tmp, core=True)
        (ours / "ticket.md").write_text("ok\n")

        sha, output = run_autocommit([ours / "ticket.md"], "pm(test): nominal")
        check("commit + push réussis", bool(sha), True)
        check("sortie vide", output.strip(), "")


if __name__ == "__main__":
    test_core_non_ff_sans_conflit()
    test_core_non_ff_avec_conflit()
    test_code_repo_pas_de_rebase()
    test_succes_silencieux()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nTous les tests passent.")
