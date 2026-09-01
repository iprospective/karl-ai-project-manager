#!/usr/bin/env python3
"""Tests RM2356 — pm-cockpit-test-env (instance karl-agent de test par ticket).

Unitaire (sans systemd ni réseau) : port déterministe, résolution/refus de
worktree, dry-run, registre, teardown --if-exists silencieux.
Lancer : python3 scripts/test_pm_cockpit_test_env.py
"""
import contextlib
import importlib.util
import io
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

# — create --dry-run : rien n'est fait, tout est annoncé —
# RM2717 : le test exigeait un sondage `ip route`, hérité du pont socat lié à l'IP du
# conteneur. RM2565 l'a remplacé par un vhost Apache vers 127.0.0.1 et `container_ip()`
# a disparu du script : l'assertion survivait à ce qu'elle vérifiait. On teste
# désormais ce que le dry-run doit garantir — l'ANNONCE, et l'absence d'effet.
calls = []
cte.subprocess.run = lambda *a, **k: calls.append(a) or types.SimpleNamespace(
    returncode=0, stdout="", stderr="")
args = types.SimpleNamespace(rmid=42, workspace=str(ws), dry_run=True)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cte.cmd_create(args)
said = buf.getvalue()
check("dry-run : port déterministe annoncé", str(cte.port_for(42)) in said)
check("dry-run : vhost et test_url annoncés",
      ".lxc" in said and "test_url" in said and "[dry-run]" in said)
# le résolveur de worktree (RM2394) peut faire des lectures git : on vérifie
# l'absence d'EFFET, pas le nombre d'appels.
_verbs = [c[0][0] for c in calls if c and c[0]]
check("dry-run : aucune unité systemd", not any(v in ("systemd-run", "systemctl") for v in _verbs))
check("dry-run : aucun vhost posé", not any("vhost" in " ".join(map(str, c[0])) for c in calls if c and c[0]))
check("dry-run : registre non écrit", not cte.REGISTRY.exists())

# — create réel : STATE_DIR partagé + LOG_DIR isolé sur l'unité karl (RM2385) —
calls.clear()
cte.urllib.request.urlopen = lambda *a, **k: types.SimpleNamespace()   # /health « vivant »
cte._pes.set_test_url = lambda *a, **k: None                          # pas d'écriture frontmatter
cte.cmd_create(types.SimpleNamespace(rmid=42, workspace=str(ws), dry_run=False))
karl_unit = next((c[0] for c in calls
                  if c[0][0] == "systemd-run" and "--unit=karl-test-42" in c[0]), None)
check("create : unité karl lancée", karl_unit is not None)
state_flag = next((a for a in (karl_unit or []) if a.startswith("--setenv=KARL_AGENT_STATE_DIR=")), "")
log_flag = next((a for a in (karl_unit or []) if a.startswith("--setenv=KARL_AGENT_LOG_DIR=")), "")
check("STATE_DIR pointé sur l'état prod partagé (…/karl-agent)",
      state_flag.endswith("/karl-agent"))
check("LOG_DIR isolé par instance (logdir-42)", "logdir-42" in log_flag)
check("STATE_DIR ≠ LOG_DIR (état partagé, logs isolés)",
      state_flag.split("=", 1)[-1] != log_flag.split("=", 1)[-1])

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
