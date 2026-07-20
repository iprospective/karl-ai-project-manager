#!/usr/bin/env python3
"""Tests RM2356 — pm-cockpit-test-env (instance karl-agent de test par ticket).

Unitaire (sans systemd ni réseau) : port déterministe, résolution/refus de
worktree, dry-run, registre, teardown --if-exists silencieux.
Lancer : python3 scripts/test_pm_cockpit_test_env.py
"""
import importlib.util
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cte", HERE / "pm-cockpit-test-env.py")
cte = importlib.util.module_from_spec(spec)
sys.modules["cte"] = cte
spec.loader.exec_module(cte)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — port déterministe, stable, dans la plage —
check("port stable", cte.port_for(2350) == cte.port_for(2350) == 9910)
check("plage bornée", all(9900 <= cte.port_for(i) < 9990 for i in range(2000, 2200)))

# — workspace fabriqué : repos/ + envs/ —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2356-"))
ws = tmp / "ws"
(ws / ".mmi-pm").mkdir(parents=True)
(ws / ".mmi-pm" / "meta.yml").write_text("repos:\n- name: demo\n")
(ws / "repos" / "demo.git").mkdir(parents=True)
(ws / "envs").mkdir()
cte.REGISTRY = tmp / "registry.json"


def expect_exit(fn, name, needle):
    try:
        fn()
        check(name, False)
    except SystemExit as e:
        check(name, needle in str(e))


# worktree absent → refus explicite
expect_exit(lambda: cte.resolve_worktree(ws, 42), "worktree absent → refus", "worktree absent")
# worktree sans karl-agent.py → refus (pas cockpit-testable)
wt = ws / "envs" / "demo-rm42"
(wt / "scripts").mkdir(parents=True)
expect_exit(lambda: cte.resolve_worktree(ws, 42), "sans karl-agent.py → refus", "cockpit-testable")
# worktree valide → résolu
(wt / "scripts" / "karl-agent.py").write_text("# stub\n")
check("worktree valide résolu", cte.resolve_worktree(ws, 42) == wt)

# — create --dry-run : aucune unité lancée, sortie annoncée —
calls = []
cte.subprocess.run = lambda *a, **k: calls.append(a) or types.SimpleNamespace(
    returncode=0, stdout="1.1.1.1 via 10.0.3.1 dev eth0 src 10.0.3.99 uid 1000", stderr="")
args = types.SimpleNamespace(rmid=42, workspace=str(ws), dry_run=True)
cte.cmd_create(args)
check("dry-run : seul `ip route` exécuté", len(calls) == 1 and calls[0][0][0] == "ip")

# — registre : écriture/lecture atomiques —
cte._save_registry({"42": {"port": 9942, "url": "http://x/"}})
check("registre relu", cte._registry()["42"]["port"] == 9942)

# — teardown --if-exists sans instance : silencieux, rien stoppé —
calls.clear()
cte._save_registry({})
cte.cmd_teardown(types.SimpleNamespace(rmid=99, workspace=str(ws), if_exists=True, dry_run=False))
check("teardown --if-exists : silencieux sans instance", not calls)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests pm-cockpit-test-env RM2356 passent")
