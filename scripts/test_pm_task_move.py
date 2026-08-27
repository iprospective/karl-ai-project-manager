#!/usr/bin/env python3
"""Test hors ligne de pm-task-move (RM2866).

Couvre ce qui casse en silence si on se trompe : la résolution de la cible
(tripwire #14), les refus (même projet, branche de code, collision), le
`--dry-run` qui ne doit rien toucher, et surtout le **groupement des commits par
dépôt** — source et cible ne vivent pas forcément dans le même repo de données,
et `pm_git.autocommit` ne savait pas committer une suppression avant ce ticket.

Aucun appel réseau : toutes les invocations passent `--no-redmine`.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from test_support import subprocess_env                          # noqa: E402

MOVE = SCRIPTS / "pm-task-move.py"
FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} {detail}")
        FAILURES.append(label)


def run(env, *args):
    return subprocess.run([sys.executable, str(MOVE), *args], env=env,
                          capture_output=True, text=True, cwd=str(SCRIPTS))


def make_project(root, entity, project, redmine_id):
    d = root / "clients" / entity / "projects" / project
    (d / "tasks").mkdir(parents=True, exist_ok=True)
    (d / "project").mkdir(parents=True, exist_ok=True)
    (d / "meta.yml").write_text(
        f"schema_version: 1.7.1\nslug: {project}\nclient: {entity}\n"
        f"redmine:\n  project_id: {redmine_id}\n", encoding="utf-8")
    return d


def make_task(tasks_dir, rm_id, slug="tache-de-test", branch=None, reporting=True):
    git_block = f"git:\n  repo: null\n  branch: {branch}\n" if branch else ""
    md = tasks_dir / f"RM{rm_id}_{slug}.md"
    md.write_text(f"---\nschema_version: 1.11.0\nredmine_id: {rm_id}\n"
                  f"title: 'Tâche de test'\ntype: feature\nstatus: nouveau\n"
                  f"{git_block}created: '2026-08-27'\nupdated: 2026-08-27T10:00\n---\n\n"
                  f"## Contexte\n\nRien.\n", encoding="utf-8")
    (tasks_dir / f"RM{rm_id}_{slug}.log.md").write_text(
        f"# Journal RM{rm_id}\n", encoding="utf-8")
    if reporting:
        (tasks_dir / f"RM{rm_id}_{slug}.reporting.yml").write_text(
            "history: []\n", encoding="utf-8")
    return md


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def git_init(repo):
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    # marqueur de dépôt de DONNÉES PM (pm_git.is_core_repo) — dossier RÉEL
    (repo / ".mmi-pm").mkdir(exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")


def main():
    env = subprocess_env()
    root = Path(env["PM_CORE_DIR"]) / "projects"

    print("· résolution de la cible et refus")
    src = make_project(root, "alpha", "one", "alpha-one")
    dst = make_project(root, "beta", "two", "beta-two")
    make_project(root, "gamma", "shared", "gamma-shared")
    make_project(root, "delta", "shared", "delta-shared")
    make_task(src / "tasks", 9001)

    r = run(env, "9001", "--to", "shared", "--no-redmine")
    check("slug nu ambigu refusé (tripwire #14)",
          r.returncode != 0 and "ambigu" in (r.stdout + r.stderr), r.stderr[:200])

    r = run(env, "9001", "--to", "alpha/one", "--no-redmine")
    check("projet cible == projet source refusé", r.returncode != 0)

    r = run(env, "9404", "--to", "beta/two", "--no-redmine")
    check("tâche sans fiche PM refusée", r.returncode != 0)

    r = run(env, "9001", "--to", "beta/two", "--no-redmine", "--dry-run")
    check("--dry-run n'écrit rien",
          r.returncode == 0
          and (src / "tasks" / "RM9001_tache-de-test.md").exists()
          and not (dst / "tasks" / "RM9001_tache-de-test.md").exists(), r.stderr[:200])

    print("· déplacement nominal (sans git)")
    r = run(env, "9001", "--to", "beta/two", "--no-redmine", "--no-commit")
    check("sortie 0", r.returncode == 0, r.stderr[:300])
    for suffix in (".md", ".log.md", ".reporting.yml"):
        name = f"RM9001_tache-de-test{suffix}"
        check(f"{suffix} déplacé",
              (dst / "tasks" / name).exists() and not (src / "tasks" / name).exists())
    log = (dst / "tasks" / "RM9001_tache-de-test.log.md").read_text(encoding="utf-8")
    check("entrée de journal ajoutée",
          "alpha/one" in log and "beta/two" in log and "Déplacement" in log)

    print("· garde-fous")
    make_task(src / "tasks", 9002, branch="9002-truc")
    r = run(env, "9002", "--to", "beta/two", "--no-redmine", "--no-commit")
    check("branche de code → refus", r.returncode != 0 and "branche" in (r.stdout + r.stderr))
    r = run(env, "9002", "--to", "beta/two", "--no-redmine", "--no-commit", "--force")
    check("--force lève le refus", r.returncode == 0, r.stderr[:200])

    make_task(src / "tasks", 9003)
    make_task(dst / "tasks", 9003)
    r = run(env, "9003", "--to", "beta/two", "--no-redmine", "--no-commit")
    check("collision de nom à la cible → refus",
          r.returncode != 0 and "déjà" in (r.stdout + r.stderr))

    print("· commits — DEUX dépôts distincts")
    two = Path(tempfile.mkdtemp(prefix="pm-move-git-"))
    r2 = two / "projects"
    src2 = make_project(r2, "alpha", "one", "alpha-one")
    dst2 = make_project(r2, "beta", "two", "beta-two")
    repo_a, repo_b = r2 / "clients" / "alpha", r2 / "clients" / "beta"
    git_init(repo_a)
    git_init(repo_b)
    make_task(src2 / "tasks", 9101)
    git(repo_a, "add", "-A")
    git(repo_a, "commit", "-q", "-m", "tâche 9101")

    env2 = subprocess_env()
    env2["PROJECTS_PATH"] = str(r2)
    (Path(env2["PM_CORE_DIR"]) / ".env").write_text(
        f"PROJECTS_PATH={r2}\n", encoding="utf-8")
    r = run(env2, "9101", "--to", "beta/two", "--no-redmine")
    check("sortie 0 (deux repos)", r.returncode == 0, (r.stdout + r.stderr)[:400])
    check("fichiers déplacés (deux repos)",
          (dst2 / "tasks" / "RM9101_tache-de-test.md").exists()
          and not (src2 / "tasks" / "RM9101_tache-de-test.md").exists())
    check("commit de SUPPRESSION côté source",
          "pm(move)" in git(repo_a, "log", "-1", "--format=%s").stdout
          and not git(repo_a, "status", "--porcelain").stdout.strip(),
          git(repo_a, "status", "--porcelain").stdout[:200])
    check("commit d'AJOUT côté cible",
          "pm(move)" in git(repo_b, "log", "-1", "--format=%s").stdout
          and not git(repo_b, "status", "--porcelain").stdout.strip(),
          git(repo_b, "status", "--porcelain").stdout[:200])

    print("· commits — UN SEUL dépôt (rename)")
    one = Path(tempfile.mkdtemp(prefix="pm-move-git1-"))
    r3 = one / "projects"
    src3 = make_project(r3, "alpha", "one", "alpha-one")
    dst3 = make_project(r3, "alpha", "two", "alpha-two")
    git_init(one)
    make_task(src3 / "tasks", 9201)
    git(one, "add", "-A")
    git(one, "commit", "-q", "-m", "tâche 9201")

    env3 = subprocess_env()
    (Path(env3["PM_CORE_DIR"]) / ".env").write_text(
        f"PROJECTS_PATH={r3}\n", encoding="utf-8")
    r = run(env3, "9201", "--to", "alpha/two", "--no-redmine")
    check("sortie 0 (un repo)", r.returncode == 0, (r.stdout + r.stderr)[:400])
    check("un seul commit couvre le rename",
          "pm(move)" in git(one, "log", "-1", "--format=%s").stdout
          and not git(one, "status", "--porcelain").stdout.strip(),
          git(one, "status", "--porcelain").stdout[:200])
    check("fiche visible à la cible dans git",
          "alpha/projects/two/tasks/RM9201_tache-de-test.md"
          in git(one, "ls-files").stdout)

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        return 1
    print("✓ pm-task-move : tout vert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
