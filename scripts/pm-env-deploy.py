#!/usr/bin/env python3
"""pm-env-deploy — déployer la branche d'un ticket dans un env PARTAGÉ du projet
(RM2218, console de test RM2210). À distinguer de pm-env-session (env isolé
par ticket) : ici on bascule un worktree partagé (ex. `envs/<repo>-test`) sur
la branche à tester — ressource concurrente, donc garde-fous stricts.

    deploy  <rmid> [workspace] [--env test] [--repo R] [--force]
            → fetch + switch du worktree partagé sur la branche du ticket
              (refus si worktree sale sans --force ; l'ancienne branche est
              affichée AVANT bascule) + note Redmine + log
    restore <rmid> [workspace] [--env test] [--repo R] [--force]
            → retour du worktree sur la branche d'intégration du manifeste
    status  [workspace] → branche courante de chaque env partagé du workspace

La branche déployée est lue dans le frontmatter du ticket (`git.branch`) —
jamais saisie à la main (tripwire #13). Workspace : argument, sinon découverte
`.mmi-pm` en remontant depuis le cwd.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig


def die(msg):
    sys.exit(f"pm-env-deploy: {msg}")


def git(args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} : {(r.stderr or r.stdout).strip()}")
    return r.returncode, r.stdout.strip()


def find_workspace(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").exists():
            return d
    die(f"aucun `.mmi-pm` en remontant depuis {start} (workspace PM-tracké ?)")


def load_manifest(ws: Path) -> list:
    import yaml
    meta = ws / ".mmi-pm" / "meta.yml"
    if not meta.is_file():
        die(f"manifeste absent : {meta}")
    data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    return data.get("repos") or []


def pick_repo(repos: list, name: str | None) -> dict:
    if not repos:
        die("aucun repo au manifeste (.mmi-pm/meta.yml › repos:) — workspace non normalisé ?")
    if name:
        r = next((r for r in repos if r.get("name") == name), None)
        return r or die(f"repo {name!r} absent du manifeste")
    if len(repos) > 1:
        die(f"plusieurs repos au manifeste ({[r.get('name') for r in repos]}) — précise --repo")
    return repos[0]


def ticket_branch(cfg, rm_id: int) -> str:
    tf = cfg.find_task(rm_id)
    if not tf:
        die(f"ticket RM{rm_id} introuvable en local")
    m = re.search(r"^git:\n(?:  .*\n)*?  branch:\s*(\S+)", tf.read_text(encoding="utf-8"), re.M)
    if not m or m.group(1) in ("null", "~"):
        die(f"RM{rm_id} : pas de branche au frontmatter (git.branch) — pm-branch-start d'abord")
    return m.group(1).strip("'\"")


def env_worktree(ws: Path, code: str, env: str) -> Path:
    wt = ws / "envs" / f"{code}-{env}"
    if not wt.is_dir() or not (wt / ".git").exists():
        die(f"env partagé introuvable : {wt} (pm-env-init --with-{env} ?)")
    return wt


def guard_clean(wt: Path, force: bool):
    _, out = git(["-C", str(wt), "status", "--porcelain"])
    if out and not force:
        die(f"worktree SALE ({len(out.splitlines())} modif(s)) : {wt}\n"
            f"  Un env partagé peut porter le travail de quelqu'un d'autre — inspecte,\n"
            f"  ou relance avec --force en connaissance de cause.")


def trace(rm_id: int, note: str):
    scr = Path(__file__).resolve().parent / "pm-task-comment.py"
    subprocess.run([sys.executable, str(scr), str(rm_id), "--note", note], check=False)


def switch(wt: Path, branch: str):
    git(["-C", str(wt), "fetch", "origin"], check=False)
    rc, _ = git(["-C", str(wt), "switch", branch], check=False)
    if rc != 0:
        rc, _ = git(["-C", str(wt), "switch", "-c", branch, f"origin/{branch}"], check=False)
        if rc != 0:
            die(f"branche {branch} introuvable (locale et origin)")
    git(["-C", str(wt), "pull", "--ff-only"], check=False)


def cmd_deploy(a):
    cfg = PMConfig.load()
    ws = find_workspace(Path(a.workspace) if a.workspace else Path.cwd())
    repo = pick_repo(load_manifest(ws), a.repo)
    branch = ticket_branch(cfg, a.rmid)
    wt = env_worktree(ws, repo["name"], a.env)
    _, cur = git(["-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"])
    print(f"env partagé : {wt.name}  (branche ACTUELLE : {cur})")
    guard_clean(wt, a.force)
    switch(wt, branch)
    print(f"✓ {wt.name} → {branch} (était : {cur})")
    trace(a.rmid, f"Branche `{branch}` déployée dans l'env partagé `{wt.name}` "
                  f"(remplace `{cur}`) via pm-env-deploy.")


def cmd_restore(a):
    ws = find_workspace(Path(a.workspace) if a.workspace else Path.cwd())
    repo = pick_repo(load_manifest(ws), a.repo)
    target = repo.get("integration_branch") or "dev"
    wt = env_worktree(ws, repo["name"], a.env)
    _, cur = git(["-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"])
    guard_clean(wt, a.force)
    switch(wt, target)
    print(f"✓ {wt.name} → {target} (était : {cur})")
    trace(a.rmid, f"Env partagé `{wt.name}` restauré sur `{target}` (quittait `{cur}`) "
                  f"via pm-env-deploy restore.")


def cmd_status(a):
    ws = find_workspace(Path(a.workspace) if a.workspace else Path.cwd())
    envs = sorted((ws / "envs").glob("*")) if (ws / "envs").is_dir() else []
    for wt in envs:
        if not (wt / ".git").exists():
            continue
        _, br = git(["-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"], check=False)
        _, dirty = git(["-C", str(wt), "status", "--porcelain"], check=False)
        print(f"  {wt.name:<40} [{br}]{' — SALE (' + str(len(dirty.splitlines())) + ' modifs)' if dirty else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, with_rm=True):
        if with_rm:
            p.add_argument("rmid", type=int, help="id Redmine du ticket (trace + branche)")
        p.add_argument("workspace", nargs="?", default=None)
        p.add_argument("--env", default="test", help="nom de l'env partagé (défaut : test)")
        p.add_argument("--repo", default=None, help="repo du manifeste (si plusieurs)")
        p.add_argument("--force", action="store_true", help="bascule même si le worktree est sale")

    pd = sub.add_parser("deploy", help="déploie la branche du ticket dans l'env partagé")
    common(pd); pd.set_defaults(fn=cmd_deploy)
    pr = sub.add_parser("restore", help="restaure l'env partagé sur la branche d'intégration")
    common(pr); pr.set_defaults(fn=cmd_restore)
    ps = sub.add_parser("status", help="branche courante de chaque env du workspace")
    ps.add_argument("workspace", nargs="?", default=None); ps.set_defaults(fn=cmd_status)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
