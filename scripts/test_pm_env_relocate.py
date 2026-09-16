#!/usr/bin/env python3
"""Tests RM3209 — `pm-env-relocate` : déplacer des envs existants sans rien perdre, les références suivant.

Reproduit, en petit et avec de vrais dépôts git, ce qu'un audit d'instance client a trouvé (2026-09-16) :
- deux envs du même propriétaire sur la MÊME branche (git refuse deux worktrees sur une branche) ;
- du travail non poussé : fichier modifié, stash, branche jamais poussée, fichiers non suivis et ignorés ;
- des liens relatifs qui sortent de l'env (`data -> ../data_dev`, `AGENTS.md -> ../AGENTS.md`) ;
- un vhost qui cite `…/alice` ET `…/alice2` (piège de préfixe).
"""
import contextlib
import getpass
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_worktrees   # noqa: E402

spec = importlib.util.spec_from_file_location("pm_env_relocate", HERE / "pm-env-relocate.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)
FAIL = []
ME = getpass.getuser()


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def g(*a, cwd):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def fixture(d: Path):
    ws = d / "site"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("règles\n")
    (d / "data_dev").mkdir()
    (d / "data_dev" / "photo.jpg").write_text("jpg")
    (ws / "data_dev").symlink_to(d / "data_dev")
    origin = d / "origin.git"
    g("init", "-q", "--bare", "-b", "dev", str(origin), cwd=d)
    seed = d / "seed"
    g("clone", "-q", str(origin), str(seed), cwd=d)
    (seed / ".gitignore").write_text("vendor/\n")
    (seed / "app.php").write_text("v1\n")
    g("add", ".", cwd=seed); g("commit", "-q", "-m", "init", cwd=seed); g("push", "-q", "origin", "dev", cwd=seed)
    g("checkout", "-q", "-b", "feature/x", cwd=seed); (seed / "app.php").write_text("v2\n")
    g("commit", "-qam", "x", cwd=seed); g("push", "-q", "origin", "feature/x", cwd=seed)
    envs = {}
    for name in ("alice", "alice2"):
        e = ws / name
        g("clone", "-q", "-b", "feature/x", str(origin), str(e), cwd=d)
        (e / "data").symlink_to("../data_dev")
        (e / "AGENTS.md").symlink_to("../AGENTS.md")
        (e / "vendor").mkdir(); (e / "vendor" / "lib.php").write_text("ignoré\n")
        (e / "notes.txt").write_text("non suivi\n")
        envs[name] = e
    a = envs["alice"]
    (a / "app.php").write_text("modif locale\n")
    g("stash", "-q", cwd=a)
    (a / "app.php").write_text("modif en cours\n")
    g("checkout", "-q", "-b", "jamais-poussee", cwd=a); g("commit", "-q", "--allow-empty", "-m", "local", cwd=a)
    g("checkout", "-q", "feature/x", cwd=a)
    vhost = d / "etc" / "site.conf"
    vhost.parent.mkdir()
    vhost.write_text(f'DocumentRoot "{ws}/alice/public"\nDocumentRoot "{ws}/alice2/public"\n'
                     f'<Directory {ws}/alice2>\n')
    plan = d / "plan.yml"
    plan.write_text(
        f"workspace: {ws}\nrepo: site\ncompat_links: [AGENTS.md, data_dev, agent_config]\n"
        f"references: ['{d}/etc/*.conf']\nvalidate: []\n"
        f"envs:\n  - {{from: {ws}/alice, name: site}}\n  - {{from: {ws}/alice2, name: site-2}}\n")
    return ws, envs, vhost, plan


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = pr.main([str(a) for a in argv])
    return rc, out.getvalue() + err.getvalue()


def main():
    pr.pm_worktrees.read_layout = lambda *a, **k: pm_worktrees.Layout("per_user", "user")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        os.environ["PM_REPOS_DIR"] = str(d / "home" / "repos")
        ws, envs, vhost, plan = fixture(d)
        a_sha = g("rev-parse", "HEAD", cwd=envs["alice"])
        vhost_avant = vhost.read_text()

        print("garde : snapshot exigé")
        rc, out = run("--plan", plan)
        check("sans --snapshot ni --no-snapshot → refus", rc == 2 and "snapshot" in out, out)

        print("essai à blanc")
        rc, out = run("--plan", plan, "--dry-run")
        check("rc 0", rc == 0, out)
        check("rien n'a bougé", envs["alice"].is_dir() and not (ws / "envs").exists())
        check("diff de référence montré", f"{ws}/envs/{ME}/site-2/public" in out, out[-600:])

        print("exécution")
        journal = d / "journal.json"
        rc, out = run("--plan", plan, "--no-snapshot", "--journal", journal)
        check("rc 0", rc == 0, out[-800:])
        dest = ws / "envs" / ME / "site"
        dest2 = ws / "envs" / ME / "site-2"
        check("anciens dossiers déplacés", not envs["alice"].exists() and dest.is_dir() and dest2.is_dir())
        check("adopté : .git est un worktree", (dest / ".git").is_file() and (dest2 / ".git").is_file())
        repo = d / "home" / "repos" / "site"
        check("dépôt du propriétaire créé", (repo / ".git").is_dir())
        check("même commit", g("rev-parse", "HEAD", cwd=dest) == a_sha)
        check("modification en cours préservée", (dest / "app.php").read_text() == "modif en cours\n"
              and "app.php" in g("status", "--porcelain", cwd=dest))
        check("non suivi et ignoré préservés", (dest / "notes.txt").exists() and (dest / "vendor" / "lib.php").exists())
        stash = g("for-each-ref", "--format=%(refname)", "refs/relocate/site/stash", cwd=repo)
        check("stash importé", stash.strip() != "", stash)
        check("contenu du stash intact", "modif locale" in g("show", f"{stash.split()[0]}:app.php", cwd=repo))
        check("branche jamais poussée importée",
              g("rev-parse", "--verify", "refs/heads/relocate/site/jamais-poussee", cwd=repo) != "")
        b1, b2 = g("branch", "--show-current", cwd=dest), g("branch", "--show-current", cwd=dest2)
        check("1er env sur sa branche d'origine", b1 == "feature/x", b1)
        check("2e env, même branche : branche dérivée", b2 == "relocate/site-2/feature/x", b2)
        check("liens relatifs résolus via les liens de compatibilité",
              (dest / "data" / "photo.jpg").read_text() == "jpg" and (dest / "AGENTS.md").read_text() == "règles\n")
        check("lien de compatibilité absent de la source ignoré", not (ws / "envs" / ME / "agent_config").exists())
        v = vhost.read_text()
        check("vhost réécrit au chemin exact (alice / alice2)",
              f'"{dest}/public"' in v and f'"{dest2}/public"' in v and f"<Directory {dest2}>" in v, v)
        check("journal écrit", json.loads(journal.read_text())["ops"])

        print("annulation")
        rc, out = run("--undo", journal)
        check("rc 0", rc == 0, out)
        check("envs remis en place", envs["alice"].is_dir() and not dest.exists())
        check("redevenus clones complets", (envs["alice"] / ".git").is_dir() and (envs["alice2"] / ".git").is_dir())
        check("travail intact après annulation", (envs["alice"] / "app.php").read_text() == "modif en cours\n"
              and g("rev-parse", "HEAD", cwd=envs["alice"]) == a_sha)
        check("stash de l'env d'origine toujours là", g("stash", "list", cwd=envs["alice"]) != "")
        check("vhost restauré", vhost.read_text() == vhost_avant)
        check("liens de compatibilité retirés", not (ws / "envs" / ME / "AGENTS.md").is_symlink())

        print("validation en échec → références restaurées")
        plan.write_text(plan.read_text().replace("validate: []", "validate: ['exit 1']"))
        rc, out = run("--plan", plan, "--no-snapshot", "--journal", d / "j2.json")
        check("rc 3", rc == 3, out[-400:])
        check("vhost restauré après échec", vhost.read_text() == vhost_avant)
        rc, _ = run("--undo", d / "j2.json")
        check("annulation après échec : envs remis", rc == 0 and envs["alice"].is_dir())

        print("refus au contrôle préalable (rien ne bouge)")
        rc, out = run("--plan", plan, "--dry-run")
        (ws / "envs" / ME / "site").mkdir(parents=True)
        rc, out = run("--plan", plan, "--no-snapshot")
        check("destination occupée → refus, source intacte", rc == 2 and "occupée" in out and envs["alice"].is_dir(), out)
        (ws / "envs" / ME / "site").rmdir()
        pr.pm_worktrees.read_layout = lambda *a, **k: pm_worktrees.Layout("central", "project")
        rc, out = run("--plan", plan, "--dry-run")
        check("adoption demandée en central → refus", rc == 2 and "pm-env-migrate" in out, out)
        pr.pm_worktrees.read_layout = lambda *a, **k: pm_worktrees.Layout("per_user", "user")
        check("autre système de fichiers → refus", "même système de fichiers" in str(_raises(
            lambda: pr.resolve_plan(pr.load_plan(plan), pm_worktrees.Layout("per_user", "user"),
                                    st_dev=lambda p: 1 if str(p).endswith("alice") else 2))))

    print("réécriture au chemin exact")
    moves = [("/h/alice", "/h/envs/a/sf7"), ("/h/alice2", "/h/envs/a/sf7-2")]
    t = pr.rewrite_text('"/h/alice/public" /h/alice2 /h/alice_old /h/alice.bak /h/alice\n', moves)
    check("préfixes, soulignés et points non touchés",
          t == '"/h/envs/a/sf7/public" /h/envs/a/sf7-2 /h/alice_old /h/alice.bak /h/envs/a/sf7\n', t)

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


def _raises(fn):
    try:
        fn()
    except pr.RelocateError as e:
        return e
    return None


if __name__ == "__main__":
    sys.exit(main())
