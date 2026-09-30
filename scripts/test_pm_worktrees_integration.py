#!/usr/bin/env python3
"""Tests RM3209 — les réglages de worktrees, branchés dans les outils réels.

- `pm-branch-start` : la racine des envs vient des réglages quand ils existent ; sinon, comme avant ;
- `pm-env-session create` en `per_user` + `user` : part du dépôt de l'utilisateur, pose l'env sous
  `envs/<utilisateur>/`, et dit clairement quoi faire quand ce dépôt manque ;
- `pm-env-init` refuse de créer un dépôt partagé en `per_user` ; `pm-env-migrate` renvoie vers `env-relocate` ;
- cockpit : les deux réglages existent, avec les mêmes valeurs que le résolveur, et exigent l'admin.
"""
import contextlib
import getpass
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core   # noqa: E402
hermetic_core()
import pm_worktrees   # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def g(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def workspace(base: Path) -> Path:
    ws = base / "site"
    (ws / ".mmi-pm" / "tasks").mkdir(parents=True)
    (ws / ".mmi-pm" / "meta.yml").write_text("repos:\n- name: site\n  integration_branch: dev\n  remotes: {}\n")
    return ws


def temp_core(base: Path, scripts, config: str) -> Path:
    """Une instance jetable, modules COPIÉS : un module lié par symlink réinjecterait le vrai `scripts/` en tête
    du sys.path (`Path(__file__).resolve()`), et le script testé lirait alors la vraie configuration."""
    core = base / "core"
    (core / "scripts").mkdir(parents=True)
    for f in HERE.iterdir():
        if f.suffix == ".py" and not f.name.startswith("test"):
            shutil.copy(f, core / "scripts" / f.name)
    shutil.copy(HERE.parent / "pm.config.yml", core / "pm.config.yml")
    (core / "pm.config.local.yml").write_text(config)
    return core


def main():
    me = getpass.getuser()

    print("pm-branch-start : racine des envs")
    pbs = load("pm_branch_start", "pm-branch-start.py")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        root = d / "home" / "repos" / "site"
        root.mkdir(parents=True)
        check("sans réglage : à côté du dépôt courant, comme avant",
              pbs.worktree_path(root, 12, "12-x", 3) == root.parent / "site-rm12")
        envs = d / "ws" / "envs" / me
        check("avec réglages : sous la racine résolue", pbs.worktree_path(root, 12, "12-x", 3, envs=envs) == envs / "site-rm12")

    print("pm-env-session create en per_user + user")
    pes = load("pm_env_session", "pm-env-session.py")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ws = workspace(d)
        conf = d / "conf"
        conf.mkdir()
        (conf / "pm.config.local.yml").write_text("git:\n  worktree_source: per_user\n  envs_layout: user\n")
        pes.LAYOUT_CORE = conf
        repos = d / "depots"
        os.environ["PM_REPOS_DIR"] = str(repos)
        layout, src, envs = pes.source_and_envs(ws, "site")
        check("source = dépôt de l'utilisateur", src == repos / "site", src)
        check("envs = envs/<utilisateur>", envs == ws / "envs" / me, envs)
        args = SimpleNamespace(db_clone=False, no_db_clone=False, workspace=str(ws), repo=None, rmid=12,
                               slug="essai", dry_run=True)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                pes.cmd_create(args)
            check("dépôt absent → refus", False)
        except SystemExit as e:
            check("dépôt absent → refus qui dit quoi faire", "dépôt personnel absent" in str(e) and "PM_REPOS_DIR" in str(e), e)
        (repos / "site").mkdir(parents=True)
        g("init", "-q", "-b", "dev", cwd=repos / "site")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init", cwd=repos / "site")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pes.cmd_create(args)
        check("à blanc : création annoncée depuis le dépôt de l'utilisateur", "git worktree add -b 12-essai" in out.getvalue(),
              out.getvalue())
        args.dry_run = False
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                pes.cmd_create(args)
            except SystemExit:
                pass
        wt = ws / "envs" / me / "site-rm12"
        check("worktree réellement créé sous envs/<utilisateur>/", (wt / ".git").is_file(), list((ws / "envs").rglob("*"))[:5])
        common = g("rev-parse", "--git-common-dir", cwd=wt).stdout.strip()
        check("worktree lié au dépôt de l'utilisateur",
              pm_worktrees.main_repo_dir(wt, common).resolve() == (repos / "site").resolve(), common)
        os.environ.pop("PM_REPOS_DIR")
        pes.LAYOUT_CORE = None

    print("pm-env-init / pm-env-migrate en per_user")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ws = workspace(d)
        core = temp_core(d, ["pm-env-init.py", "pm-env-migrate.py"], "git:\n  worktree_source: per_user\n")
        r = subprocess.run([sys.executable, str(core / "scripts" / "pm-env-init.py"), str(ws)], capture_output=True, text=True)
        check("pm-env-init refuse de créer un dépôt partagé", r.returncode != 0 and "per_user" in r.stderr and not (ws / "repos").exists(),
              r.stdout[-300:] + r.stderr[-300:])
        r = subprocess.run([sys.executable, str(core / "scripts" / "pm-env-migrate.py"), str(ws), "--dry-run"],
                           capture_output=True, text=True)
        check("pm-env-migrate renvoie vers env-relocate", r.returncode != 0 and "env-relocate" in r.stderr, r.stdout[-300:] + r.stderr[-300:])

    print("cockpit : réglages exposés, réservés à l'admin")
    ka = load("karl_agent", "karl-agent.py")
    by = {e["key"]: e for e in ka._PM_SETTINGS_CONF}
    src, lay = by.get("conf:git.worktree_source"), by.get("conf:git.envs_layout")
    check("source : mêmes valeurs que le résolveur", src and tuple(src["options"]) == pm_worktrees.SOURCES, src)
    check("disposition : mêmes valeurs que le résolveur", lay and tuple(lay["options"]) == pm_worktrees.LAYOUTS, lay)
    check("défauts = comportement antérieur", src["default"] == "central" and lay["default"] == "project")
    check("réservés à l'admin", ka.setting_requires_admin("conf:git.worktree_source") and ka.setting_requires_admin("conf:git.envs_layout"))
    check("les autres réglages inchangés", not ka.setting_requires_admin("conf:git.autocommit"))

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
