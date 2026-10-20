#!/usr/bin/env python3
"""Test hors ligne de pm-task-delete (RM3468).

Ce qui casse en silence si on se trompe : un plan (sans --apply) qui détruirait
quand même, un ticket porteur de travail supprimé sans --force, un frère de la fiche
oublié (think, script de MEP), une suppression non committée, et une trace absente
du journal PM — la seule qui reste une fois le ticket parti.

Aucun appel réseau : les invocations passent `--no-redmine` ; la lecture des
relations et du travail côté Redmine est testée sur des issues simulées.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from test_support import subprocess_env                          # noqa: E402

DELETE = SCRIPTS / "pm-task-delete.py"
FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} {detail}")
        FAILURES.append(label)


def run(env, *args):
    return subprocess.run([sys.executable, str(DELETE), *args], env=env,
                          capture_output=True, text=True, cwd=str(SCRIPTS))


def make_project(root, entity, project, redmine_id):
    d = root / "clients" / entity / "projects" / project
    (d / "tasks").mkdir(parents=True, exist_ok=True)
    (d / "project").mkdir(parents=True, exist_ok=True)
    (d / "meta.yml").write_text(
        f"schema_version: 1.7.1\nslug: {project}\nclient: {entity}\n"
        f"redmine:\n  project_id: {redmine_id}\n", encoding="utf-8")
    return d


def make_task(tasks_dir, rm_id, slug="bruit", extra=""):
    md = tasks_dir / f"RM{rm_id}_{slug}.md"
    md.write_text(f"---\nschema_version: 1.11.0\nredmine_id: {rm_id}\n"
                  f"title: 'Ticket de bruit'\ntype: security\nstatus: nouveau\n"
                  f"{extra}created: '2026-10-09'\nupdated: 2026-10-09T10:00\n---\n\n"
                  f"## Contexte\n\nRien.\n", encoding="utf-8")
    (tasks_dir / f"RM{rm_id}_{slug}.log.md").write_text(f"# Journal RM{rm_id}\n", encoding="utf-8")
    (tasks_dir / f"RM{rm_id}_{slug}.think.md").write_text("# Réflexion\n", encoding="utf-8")
    (tasks_dir / f"RM{rm_id}_{slug}.script-mep.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return md


def siblings(tasks_dir, rm_id, slug="bruit"):
    return [tasks_dir / f"RM{rm_id}_{slug}{s}" for s in (".md", ".log.md", ".think.md", ".script-mep.sh")]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def load_module():
    spec = importlib.util.spec_from_file_location("pm_task_delete", DELETE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    journal = Path(tempfile.mkdtemp(prefix="pm-delete-journal-"))
    worklogs = Path(tempfile.mkdtemp(prefix="pm-delete-worklogs-"))
    env = subprocess_env(KARL_JOURNAL_DIR=journal, KARL_JOURNAL_STDERR="0",
                         PM_SESSION_WORKLOG_DIR=worklogs)
    root = Path(env["PM_CORE_DIR"]) / "projects"
    proj = make_project(root, "alpha", "one", "alpha-one")
    tasks = proj / "tasks"

    print("· plan et refus")
    make_task(tasks, 9101)
    r = run(env, "9101", "--no-redmine")
    check("--reason obligatoire", r.returncode != 0)
    r = run(env, "9101", "--reason", "   ", "--no-redmine", "--apply")
    check("--reason vide refusé", r.returncode != 0 and all(f.exists() for f in siblings(tasks, 9101)))
    r = run(env, "9101", "--reason", "bruit", "--no-redmine")
    check("sans --apply : plan, rien n'est supprimé",
          r.returncode == 0 and all(f.exists() for f in siblings(tasks, 9101)), r.stderr[:200])
    r = run(env, "9404", "--reason", "bruit", "--no-redmine", "--apply")
    check("ticket sans fiche refusé", r.returncode != 0)

    print("· suppression nominale (sans git)")
    # le cockpit liste « reste à faire » depuis les worklogs de session
    for sid, refs in (("sess-a", ["RM9101", "RM9500"]), ("sess-b", ["RM9500"])):
        (worklogs / f"{sid}.json").write_text(json.dumps({
            "session_id": sid, "title": None, "updated": "2026-10-13T10:00",
            "items": [{"id": n + 1, "ref": r, "label": r, "status": "nouveau"}
                      for n, r in enumerate(refs)]}), encoding="utf-8")
    r = run(env, "9101", "--reason", "faux positif (test)", "--no-redmine", "--apply", "--no-commit")
    check("sortie 0", r.returncode == 0, r.stderr[:300])
    check("fiche et frères supprimés (journal, think, script de MEP)",
          not any(f.exists() for f in siblings(tasks, 9101)))
    refs_a = [i["ref"] for i in json.loads((worklogs / "sess-a.json").read_text())["items"]]
    refs_b = [i["ref"] for i in json.loads((worklogs / "sess-b.json").read_text())["items"]]
    check("retiré du worklog de session (et lui seul)", refs_a == ["RM9500"] and refs_b == ["RM9500"],
          f"{refs_a} {refs_b}")
    lines = [json.loads(l) for f in journal.glob("*.jsonl") for l in f.read_text().splitlines() if l.strip()]
    trace = [l for l in lines if l.get("rm_id") == 9101]
    check("trace au journal PM (motif, titre, projet)",
          bool(trace) and trace[0].get("reason") == "faux positif (test)"
          and trace[0].get("title") == "Ticket de bruit" and trace[0].get("project") == "alpha/one",
          str(lines)[:300])

    print("· garde-fous")
    make_task(tasks, 9102, extra="git:\n  repo: x\n  branch: 9102-truc\n")
    r = run(env, "9102", "--reason", "bruit", "--no-redmine", "--apply", "--no-commit")
    check("branche de code → refus, rien supprimé",
          r.returncode != 0 and "travail" in (r.stdout + r.stderr)
          and all(f.exists() for f in siblings(tasks, 9102)))
    r = run(env, "9102", "--reason", "bruit", "--no-redmine", "--apply", "--no-commit", "--force")
    check("--force lève le refus", r.returncode == 0 and not siblings(tasks, 9102)[0].exists(), r.stderr[:200])

    make_task(tasks, 9103, extra="relates:\n- 9999\n")
    r = run(env, "9103", "--reason", "bruit", "--no-redmine", "--apply", "--no-commit")
    check("lié + --no-redmine → refus (miroirs impossibles à nettoyer)",
          r.returncode != 0 and siblings(tasks, 9103)[0].exists())

    print("· lecture Redmine (issues simulées)")
    mod = load_module()
    fm = {"redmine_id": 3433, "relates": [3414]}
    issue = {"relations": [{"issue_id": 3414, "issue_to_id": 3433}, {"issue_id": 3433, "issue_to_id": 3500}],
             "spent_hours": 0.0, "children": [], "changesets": []}
    check("liens = fiche ∪ Redmine, sans soi-même", mod.linked_ids(fm, issue) == [3414, 3500],
          str(mod.linked_ids(fm, issue)))
    check("ticket de bruit : aucun travail", mod.blockers(fm, issue) == [])
    busy = dict(issue, spent_hours=1.5, children=[{"id": 1}], changesets=[{"revision": "abc"}])
    check("temps, sous-tâches et commits = travail", len(mod.blockers(fm, busy)) == 3,
          str(mod.blockers(fm, busy)))

    print("· commit de la suppression")
    two = Path(tempfile.mkdtemp(prefix="pm-delete-git-"))
    env2 = subprocess_env(PROJECTS_PATH=two / "projects", KARL_JOURNAL_DIR=journal)
    p2 = make_project(two / "projects", "beta", "two", "beta-two")
    make_task(p2 / "tasks", 9201)
    repo = two / "projects" / "clients" / "beta"
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / ".mmi-pm").mkdir(exist_ok=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    r = run(env2, "9201", "--reason", "bruit", "--no-redmine", "--apply")
    check("sortie 0 (git)", r.returncode == 0, r.stderr[:300])
    tracked = git(repo, "ls-files").stdout
    check("suppression committée", "RM9201_" not in tracked and not git(repo, "status", "--porcelain").stdout.strip(),
          git(repo, "status", "--porcelain").stdout[:300])
    check("message de commit porte le motif", "supprimé — bruit" in git(repo, "log", "-1", "--format=%s").stdout)

    print(f"\n{'OK' if not FAILURES else 'ÉCHEC'} — {len(FAILURES)} échec(s)")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
