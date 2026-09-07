#!/usr/bin/env python3
"""Tests RM3033 — mmi-pm.py : résolution `<cmd>` et repli `<nom> <verbe>` → pm-<nom>-<verbe>, alias par nom d'appel (mmi-<domaine>),
--list (filtré), exécution transparente (subprocess sur un faux dossier de scripts via PM_CORE_DIR)."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mmi_pm", HERE / "mmi-pm.py"); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("argv_for : mmi-pm inchangé", M.argv_for("/usr/local/bin/mmi-pm", ["core", "update"]) == ["core", "update"] and M.argv_for("mmi-pm.py", ["x"]) == ["x"])
check("argv_for : mmi-<domaine> préfixe", M.argv_for("/usr/local/bin/mmi-core", ["update", "--dry-run"]) == ["core-update", "--dry-run"] and M.argv_for("mmi-task", ["show", "42"]) == ["task-show", "42"])
check("argv_for : mmi-<domaine> seul → liste du domaine", M.argv_for("mmi-task", []) == ["--list", "task"] and M.argv_for("mmi-env", ["--help"]) == ["--list", "env"])
t, r = M.resolve("core", ["update", "--dry-run"]); check("repli nom verbe → pm-core-update.py, verbe consommé", t.name == "pm-core-update.py" and r == ["--dry-run"])
t, r = M.resolve("task-show", ["42"]); check("cmd direct → pm-task-show.py, args intacts", t.name == "pm-task-show.py" and r == ["42"])
t, r = M.resolve("index", ["add", "a/b"]); check("index add → pm-index-add.py", t.name == "pm-index-add.py" and r == ["a/b"])
check("inconnu → None", M.resolve("zz", ["x"]) == (None, ["x"]) and M.resolve("core", ["--dry-run"]) == (None, ["--dry-run"]))
cmds = M._list_commands(); check("--list voit les verbes portés", all(c in cmds for c in ("core-update", "index-add", "index-remove", "index-rebuild", "index-list", "env-vhost", "task-add")))

with tempfile.TemporaryDirectory() as td:
    core = pathlib.Path(td); sc = core / "scripts"; sc.mkdir()
    (sc / "pm-demo-run.py").write_text("import sys; print('demo-run', *sys.argv[1:])\n")
    (sc / "pm-solo.py").write_text("import sys; print('solo', *sys.argv[1:])\n")
    (sc / "pm-other").write_text("#!/bin/sh\necho other \"$@\"\n"); os.chmod(sc / "pm-other", 0o755)
    env = dict(os.environ, PM_CORE_DIR=str(core))
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "mmi-pm.py"), *a], capture_output=True, text=True, env=env)  # noqa: E731
    check("exécution directe", run("demo-run", "a", "b").stdout.strip() == "demo-run a b")
    check("exécution par repli « nom verbe »", run("demo", "run", "--x").stdout.strip() == "demo-run --x")
    check("script sans extension", run("other", "1").stdout.strip() == "other 1")
    r = run("nope"); check("inconnu : code 1 + message", r.returncode == 1 and "sous-commande inconnue 'nope'" in r.stderr)
    check("--list et --list <domaine>", run("--list").stdout.split() == ["demo-run", "other", "solo"] and run("--list", "demo").stdout.split() == ["demo-run"])
    alias = core / "mmi-demo"; alias.symlink_to(HERE / "mmi-pm.py")
    r = subprocess.run([sys.executable, str(alias), "run", "z"], capture_output=True, text=True, env=env)
    check("alias mmi-demo run → demo-run", r.stdout.strip() == "demo-run z", r.stdout + r.stderr)
    check("alias mmi-demo seul → liste du domaine", subprocess.run([sys.executable, str(alias)], capture_output=True, text=True, env=env).stdout.split() == ["demo-run"])

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — dispatcher mmi-pm (RM3033)")
