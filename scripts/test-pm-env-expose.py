#!/usr/bin/env python3
"""Tests de pm-env-expose (RM2358) — stdlib only, sans root ni Redmine.

Unitaires (derive_name, pick_port, update_test_url, registre) + un expose/
unexpose de bout en bout sur un workspace-fixture, helper et Redmine factices.
Lancer : python3 scripts/test-pm-env-expose.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_env_expose", HERE / "pm-env-expose.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FAILURES = []


def check(label, cond, detail=""):
    print(("✓ " if cond else "✗ ") + label + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def expect_die(label, fn):
    try:
        fn()
    except SystemExit:
        check(label, True)
    else:
        check(label, False, "aurait dû mourir")


# ── derive_name : convention <project>-rm<id>[-s<seq>] ──────────────────────
d = lambda base, rmid: mod.derive_name(Path("/x/envs") / base, rmid)  # noqa: E731
check("env canonique → <repo>-rm<id>",
      d("ai-project-management-rm2334", 2334) == "ai-project-management-rm2334")
check("worktree session -dev-<id>-s<n> → <repo>-rm<id>-s<n>",
      d("ai-project-management-dev-2334-s23", 2334) == "ai-project-management-rm2334-s23")
check("worktree -rm<id>-s<n> conservé",
      d("maths_v5-rm1998-s4", 1998) == "maths_v5-rm1998-s4")
check("regex NAME_RE refuse un nom sans -rm<id>",
      not mod.NAME_RE.match("ai-project-management-dev"))
expect_die("dossier sans repo dérivable → die", lambda: d("rm42", 42))

# ── pick_port ────────────────────────────────────────────────────────────────
reg = {"1": {"port": 21000}, "2": {"port": 21001}}
check("pool : premier port libre", mod.pick_port(reg, None) == 21002)
check("port explicite accepté", mod.pick_port(reg, 9999) == 9999)
expect_die("port hors bornes refusé", lambda: mod.pick_port(reg, 80))

# ── update_test_url (verrou simple + nettoyage conditionnel) ─────────────────
tmp = Path(tempfile.mkdtemp(prefix="pm-env-expose-test-"))
task = tmp / "RM99_test.md"
task.write_text("---\ntest_url: null\nupdated: 2026-01-01T00:00\n---\ncorps\n")
check("pose de test_url", mod.update_test_url(task, "http://a-rm99.lxc/", None))
check("test_url écrit", "test_url: http://a-rm99.lxc/" in task.read_text())
check("updated rafraîchi", "updated: 2026-01-01T00:00" not in task.read_text())
check("idempotent (même valeur → False)",
      not mod.update_test_url(task, "http://a-rm99.lxc/", None))
check("nettoyage refusé si autre valeur",
      not mod.update_test_url(task, None, "http://autre-rm99.lxc"))
check("nettoyage si valeur attendue", mod.update_test_url(task, None, "http://a-rm99.lxc"))
check("test_url → null", "test_url: null" in task.read_text())

# ── expose / unexpose de bout en bout (fixture + helper factice) ─────────────
ws = tmp / "workspace"
(ws / ".mmi-pm").mkdir(parents=True)
(ws / "envs" / "demo-rm77").mkdir(parents=True)
proj = tmp / "projects" / "clients" / "c1" / "projects" / "p1"
(proj / "tasks").mkdir(parents=True)
(proj / "workspace").symlink_to(ws)
tf = proj / "tasks" / "RM77_demo.md"
tf.write_text("---\nredmine_id: 77\ngit:\n  worktree: null\ntest_url: null\n"
              "updated: 2026-01-01T00:00\n---\ncorps\n")

calls = []
mod.PMConfig = SimpleNamespace(load=lambda: SimpleNamespace(projects_root=tmp / "projects"))
mod.run_vhost = lambda args, dry: calls.append((tuple(args), dry))
mod.push_cf14 = lambda rmid, value, dry: calls.append(("cf14", rmid, value))

mod.cmd_expose(SimpleNamespace(rmid=77, port=None, workspace=None, dry_run=False))
check("run_vhost appelé : vhost-proxy-add demo-rm77 21000",
      (("vhost-proxy-add", "demo-rm77", "21000"), False) in calls)
check("CF14 poussé avec l'URL", ("cf14", 77, "http://demo-rm77.lxc/") in calls)
reg2 = json.loads((ws / "var" / "env-expose.json").read_text())
check("registre écrit", reg2.get("77", {}).get("name") == "demo-rm77"
      and reg2["77"]["port"] == 21000)
check("frontmatter test_url posé", "test_url: http://demo-rm77.lxc/" in tf.read_text())
check("log appendé", "Env exposé" in (proj / "tasks" / "RM77_demo.log.md").read_text())

calls.clear()
mod.cmd_expose(SimpleNamespace(rmid=77, port=None, workspace=None, dry_run=False))
reg3 = json.loads((ws / "var" / "env-expose.json").read_text())
check("re-expose idempotent : même port depuis le registre",
      reg3["77"]["port"] == 21000 and
      (("vhost-proxy-add", "demo-rm77", "21000"), False) in calls)

calls.clear()
mod.cmd_unexpose(SimpleNamespace(rmid=77, port=None, workspace=None, dry_run=False))
check("run_vhost appelé : vhost-remove", (("vhost-remove", "demo-rm77"), False) in calls)
check("registre nettoyé", "77" not in json.loads((ws / "var" / "env-expose.json").read_text()))
check("test_url nettoyé", "test_url: null" in tf.read_text())
check("CF14 vidé", ("cf14", 77, "") in calls)

print(f"\n{len(FAILURES)} échec(s)" if FAILURES else "\nTous les tests passent.")
sys.exit(1 if FAILURES else 0)
