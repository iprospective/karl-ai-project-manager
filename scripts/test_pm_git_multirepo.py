#!/usr/bin/env python3
"""Tests RM3237 — `pm_git.autocommit` committe dans CHAQUE dépôt concerné.

Un appel peut porter sur plusieurs dépôts : `pm-task-link` entre deux tickets de
projets différents écrit le journal de chacun, donc deux dépôts de DONNÉES. La
fonction ne calculait qu'une racine (celle de `paths[0]`) et ignorait le reste —
les fichiers de l'autre dépôt restaient non commités jusqu'au rattrapage RM3013,
soit plus d'une heure, et seulement si un autre outil repassait par là.

Sans réseau : chaque remote est un dépôt bare local.
Lancer : python3 scripts/test_pm_git_multirepo.py
"""
import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
JOURNAL_DIR = tempfile.mkdtemp(prefix="pm-git-multirepo-journal-")
os.environ["KARL_JOURNAL_DIR"] = JOURNAL_DIR
os.environ["KARL_JOURNAL_STDERR"] = "0"
import pm_git  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True, text=True).stdout


def build(tmp, nom):
    """Un clone `nom` d'un bare local, marqué dépôt de DONNÉES (dossier .mmi-pm réel)."""
    bare = tmp / f"{nom}-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp / nom
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True)
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    git(work, "checkout", "-q", "-b", "main")
    (work / ".mmi-pm" / "tasks").mkdir(parents=True)
    (work / ".mmi-pm" / "tasks" / "RM1_a.log.md").write_text("journal\n")
    (work / "README.md").write_text("seed\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "seed")
    git(work, "push", "-q", "origin", "main")
    return bare, work


def run(paths, msg, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        sha = pm_git.autocommit(paths, msg, **kw)
    return sha, out.getvalue()


def sujets(cwd, n=3):
    return git(cwd, "log", f"-{n}", "--format=%s").strip().splitlines()


def propre(cwd, chemin):
    """Le chemin est-il commité (rien à signaler dans git status) ?"""
    return git(cwd, "status", "--porcelain", "--", chemin).strip() == ""


with tempfile.TemporaryDirectory() as td:
    tmp = pathlib.Path(td)
    bare_a, repo_a = build(tmp, "projet-a")
    bare_b, repo_b = build(tmp, "projet-b")
    a = repo_a / ".mmi-pm" / "tasks" / "RM1_a.log.md"
    b = repo_b / ".mmi-pm" / "tasks" / "RM1_a.log.md"

    # ── 1. le cas du bug : un lien écrit le journal des DEUX tickets ──
    a.write_text("journal + lien vers RM2\n")
    b.write_text("journal + lien vers RM1\n")
    sha, sortie = run([a, b], "pm(link): RM1 relates RM2")

    check("dépôt de paths[0] : commité", propre(repo_a, str(a)))
    check("AUTRE dépôt : commité aussi (le bug)", propre(repo_b, str(b)),
          "git status : " + git(repo_b, "status", "--porcelain"))
    check("message identique dans les deux dépôts",
          sujets(repo_a)[0] == "pm(link): RM1 relates RM2"
          and sujets(repo_b)[0] == "pm(link): RM1 relates RM2",
          f"{sujets(repo_a)[:1]} / {sujets(repo_b)[:1]}")
    check("plus d'avertissement « hors du repo »", "hors du repo" not in sortie, sortie.strip()[:200])
    check("sha rendu = celui du dépôt de paths[0]",
          sha == git(repo_a, "rev-parse", "--short", "HEAD").strip(), f"rendu={sha}")

    # ── 2. les deux dépôts sont poussés ──
    check("dépôt A poussé", git(repo_a, "rev-parse", "HEAD").strip()
          == git(bare_a, "rev-parse", "main").strip())
    check("dépôt B poussé", git(repo_b, "rev-parse", "HEAD").strip()
          == git(bare_b, "rev-parse", "main").strip())

    # ── 3. un seul dépôt : comportement inchangé ──
    a.write_text("journal seul\n")
    sha1, _ = run([a], "pm(tick): RM1")
    check("un seul dépôt : commit et sha rendus", sha1 is not None and propre(repo_a, str(a)))
    check("un seul dépôt : le dépôt B n'a pas bougé",
          sujets(repo_b)[0] == "pm(link): RM1 relates RM2", sujets(repo_b)[:1])

    # ── 4. rien à committer dans l'un des deux ──
    b.write_text("journal B modifié seul\n")
    sha2, sortie2 = run([a, b], "pm(comment): RM2")
    check("contenu inchangé dans A, modifié dans B : B est commité", propre(repo_b, str(b)))
    check("sha rendu None quand A n'avait rien à committer", sha2 is None, f"rendu={sha2}")

    # ── 5. un chemin hors de tout dépôt git ne fait pas échouer le reste ──
    hors = tmp / "hors-depot.md"
    hors.write_text("fichier isolé\n")
    a.write_text("journal encore\n")
    sha3, sortie3 = run([a, hors], "pm(tick): RM1 bis")
    check("chemin hors dépôt : signalé", "n'est pas dans un repo git" in sortie3
          or "hors du repo" in sortie3, sortie3.strip()[:200])
    check("chemin hors dépôt : le dépôt valide est quand même commité",
          sha3 is not None and propre(repo_a, str(a)), f"rendu={sha3}")

print()
if fails:
    print(f"{len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("tous les tests passent")
