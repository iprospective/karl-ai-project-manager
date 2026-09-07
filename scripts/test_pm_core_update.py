#!/usr/bin/env python3
"""Tests RM3033 — pm-core-update.py (port de `bin/mmi-pm core update`) : lecture du .env, détection du redémarrage karl-agent,
plans (hooks, co-déploiement, alias), dry-run sans privilège sur un dépôt temporaire, refus hors root sans dry-run (message sudo)."""
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_core_update", HERE / "pm-core-update.py"); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("needs_agent_restart : seul scripts/karl-agent.py compte", C.needs_agent_restart(["scripts/karl-agent.py", "x"]) and not C.needs_agent_restart(["scripts/pm-task-add.py", "deploy/karl-agent/cockpit/index.html"]) and not C.needs_agent_restart([]))
with tempfile.TemporaryDirectory() as td:
    core = pathlib.Path(td) / "core"; (core / "scripts").mkdir(parents=True)
    (core / ".env").write_text('KARL_USER="mathieu"\n# commentaire\nPROJECTS_PATH=/p\nVIDE\n')
    check("read_env : quotes dépouillées, commentaires et lignes sans = ignorés", C.read_env(core / ".env") == {"KARL_USER": "mathieu", "PROJECTS_PATH": "/p"} and C.read_env(core / "absent") == {})
    subprocess.run(["git", "init", "-q", str(core)], check=True); subprocess.run(["git", "-C", str(core), "config", "user.email", "t@t"], check=True); subprocess.run(["git", "-C", str(core), "config", "user.name", "t"], check=True)
    (core / "scripts" / "pm-post-commit.py").write_text("#"); (core / "scripts" / "pm-pre-push").write_text("#")
    (core / ".git" / "hooks").mkdir(exist_ok=True); (core / ".git" / "hooks" / "pre-push").write_text("vrai fichier")
    plan = {n: a for n, _, a in C.hooks_plan(core)}
    check("hooks_plan : link / manual (fichier non-symlink) / skip-missing", plan == {"post-commit": "link", "pre-push": "manual", "pre-commit": "skip-missing"}, str(plan))
    dp = C.deploy_plan(core); check("deploy_plan : sources absentes → rien", dp == [])
    (core / "tools" / "env-runtime").mkdir(parents=True); (core / "tools" / "env-runtime" / "pm-env-helper.sh").write_text("#!/bin/sh\n")
    dp = C.deploy_plan(core); check("deploy_plan : source présente, cible absente → à installer", len(dp) == 1 and dp[0][1] == pathlib.Path("/usr/local/sbin/pm-env-helper") and dp[0][3] is True)
    bindir = pathlib.Path(td) / "bin"; bindir.mkdir()
    check("alias_plan : sans mmi-pm installé → skip", all(a == "skip" for *_, a in C.alias_plan(core, bindir)))
    (bindir / "mmi-pm").symlink_to(HERE / "mmi-pm.py"); (bindir / "mmi-task").write_text("vrai fichier"); (bindir / "mmi-core").symlink_to(HERE / "mmi-pm.py")
    ap = {l.name: a for l, _, a in C.alias_plan(core, bindir)}
    check("alias_plan : ok / manual / link", ap["mmi-core"] == "ok" and ap["mmi-task"] == "manual" and ap["mmi-env"] == "link" and set(ap) == {f"mmi-{d}" for d in C.ALIAS_DOMAINS}, str(ap))
    (core / "README.md").write_text("x"); subprocess.run(["git", "-C", str(core), "add", "-A"], check=True); subprocess.run(["git", "-C", str(core), "commit", "-qm", "seed"], check=True)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = C.update(core, dry=True)
    o = out.getvalue()
    check("dry-run : plan complet, rien écrit, code 0", rc == 0 and "[dry] git pull --ff-only origin" in o and "[dry] hook post-commit : link" in o and "[dry] hook pre-push : manual" in o and "/usr/local/sbin/pm-env-helper : à installer" in o and "[dry] alias mmi-core" in o and not (core / ".git" / "hooks" / "post-commit").exists(), o)
    if os.geteuid() != 0:
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                C.update(core, dry=False)
            check("hors root sans dry-run : refus explicite", False)
        except SystemExit as e:
            check("hors root sans dry-run : refus explicite (le re-exec sudo est dans main)", "doit tourner en root" in str(e))
    else:
        check("(root) garde sudo non testée", True)
    try:
        C.update(pathlib.Path(td) / "pasgit", dry=True); check("pas un dépôt git → erreur", False)
    except SystemExit as e:
        check("pas un dépôt git → erreur", "pas un dépôt git" in str(e))
    r = subprocess.run([sys.executable, str(HERE / "pm-core-update.py"), "--dry-run", "--core-dir", str(core)], capture_output=True, text=True)
    check("CLI --dry-run : sans sudo, code 0", r.returncode == 0 and "[dry]" in r.stdout and "re-exec sudo" not in r.stdout, r.stdout + r.stderr)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — pm-core-update (RM3033)")
