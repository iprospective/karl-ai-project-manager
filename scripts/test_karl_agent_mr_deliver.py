#!/usr/bin/env python3
"""Tests RM2355 — /mr/deliver : livre la branche d'un ticket (MR + merge → dev)
pour débloquer un verdict bloqué par la merge gate RM2319.

Unitaire (sans réseau, sans GitLab) : résolution (bare code, branche frontmatter,
intégration) depuis un workspace fabriqué, gardes, et argv pm-mr construit —
subprocess mocké. Lancer : python3 scripts/test_karl_agent_mr_deliver.py
"""
import importlib.util
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def expect_api(code, fn, name):
    try:
        fn()
        check(name, False)
    except ka.ApiError as e:
        check(name, e.code == code)
    except Exception as e:  # noqa: BLE001
        print("   (exception inattendue :", repr(e), ")")
        check(name, False)


# — workspace fabriqué : .mmi-pm/meta.yml (mono-repo) + repos/<name>.git + tâche —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2355-"))
ws = tmp / "ws"
(ws / ".mmi-pm" / "tasks").mkdir(parents=True)
(ws / ".mmi-pm" / "meta.yml").write_text(
    "repos:\n- name: demo\n  integration_branch: dev\n", encoding="utf-8")
(ws / "repos" / "demo.git").mkdir(parents=True)
task = ws / ".mmi-pm" / "tasks" / "RM2355_x.md"
task.write_text("---\nredmine_id: 2355\ngit:\n  branch: 2355-feature-m1-s1\n"
                "  repo: demo\nstatus: a_tester_demandeur\n---\n# corps\n", encoding="utf-8")

# on court-circuite la localisation projet/workspace (testée ailleurs) pour
# isoler la logique de _mr_deliver_context
ka._find_task_file = lambda rm: task if str(rm) == "2355" else None
ka._resolve_workspace = lambda _pd: ws

# — cas nominal —
bare, branch, integration = ka._mr_deliver_context("2355")
check("bare = repos/demo.git", bare == ws / "repos" / "demo.git")
check("branche lue au frontmatter", branch == "2355-feature-m1-s1")
check("intégration = dev", integration == "dev")

# — gardes —
expect_api(400, lambda: ka._mr_deliver_context("abc"), "rm_id non numérique → 400")
expect_api(404, lambda: ka._mr_deliver_context("9999"), "ticket inconnu → 404")

# branche absente du frontmatter → 400
task.write_text("---\nredmine_id: 2355\ngit:\n  repo: demo\n---\n", encoding="utf-8")
expect_api(400, lambda: ka._mr_deliver_context("2355"), "git.branch absent → 400")
# restaure
task.write_text("---\ngit:\n  branch: 2355-feature-m1-s1\n---\n", encoding="utf-8")

# multi-repo → refus (livraison auto mono-repo)
(ws / ".mmi-pm" / "meta.yml").write_text(
    "repos:\n- name: a\n- name: b\n", encoding="utf-8")
expect_api(400, lambda: ka._mr_deliver_context("2355"), "multi-repo → 400")
# restaure mono-repo
(ws / ".mmi-pm" / "meta.yml").write_text(
    "repos:\n- name: demo\n  integration_branch: dev\n", encoding="utf-8")

# bare absent → 400
import shutil
shutil.rmtree(ws / "repos" / "demo.git")
expect_api(400, lambda: ka._mr_deliver_context("2355"), "bare code absent → 400")
(ws / "repos" / "demo.git").mkdir(parents=True)

# — op_mr_deliver : confirm requis + argv pm-mr correct (subprocess mocké) —
expect_api(400, lambda: ka.op_mr_deliver({"rm_id": "2355"}),
           "confirm manquant → 400")

captured = {}


def _fake_run(argv, **k):
    captured["argv"] = argv
    return types.SimpleNamespace(returncode=0, stdout="✓ merge !9 → dev", stderr="")


ka.subprocess.run = _fake_run
out = ka.op_mr_deliver({"rm_id": "2355", "confirm": True})
argv = captured.get("argv", [])
check("op ok (rc 0)", out["ok"] and out["rc"] == 0)
check("argv : sous-commande create", "create" in argv and argv[argv.index("create") + 1] == "2355")
check("argv : --source = branche frontmatter",
      "--source" in argv and argv[argv.index("--source") + 1] == "2355-feature-m1-s1")
check("argv : --repo = bare code",
      "--repo" in argv and argv[argv.index("--repo") + 1].endswith("repos/demo.git"))
check("argv : --target = dev", "--target" in argv and argv[argv.index("--target") + 1] == "dev")
check("argv : --merge (atomique)", "--merge" in argv)
check("retour expose branch/target", out["branch"] == "2355-feature-m1-s1" and out["target"] == "dev")

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests /mr/deliver RM2355 passent")
