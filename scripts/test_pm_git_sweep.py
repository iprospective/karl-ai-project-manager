#!/usr/bin/env python3
"""Tests RM3013 — rattrapage de ce qui traîne, porté par `pm_git.autocommit`.

Pas de timer, pas de process dédié (décision Mathieu 2026-09-06) : quand un script
auto-committe ses chemins sur un dépôt de DONNÉES, il embarque aussi, dans un
commit `pm(rattrapage): …` séparé, les fichiers non commités dont la dernière
modification remonte à plus de `git.sweep_after_min` (60 min par défaut).
Sans réseau : remote = dépôt bare local. Lancer : python3 scripts/test_pm_git_sweep.py
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
JOURNAL_DIR = tempfile.mkdtemp(prefix="pm-git-sweep-journal-")
os.environ["KARL_JOURNAL_DIR"] = JOURNAL_DIR          # le journal du test n'atterrit pas dans logs/
os.environ["KARL_JOURNAL_STDERR"] = "0"
import pm_git  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True, text=True).stdout


def build(tmp, core=True):
    """Un clone `work` d'un bare local, marqué dépôt de DONNÉES (dossier réel .mmi-pm) ou de CODE."""
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True)
    git(work, "config", "user.email", "t@t"); git(work, "config", "user.name", "t")
    git(work, "checkout", "-q", "-b", "main")
    (work / ".mmi-pm" / "tasks").mkdir(parents=True)
    if core:
        (work / ".mmi-pm" / "tasks" / "RM1_a.md").write_text("fiche\n")
        (work / ".mmi-pm" / "tasks" / "RM1_a.log.md").write_text("journal\n")
        (work / ".mmi-pm" / "tasks" / "RM2_b.md").write_text("fiche 2\n")
    else:
        subprocess.run(["rm", "-rf", str(work / ".mmi-pm")], check=True)
        (work / "docs").mkdir()
        (work / "docs" / "a.md").write_text("doc\n")
    (work / "README.md").write_text("seed\n")
    git(work, "add", "-A"); git(work, "commit", "-qm", "seed")
    git(work, "push", "-q", "origin", "main")
    return bare, work


def age(path, hours):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def run(paths, msg, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        sha = pm_git.autocommit(paths, msg, **kw)
    return sha, out.getvalue()


def log_subjects(cwd, n=5):
    return git(cwd, "log", f"-{n}", "--format=%s").strip().splitlines()


def journal():
    p = pathlib.Path(JOURNAL_DIR) / "karl-agent.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []


with tempfile.TemporaryDirectory() as td:
    tmp = pathlib.Path(td)
    bare, work = build(tmp)
    T = work / ".mmi-pm" / "tasks"

    # ── 1. un fichier vieux de 2 h traîne, un fichier frais aussi ; un script committe SA fiche ──
    (T / "RM2_b.md").write_text("fiche 2 modifiée à la main\n"); age(T / "RM2_b.md", 2)
    (T / "RM3_c.md").write_text("nouvelle fiche non suivie, vieille\n"); age(T / "RM3_c.md", 3)
    (T / "RM1_a.log.md").write_text("journal modifié il y a 10 min\n"); age(T / "RM1_a.log.md", 10 / 60)
    (T / "RM9.md.tmp").write_text("temporaire vieux\n"); age(T / "RM9.md.tmp", 5)
    (T / "RM1_a.md").write_text("fiche mise à jour par pm-task-tick\n")
    sha, out = run([T / "RM1_a.md"], "pm(tick): RM1 métriques temps/tokens")
    subjects = log_subjects(work)
    check("le commit des chemins nommés est fait et rendu", sha and subjects[-1] == "seed" and "pm(tick): RM1 métriques temps/tokens" in subjects, str(subjects))
    swept = [s for s in subjects if s.startswith("pm(rattrapage):")]
    check("un commit de rattrapage séparé est parti", len(swept) == 1, str(subjects))
    check("il compte 2 fichiers, cite le seuil et l'outil déclencheur",
          swept and "2 fichier(s)" in swept[0] and "> 60 min" in swept[0] and "déclenché par tick" in swept[0], str(swept))
    check("le rattrapage est le dernier commit (après celui des chemins nommés)", subjects[0].startswith("pm(rattrapage):"), str(subjects))
    files_swept = git(work, "show", "--name-only", "--format=", "HEAD").split()
    check("il embarque le modifié vieux et le non-suivi vieux", sorted(files_swept) == [".mmi-pm/tasks/RM2_b.md", ".mmi-pm/tasks/RM3_c.md"], str(files_swept))
    st = git(work, "status", "--porcelain", "--untracked-files=all").splitlines()
    check("le fichier frais (10 min) et le temporaire sont laissés tranquilles",
          sorted(l[3:] for l in st) == [".mmi-pm/tasks/RM1_a.log.md", ".mmi-pm/tasks/RM9.md.tmp"], str(st))
    check("les deux commits sont poussés", git(bare, "rev-parse", "main").strip() == git(work, "rev-parse", "HEAD").strip())
    check("succès silencieux (RM2440)", out.strip() == "", out)
    j = [r for r in journal() if r.get("cat") == "pm" and "rattrapage" in r.get("msg", "")]
    check("le rattrapage est journalisé (catégorie pm, niveau info, fichiers cités)",
          len(j) == 1 and j[0]["level"] == "info" and j[0].get("trigger") == "tick" and ".mmi-pm/tasks/RM2_b.md" in j[0].get("files", []), str(j))

    # ── 2. rien à committer pour nos chemins : le rattrapage tourne quand même ──
    age(T / "RM1_a.log.md", 2)
    sha, out = run([T / "RM1_a.md"], "pm(status): RM1 -> en_cours")
    subjects = log_subjects(work, 2)
    check("sans changement sur nos chemins le sha rendu est None", sha is None)
    check("mais le journal vieilli est rattrapé et poussé", subjects[0].startswith("pm(rattrapage): 1 fichier(s)") and "déclenché par status" in subjects[0]
          and git(bare, "rev-parse", "main").strip() == git(work, "rev-parse", "HEAD").strip(), str(subjects))

    # ── 3. suppression vieille : datée par le dossier parent ──
    (T / "RM3_c.md").unlink(); age(T, 2)
    sha, out = run([T / "RM1_a.md"], "pm(tick): RM1")
    check("une suppression laissée depuis > 1 h est rattrapée", ".mmi-pm/tasks/RM3_c.md" in git(work, "show", "--name-only", "--format=", "HEAD")
          and log_subjects(work, 1)[0].startswith("pm(rattrapage)"), log_subjects(work, 1)[0])
    (T / "RM4_d.md").write_text("fraîche\n"); (T / "RM1_a.md").write_text("x\n")
    git(work, "rm", "-q", "--cached", "README.md"); os.remove(work / "README.md")  # suppression toute fraîche (mtime du dossier = maintenant)
    sha, out = run([T / "RM1_a.md"], "pm(tick): RM1")
    check("une suppression fraîche ne l'est pas", not log_subjects(work, 1)[0].startswith("pm(rattrapage)"), log_subjects(work, 1)[0])
    git(work, "checkout", "-q", "HEAD", "--", "README.md"); (T / "RM4_d.md").unlink()

    # ── 4. débrayage par config : git.sweep = false ──
    (T / "RM5_e.md").write_text("vieille\n"); age(T / "RM5_e.md", 4); (T / "RM1_a.md").write_text("y\n")
    orig = pm_git.load_git_config
    pm_git.load_git_config = lambda: dict(orig(), sweep=False)
    try:
        sha, out = run([T / "RM1_a.md"], "pm(tick): RM1")
    finally:
        pm_git.load_git_config = orig
    check("git.sweep=false : commit nominal seul, rien de rattrapé", sha and not any(s.startswith("pm(rattrapage)") for s in log_subjects(work, 1))
          and ".mmi-pm/tasks/RM5_e.md" in [l[3:] for l in git(work, "status", "--porcelain", "-uall").splitlines()])

    # ── 5. seuil configurable : sweep_after_min = 1 rattrape un fichier de 5 min ──
    age(T / "RM5_e.md", 5 / 60); (T / "RM1_a.md").write_text("z\n")
    pm_git.load_git_config = lambda: dict(orig(), sweep_after_min=1)
    try:
        sha, out = run([T / "RM1_a.md"], "pm(tick): RM1")
    finally:
        pm_git.load_git_config = orig
    check("sweep_after_min=1 : le fichier de 5 min est rattrapé, seuil cité", log_subjects(work, 1)[0].startswith("pm(rattrapage): 1 fichier(s)") and "> 1 min" in log_subjects(work, 1)[0], log_subjects(work, 1)[0])

    # ── 6. un dépôt de CODE n'est jamais balayé ──
    tmp2 = tmp / "code"; tmp2.mkdir()
    _, code = build(tmp2, core=False)
    (code / "docs" / "old.md").write_text("vieux non suivi\n"); age(code / "docs" / "old.md", 9)
    (code / "docs" / "a.md").write_text("doc modifiée\n")
    sha, out = run([code / "docs" / "a.md"], "pm(test): maj")
    check("dépôt de CODE : commit nominal, aucun rattrapage", sha and not any(s.startswith("pm(rattrapage)") for s in log_subjects(code, 2))
          and "docs/old.md" in git(code, "status", "--porcelain", "-uall"), str(log_subjects(code, 2)))

    # ── 7. les échecs d'auto-commit sont journalisés en warn ──
    (T / "RM1_a.md").write_text("w\n")
    git(work, "checkout", "-q", "-b", "feature")
    pm_git.load_git_config = lambda: dict(orig(), sweep=False)
    try:
        sha, out = run([T / "RM1_a.md"], "pm(tick): RM1", push=True)  # push d'une branche sans upstream → refusé
    finally:
        pm_git.load_git_config = orig
    w = [r for r in journal() if r.get("cat") == "pm" and r.get("level") == "warn"]
    check("un push refusé parle sur la console ET dans le journal (warn, sans doublon stderr)", "auto-commit" in out and w and "auto-commit" in w[-1]["msg"] and out.count("auto-commit") == 1, out + str(w[-1:]))

shutil.rmtree(JOURNAL_DIR, ignore_errors=True)
print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("Le rattrapage RM3013 se comporte comme prévu.")
