#!/usr/bin/env python3
"""Tests RM3209 — d'où partent les worktrees, où vont les envs.

Trois réglages (décision du 2026-09-16) :
- `git.worktree_source` (instance, admin) : `central` = `<ws>/repos/<repo>.git` ; `per_user` = le dépôt du dev ;
- dossier des dépôts (par utilisateur, `PM_REPOS_DIR` de son `<core>/var/users/<user>/.env`, défaut `~/repos`) ;
- `git.envs_layout` (instance, admin) : `project` = `<ws>/envs/<env>` ; `user` = `<ws>/envs/<user>/<env>`.

Ce qui doit tenir :
- sans réglage, tout reste comme avant (central + project) ;
- les réglages d'instance se lisent dans les FICHIERS de conf (local prime) — une variable d'environnement ne les
  contourne pas : ils sont réservés à l'admin ;
- une valeur inconnue est refusée, pas rabattue sur le défaut ;
- le dossier des dépôts d'un AUTRE utilisateur se lit dans SON .env, pas dans l'environnement courant ;
- deux chemins qui désignent le même dépôt (lien symbolique) sont reconnus comme tels ;
- le workspace d'une tâche se retrouve par le lien du projet, sans suivre le `.mmi-pm` jusqu'aux données.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_worktrees as wt  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        core = d / "core"
        core.mkdir()

        print("lecture des réglages d'instance")
        lay = wt.read_layout(core)
        check("défaut : central + project", (lay.source, lay.envs_layout) == ("central", "project"), lay)
        (core / "pm.config.yml").write_text("git:\n  worktree_source: per_user\n")
        check("pm.config.yml lu", wt.read_layout(core).source == "per_user")
        (core / "pm.config.local.yml").write_text("git:\n  envs_layout: user\n  worktree_source: central\n")
        lay = wt.read_layout(core)
        check("pm.config.local.yml prime", (lay.source, lay.envs_layout) == ("central", "user"), lay)
        os.environ["PM_WORKTREE_SOURCE"] = "per_user"
        os.environ["PM_ENVS_LAYOUT"] = "project"
        lay = wt.read_layout(core)
        check("l'environnement ne contourne pas l'admin", (lay.source, lay.envs_layout) == ("central", "user"), lay)
        os.environ.pop("PM_WORKTREE_SOURCE")
        os.environ.pop("PM_ENVS_LAYOUT")
        (core / "pm.config.local.yml").write_text("git:\n  worktree_source: partout\n")
        check("valeur inconnue refusée", raises(lambda: wt.read_layout(core), wt.LayoutError))
        (core / "pm.config.local.yml").unlink()
        (core / "pm.config.yml").write_text("git: [pas, un, dict]\n")
        check("section git mal formée refusée", raises(lambda: wt.read_layout(core), wt.LayoutError))

        print("dossier des dépôts d'un utilisateur")
        home = d / "home" / "alex"
        home.mkdir(parents=True)
        check("défaut ~/repos", wt.user_repos_dir(home=home, environ={}) == home / "repos")
        check("PM_REPOS_DIR de l'environnement (utilisateur courant)",
              wt.user_repos_dir(home=home, environ={"PM_REPOS_DIR": "/srv/depots"}) == Path("/srv/depots"))
        check("~ résolu contre le home visé", wt.user_repos_dir(home=home, environ={"PM_REPOS_DIR": "~/code"}) == home / "code")
        check("relatif résolu contre le home", wt.user_repos_dir(home=home, environ={"PM_REPOS_DIR": "src"}) == home / "src")
        (home / ".config" / "mmi-pm").mkdir(parents=True)
        (home / ".config" / "mmi-pm" / ".env").write_text("REDMINE_API_KEY=x\nPM_REPOS_DIR='~/git'\n")
        check("autre utilisateur : lu dans SON .env", wt.user_repos_dir(home=home, environ=None) == home / "git")
        check("autre utilisateur : l'environnement courant n'est pas le sien",
              wt.user_repos_dir(home=home, environ=None, current=False) == home / "git")

        print("source et destination")
        ws = d / "ws"
        c, p = wt.Layout("central", "project"), wt.Layout("per_user", "user")
        check("central → bare du workspace", wt.source_repo(ws, "site", c) == ws / "repos" / "site.git")
        check("per_user → dépôt du dev", wt.source_repo(ws, "site", p, repos_dir=home / "repos") == home / "repos" / "site")
        check("per_user sans dossier de dépôts → erreur", raises(lambda: wt.source_repo(ws, "site", p), wt.LayoutError))
        check("project → envs/<env>", wt.env_dir(ws, "site-rm12", c) == ws / "envs" / "site-rm12")
        check("user → envs/<user>/<env>", wt.env_dir(ws, "site-rm12", p, user="alex") == ws / "envs" / "alex" / "site-rm12")
        check("user sans utilisateur → erreur", raises(lambda: wt.env_dir(ws, "x", p), wt.LayoutError))
        check("création de bare autorisée en central seulement",
              wt.bare_creation_allowed(c) and not wt.bare_creation_allowed(p))

        print("même dépôt à travers un lien")
        real = d / "vrai"
        real.mkdir()
        (home / "repos").mkdir()
        (home / "repos" / "site").symlink_to(real)
        check("lien reconnu", wt.same_repo(home / "repos" / "site", real))
        check("dépôts distincts distingués", not wt.same_repo(home / "repos", real))

        print("workspace d'une tâche")
        projects = d / "projects"
        data = d / "data" / "site" / ".mmi-pm" / "tasks"
        data.mkdir(parents=True)
        (data / "RM12_x.md").write_text("---\n---\n")
        (ws).mkdir(exist_ok=True)
        (ws / ".mmi-pm").symlink_to(d / "data" / "site" / ".mmi-pm")
        link = projects / "clients" / "client-a" / "projects" / "site"
        link.parent.mkdir(parents=True)
        link.symlink_to(ws / ".mmi-pm")
        md = link / "tasks" / "RM12_x.md"
        check("par le lien du projet, pas par les données", wt.workspace_for_task(md, projects) == ws,
              wt.workspace_for_task(md, projects))
        colo = d / "ws2"
        (colo / ".mmi-pm" / "tasks").mkdir(parents=True)
        (colo / ".mmi-pm" / "tasks" / "RM13_y.md").write_text("---\n---\n")
        check("co-localisé sans lien : parent du .mmi-pm",
              wt.workspace_for_task(colo / ".mmi-pm" / "tasks" / "RM13_y.md", projects) == colo)

    print("source d'une branche en per_user (vrais dépôts git)")
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        g = lambda *a, cwd: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)
        mine = d / "home" / "alex" / "repos" / "site"
        mine.mkdir(parents=True)
        g("init", "-q", "-b", "dev", cwd=mine)
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init", cwd=mine)
        g("worktree", "add", "-q", "-b", "12-x", str(d / "ws" / "envs" / "site-rm12"), cwd=mine)
        other = d / "home" / "bea" / "repos" / "site"
        other.mkdir(parents=True)
        g("init", "-q", cwd=other)
        common = lambda root: g("rev-parse", "--git-common-dir", cwd=root).stdout.strip()
        check("depuis son dépôt : accepté", wt.per_user_source_error(mine, common(mine), mine) is None)
        linked = d / "ws" / "envs" / "site-rm12"
        check("depuis un worktree lié de son dépôt : accepté",
              wt.per_user_source_error(linked, common(linked), mine) is None, wt.per_user_source_error(linked, common(linked), mine))
        err = wt.per_user_source_error(other, common(other), mine)
        check("depuis le dépôt d'un autre : refus nommant les deux", err and str(mine) in err and str(other) in err, err)
        lien = d / "home" / "alex" / "lien"
        lien.symlink_to(mine)
        check("dépôt attendu désigné par un lien : accepté", wt.per_user_source_error(mine, common(mine), lien) is None)

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
